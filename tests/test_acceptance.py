import asyncio
import hashlib
import hmac
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, time, timedelta
from threading import Barrier
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401 -- registers every table
from app.main import app
from app.models.orders import OrderStatus
from app.models.payment import Payment, PaymentStatus
from app.models.pickups import Pickup
from app.models.price_list import PriceList
from app.models.slots import Slot
from app.models.status_history import StatusHistory
from app.models.user import Role, User
from app.models.zones import Zone
from app.schemas.order import CreateOrder, CreateOrderItem, GarmentType, UpdateOrderStatus
from app.services import order_events
from app.services.order_booking import create_order
from app.services.order_status import update_order_status
from app.utils.config import settings
from app.utils.database import get_session
from app.utils.security import create_access_token


@pytest.fixture
def engine(tmp_path) -> Generator[Engine, None, None]:
    database = tmp_path / "acceptance.db"
    test_engine = create_engine(
        f"sqlite:///{database}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    SQLModel.metadata.create_all(test_engine)
    yield test_engine
    SQLModel.metadata.drop_all(test_engine)
    test_engine.dispose()


@pytest.fixture
def client(engine: Engine) -> Generator[TestClient, None, None]:
    def test_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def _seed_booking_data(
    engine: Engine,
    *,
    capacity: int = 5,
    booked_count: int = 0,
    slot_date: date | None = None,
    customer_count: int = 1,
) -> tuple[int, list[User]]:
    with Session(engine) as session:
        zone = Zone(name=f"Acceptance Zone {id(engine)}")
        session.add(zone)
        session.flush()
        assert zone.id is not None

        customers = [
            User(
                name=f"Acceptance Customer {index}",
                email=f"acceptance-{id(engine)}-{index}@example.com",
                hashed_password="unused",
                zone_id=zone.id,
            )
            for index in range(customer_count)
        ]
        session.add_all(customers)
        session.add(PriceList(garment=GarmentType.SHIRT, unit_price=50_000))
        slot = Slot(
            zone_id=zone.id,
            capacity=capacity,
            booked_count=booked_count,
            date=slot_date or date.today() + timedelta(days=1),
            start_at=time(9),
            stop_at=time(11),
        )
        session.add(slot)
        session.commit()
        session.refresh(slot)
        for customer in customers:
            session.refresh(customer)
            session.expunge(customer)
        assert slot.id is not None
        return slot.id, customers


def _order_payload(slot_id: int) -> dict[str, object]:
    return {
        "slot_id": slot_id,
        "items": [{"garment": "shirt", "quantity": 1}],
    }


def _authorization(user: User) -> dict[str, str]:
    assert user.id is not None
    token = create_access_token(user.id, user.role.value)
    return {"Authorization": f"Bearer {token}"}


def test_access_no_token_is_401_and_courier_slot_creation_is_403(
    client: TestClient,
    engine: Engine,
) -> None:
    with Session(engine) as session:
        zone = Zone(name="Access Acceptance Zone")
        session.add(zone)
        session.flush()
        assert zone.id is not None
        courier = User(
            name="Acceptance Courier",
            email="acceptance-courier@example.com",
            hashed_password="unused",
            role=Role.COURIER,
            zone_id=zone.id,
        )
        session.add(courier)
        session.commit()
        session.refresh(courier)
        zone_id = zone.id
        session.expunge(courier)

    payload = {
        "zone_id": zone_id,
        "capacity": 5,
        "date": (date.today() + timedelta(days=1)).isoformat(),
        "start_at": "09:00:00",
        "stop_at": "11:00:00",
    }

    assert client.post("/slots/", json=payload).status_code == 401
    assert (
        client.post(
            "/slots/",
            json=payload,
            headers=_authorization(courier),
        ).status_code
        == 403
    )


def test_capacity_five_with_four_bookings_becomes_full_and_returns_201(
    client: TestClient,
    engine: Engine,
) -> None:
    slot_id, customers = _seed_booking_data(engine, booked_count=4)

    response = client.post(
        "/orders/",
        json=_order_payload(slot_id),
        headers=_authorization(customers[0]),
    )

    assert response.status_code == 201
    with Session(engine) as session:
        assert session.get(Slot, slot_id).booked_count == 5  # type: ignore[union-attr]


def test_booking_a_full_slot_returns_409(
    client: TestClient,
    engine: Engine,
) -> None:
    slot_id, customers = _seed_booking_data(engine, booked_count=5)

    response = client.post(
        "/orders/",
        json=_order_payload(slot_id),
        headers=_authorization(customers[0]),
    )

    assert response.status_code == 409


def test_two_bookings_for_last_space_return_one_201_and_one_409(
    client: TestClient,
    engine: Engine,
) -> None:
    slot_id, customers = _seed_booking_data(
        engine,
        booked_count=4,
        customer_count=2,
    )
    barrier = Barrier(2)

    def book(customer: User) -> int:
        barrier.wait()
        return client.post(
            "/orders/",
            json=_order_payload(slot_id),
            headers=_authorization(customer),
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(book, customers))

    assert sorted(statuses) == [201, 409]
    with Session(engine) as session:
        assert session.get(Slot, slot_id).booked_count == 5  # type: ignore[union-attr]


def test_booking_a_past_slot_returns_422(
    client: TestClient,
    engine: Engine,
) -> None:
    slot_id, customers = _seed_booking_data(
        engine,
        slot_date=date.today() - timedelta(days=1),
    )

    response = client.post(
        "/orders/",
        json=_order_payload(slot_id),
        headers=_authorization(customers[0]),
    )

    assert response.status_code == 422


def test_cancellation_before_pickup_returns_space_to_slot(
    client: TestClient,
    engine: Engine,
) -> None:
    slot_id, customers = _seed_booking_data(engine)
    headers = _authorization(customers[0])
    created = client.post(
        "/orders/",
        json=_order_payload(slot_id),
        headers=headers,
    )
    assert created.status_code == 201

    response = client.patch(
        f"/orders/{created.json()['id']}/status",
        json={"status": "cancelled"},
        headers=headers,
    )

    assert response.status_code == 200
    with Session(engine) as session:
        assert session.get(Slot, slot_id).booked_count == 0  # type: ignore[union-attr]


def test_courier_stage_change_adds_one_status_history_row(
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.order_status.publish_order_status",
        lambda order_id, order_status: None,
    )
    slot_id, customers = _seed_booking_data(engine)
    with Session(engine) as session:
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
            name="History Courier",
            email="history-courier@example.com",
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
        before = len(session.exec(select(StatusHistory)).all())

        update_order_status(
            session,
            order.id,
            UpdateOrderStatus(status=OrderStatus.COLLECTED),
            courier,
        )

        after = len(session.exec(select(StatusHistory)).all())
        assert after == before + 1


def test_delivered_before_collected_returns_409(
    client: TestClient,
    engine: Engine,
) -> None:
    slot_id, customers = _seed_booking_data(engine)
    customer_headers = _authorization(customers[0])
    created = client.post(
        "/orders/",
        json=_order_payload(slot_id),
        headers=customer_headers,
    )
    assert created.status_code == 201
    order_id = created.json()["id"]

    with Session(engine) as session:
        pickup = session.exec(
            select(Pickup).where(Pickup.order_id == order_id)
        ).one()
        customer = session.get(User, customers[0].id)
        assert customer is not None
        courier = User(
            name="Transition Courier",
            email="transition-courier@example.com",
            hashed_password="unused",
            role=Role.COURIER,
            zone_id=customer.zone_id,
        )
        session.add(courier)
        session.commit()
        session.refresh(courier)
        pickup.courier_id = courier.id
        session.add(pickup)
        session.commit()
        courier_headers = _authorization(courier)
        session.expunge(courier)

    response = client.patch(
        f"/orders/{order_id}/status",
        json={"status": "delivered"},
        headers=courier_headers,
    )

    assert response.status_code == 409


def test_signed_webhook_pays_once_duplicate_is_unchanged_and_bad_signature_is_401(
    client: TestClient,
    engine: Engine,
) -> None:
    slot_id, customers = _seed_booking_data(engine)
    with Session(engine) as session:
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
        assert order.pickup is not None and order.pickup.id is not None
        payment = Payment(
            pickup_id=order.pickup.id,
            amount=order.total,
            reference="acceptance-webhook-reference",
        )
        session.add(payment)
        session.commit()
        session.refresh(payment)
        payment_id = payment.id

    raw_body = json.dumps(
        {
            "event": "charge.success",
            "data": {
                "id": 987654,
                "status": "success",
                "reference": "acceptance-webhook-reference",
                "amount": 50_000,
                "currency": "NGN",
            },
        },
        separators=(",", ":"),
    ).encode()
    signature = hmac.new(
        settings.PAYSTACK_SECRET_KEY.get_secret_value().encode(),
        raw_body,
        hashlib.sha512,
    ).hexdigest()
    headers = {
        "content-type": "application/json",
        "x-paystack-signature": signature,
    }

    first = client.post("/webhooks/payment", content=raw_body, headers=headers)
    with Session(engine) as session:
        paid = session.get(Payment, payment_id)
        assert paid is not None
        first_paid_at = paid.paid_at
        assert paid.status == PaymentStatus.PAID
        assert first_paid_at is not None

    duplicate = client.post("/webhooks/payment", content=raw_body, headers=headers)
    rejected = client.post(
        "/webhooks/payment",
        content=raw_body,
        headers={"x-paystack-signature": "invalid"},
    )

    assert first.status_code == 200
    assert duplicate.status_code == 200
    assert duplicate.json()["duplicate"] is True
    assert rejected.status_code == 401
    with Session(engine) as session:
        assert session.get(Payment, payment_id).paid_at == first_paid_at  # type: ignore[union-attr]


def test_stage_change_reaches_pickup_stream_within_one_second(
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    messages: list[str] = []

    class SyncRedis:
        def publish(self, channel: str, message: str) -> None:
            messages.append(message)

    class PubSub:
        async def subscribe(self, channel: str) -> None:
            return None

        async def get_message(self, **kwargs):
            if messages:
                return {"type": "message", "data": messages.pop(0)}
            await asyncio.sleep(0)
            return None

        async def unsubscribe(self, channel: str) -> None:
            return None

        async def aclose(self) -> None:
            return None

    class AsyncRedis:
        def pubsub(self) -> PubSub:
            return PubSub()

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(order_events, "get_redis_client", lambda: SyncRedis())
    monkeypatch.setattr(order_events, "get_async_redis_client", lambda: AsyncRedis())
    slot_id, customers = _seed_booking_data(engine)

    with Session(engine) as session:
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
            name="Stream Acceptance Courier",
            email="stream-acceptance-courier@example.com",
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

        async def receive_changed_status() -> str:
            stream = order_events.stream_order_status(order.id)
            await anext(stream)
            update_order_status(
                session,
                order.id,
                UpdateOrderStatus(status=OrderStatus.COLLECTED),
                courier,
            )
            event = await asyncio.wait_for(anext(stream), timeout=1.0)
            await stream.aclose()
            return event

        event = asyncio.run(receive_changed_status())

    assert '"status": "collected"' in event
