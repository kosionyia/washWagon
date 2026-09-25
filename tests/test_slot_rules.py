from datetime import date, time, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlmodel import Session

from app.models.slots import Slot
from tests.test_helpers import authorization, order_payload, seed_booking_data


def test_past_slot_is_422_and_cancellation_returns_the_space(
    acceptance_client: TestClient,
    acceptance_engine: Engine,
) -> None:
    past_slot_id, customers = seed_booking_data(
        acceptance_engine,
        slot_date=date.today() - timedelta(days=1),
    )
    headers = authorization(customers[0])

    past_booking = acceptance_client.post(
        "/orders/",
        json=order_payload(past_slot_id),
        headers=headers,
    )
    assert past_booking.status_code == 422

    with Session(acceptance_engine) as session:
        past_slot = session.get(Slot, past_slot_id)
        assert past_slot is not None
        future_slot = Slot(
            zone_id=past_slot.zone_id,
            capacity=1,
            date=date.today() + timedelta(days=1),
            start_at=time(9),
            stop_at=time(11),
        )
        session.add(future_slot)
        session.commit()
        session.refresh(future_slot)
        assert future_slot.id is not None
        future_slot_id = future_slot.id

    created = acceptance_client.post(
        "/orders/",
        json=order_payload(future_slot_id),
        headers=headers,
    )
    assert created.status_code == 201

    cancelled = acceptance_client.patch(
        f"/orders/{created.json()['id']}/status",
        json={"status": "cancelled"},
        headers=headers,
    )
    assert cancelled.status_code == 200

    with Session(acceptance_engine) as session:
        future_slot = session.get(Slot, future_slot_id)
        assert future_slot is not None
        assert future_slot.booked_count == 0
