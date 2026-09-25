from datetime import date, time, timedelta

from sqlalchemy.engine import Engine
from sqlmodel import Session

from app.models.price_list import PriceList
from app.models.slots import Slot
from app.models.user import User
from app.models.zones import Zone
from app.schemas.order import GarmentType
from app.utils.security import create_access_token


def seed_booking_data(
    engine: Engine,
    *,
    capacity: int = 5,
    booked_count: int = 0,
    customer_count: int = 1,
    slot_date: date | None = None,
    prices: dict[GarmentType, int] | None = None,
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
        for garment, unit_price in (
            prices or {GarmentType.SHIRT: 50_000}
        ).items():
            session.add(PriceList(garment=garment, unit_price=unit_price))

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


def authorization(user: User) -> dict[str, str]:
    assert user.id is not None
    token = create_access_token(user.id, user.role.value)
    return {"Authorization": f"Bearer {token}"}


def order_payload(
    slot_id: int,
    items: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "slot_id": slot_id,
        "items": items or [{"garment": "shirt", "quantity": 1}],
    }
