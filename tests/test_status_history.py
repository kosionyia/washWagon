import pytest
from fastapi import HTTPException
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from app.models.orders import OrderStatus
from app.models.status_history import StatusHistory
from app.models.user import Role, User
from app.schemas.order import CreateOrder, CreateOrderItem, GarmentType, UpdateOrderStatus
from app.services.order_booking import create_order
from app.services.order_status import update_order_status
from tests.test_helpers import seed_booking_data


def test_out_of_order_is_409_and_in_order_stages_add_one_history_each(
    acceptance_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.order_status.publish_order_status",
        lambda order_id, order_status: None,
    )
    slot_id, customers = seed_booking_data(acceptance_engine)

    with Session(acceptance_engine) as session:
        customer = session.get(User, customers[0].id)
        assert customer is not None
        order = create_order(
            session,
            customer,
            CreateOrder(
                slot_id=slot_id,
                items=[CreateOrderItem(garment=GarmentType.SHIRT, quantity=1)],
            ),
        )
        assert order.id is not None and order.pickup is not None
        courier = User(
            name="Acceptance Tracking Courier",
            email="acceptance-tracking-courier@example.com",
            hashed_password="unused",
            role=Role.COURIER,
            zone_id=customer.zone_id,
        )
        session.add(courier)
        session.commit()
        session.refresh(courier)
        order.pickup.courier_id = courier.id
        session.add(order.pickup)
        session.commit()

        initial_count = len(session.exec(select(StatusHistory)).all())
        with pytest.raises(HTTPException) as error:
            update_order_status(
                session,
                order.id,
                UpdateOrderStatus(status=OrderStatus.DELIVERED),
                courier,
            )
        assert error.value.status_code == 409
        assert len(session.exec(select(StatusHistory)).all()) == initial_count

        stages = [
            OrderStatus.COLLECTED,
            OrderStatus.WASHING,
            OrderStatus.READY,
            OrderStatus.OUT_FOR_DELIVERY,
            OrderStatus.DELIVERED,
        ]
        for expected_count, stage in enumerate(stages, start=initial_count + 1):
            updated = update_order_status(
                session,
                order.id,
                UpdateOrderStatus(status=stage),
                courier,
            )
            assert updated.status == stage
            assert len(session.exec(select(StatusHistory)).all()) == expected_count

        histories = session.exec(
            select(StatusHistory).order_by(StatusHistory.id)  # type: ignore[arg-type]
        ).all()
        assert [history.stage for history in histories] == [
            OrderStatus.BOOKED,
            *stages,
        ]
