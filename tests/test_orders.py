from datetime import date, time, timedelta
from typing import Generator

import pytest
from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401 -- registers every table with SQLModel metadata
from app.models.order_item import OrderItem
from app.models.orders import Order, OrderStatus
from app.models.pickups import Pickup
from app.models.price_list import PriceList
from app.models.slots import Slot
from app.models.status_history import StatusHistory
from app.models.user import Role, User
from app.models.zones import Zone
from app.schemas.order import (
    AssignCourier,
    CreateOrder,
    CreateOrderItem,
    GarmentType,
    OrderOut,
    UpdateOrderStatus,
)
from app.services.orders import assign_courier, create_order, update_order_status


@pytest.fixture
def session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session
    SQLModel.metadata.drop_all(engine)


def seed_booking_data(session: Session) -> tuple[User, Slot]:
    zone = Zone(name="Test Zone")
    session.add(zone)
    session.flush()
    assert zone.id is not None

    customer = User(
        name="Test Customer",
        email="customer@example.com",
        hashed_password="not-used-in-this-test",
        zone_id=zone.id,
    )
    slot = Slot(
        zone_id=zone.id,
        capacity=2,
        date=date.today() + timedelta(days=1),
        start_at=time(9, 0),
        stop_at=time(11, 0),
    )
    session.add(customer)
    session.add(slot)
    session.add(PriceList(garment=GarmentType.SHIRT, unit_price=50_000))
    session.commit()
    session.refresh(customer)
    session.refresh(slot)
    return customer, slot


def test_create_order_creates_complete_booking(session: Session) -> None:
    customer, slot = seed_booking_data(session)
    assert slot.id is not None

    order = create_order(
        session=session,
        customer=customer,
        data=CreateOrder(
            slot_id=slot.id,
            items=[CreateOrderItem(garment=GarmentType.SHIRT, quantity=2)],
        ),
    )

    assert order.total == 100_000
    assert order.status == OrderStatus.BOOKED
    assert len(order.items) == 1
    assert order.items[0].quantity == 2
    assert order.pickup is not None
    assert order.pickup.slot_id == slot.id
    assert OrderOut.model_validate(order).pickup.slot_id == slot.id

    session.refresh(slot)
    assert slot.booked_count == 1
    histories = session.exec(select(StatusHistory)).all()
    assert len(histories) == 1
    assert histories[0].stage == OrderStatus.BOOKED
    assert histories[0].actor_id == customer.id


def test_create_order_rolls_back_when_a_price_is_missing(session: Session) -> None:
    customer, slot = seed_booking_data(session)
    assert slot.id is not None

    with pytest.raises(HTTPException) as error:
        create_order(
            session=session,
            customer=customer,
            data=CreateOrder(
                slot_id=slot.id,
                items=[CreateOrderItem(garment=GarmentType.JEAN, quantity=1)],
            ),
        )

    assert error.value.status_code == 422
    assert session.exec(select(Order)).all() == []
    assert session.exec(select(OrderItem)).all() == []
    assert session.exec(select(Pickup)).all() == []
    assert session.exec(select(StatusHistory)).all() == []
    session.refresh(slot)
    assert slot.booked_count == 0


def test_ops_assigns_courier_and_courier_collects_order(
    session: Session,
) -> None:
    customer, slot = seed_booking_data(session)
    assert customer.zone_id is not None
    assert slot.id is not None

    courier = User(
        name="Test Courier",
        email="courier@example.com",
        hashed_password="not-used-in-this-test",
        role=Role.COURIER,
        zone_id=customer.zone_id,
    )
    session.add(courier)
    session.commit()
    session.refresh(courier)
    assert courier.id is not None

    order = create_order(
        session=session,
        customer=customer,
        data=CreateOrder(
            slot_id=slot.id,
            items=[CreateOrderItem(garment=GarmentType.SHIRT, quantity=1)],
        ),
    )
    assert order.id is not None

    assigned = assign_courier(
        session=session,
        order_id=order.id,
        data=AssignCourier(courier_id=courier.id),
    )
    assert assigned.pickup is not None
    assert assigned.pickup.courier_id == courier.id

    collected = update_order_status(
        session=session,
        order_id=order.id,
        data=UpdateOrderStatus(status=OrderStatus.COLLECTED),
        actor=courier,
    )
    assert collected.status == OrderStatus.COLLECTED

    with pytest.raises(HTTPException) as error:
        update_order_status(
            session=session,
            order_id=order.id,
            data=UpdateOrderStatus(status=OrderStatus.WASHING),
            actor=courier,
        )
    assert error.value.status_code == 403
    assert len(session.exec(select(StatusHistory)).all()) == 2

    with pytest.raises(HTTPException) as error:
        update_order_status(
            session=session,
            order_id=order.id,
            data=UpdateOrderStatus(status=OrderStatus.CANCELLED),
            actor=customer,
        )
    assert error.value.status_code == 403
    assert len(session.exec(select(StatusHistory)).all()) == 2


def test_customer_cancellation_releases_slot_capacity(session: Session) -> None:
    customer, slot = seed_booking_data(session)
    assert slot.id is not None

    order = create_order(
        session=session,
        customer=customer,
        data=CreateOrder(
            slot_id=slot.id,
            items=[CreateOrderItem(garment=GarmentType.SHIRT, quantity=1)],
        ),
    )
    assert order.id is not None

    cancelled = update_order_status(
        session=session,
        order_id=order.id,
        data=UpdateOrderStatus(status=OrderStatus.CANCELLED),
        actor=customer,
    )

    assert cancelled.status == OrderStatus.CANCELLED
    session.refresh(slot)
    assert slot.booked_count == 0
    histories = session.exec(
        select(StatusHistory).order_by(StatusHistory.id)                 # type: ignore[arg-type]
    ).all()
    assert [entry.stage for entry in histories] == [
        OrderStatus.BOOKED,
        OrderStatus.CANCELLED,
    ]
