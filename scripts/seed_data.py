"""Seed WashWagon with the reference data needed to start the API."""

from dataclasses import dataclass
from datetime import date, time, timedelta

from sqlmodel import Session, select

from app.models.price_list import PriceList
from app.models.slots import Slot
from app.models.user import Role, User
from app.models.zones import Zone
from app.schemas.order import GarmentType
from app.utils.config import settings
from app.utils.database import engine
from app.utils.security import hash_password


ZONE_NAMES = (
    "Lekki",
    "Ikeja",
    "Victoria Island",
    "Yaba",
)

# All prices are stored in kobo: 150_000 kobo = NGN 1,500.
GARMENT_PRICES = {
    GarmentType.SHIRT: 150_000,
    GarmentType.JEAN: 200_000,
    GarmentType.JOGGER: 180_000,
    GarmentType.DRESS: 250_000,
    GarmentType.SKIRT: 150_000,
    GarmentType.JACKET: 300_000,
    GarmentType.SWEATER: 250_000,
    GarmentType.SHOES: 300_000,
}

SLOT_WINDOWS = (
    (time(9), time(11)),
    (time(12), time(14)),
    (time(15), time(17)),
)


@dataclass
class SeedResult:
    zones: int = 0
    prices: int = 0
    slots: int = 0
    ops_managers: int = 0


def seed_initial_data(
    session: Session,
    *,
    ops_password: str,
    first_slot_date: date | None = None,
    slot_days: int = 7,
) -> SeedResult:
    """Create missing reference data and return creation counts."""
    result = SeedResult()
    zones = _seed_zones(session, result)
    _seed_prices(session, result)
    _seed_ops_manager(session, ops_password, result)
    _seed_slots(
        session,
        zones,
        first_slot_date or date.today() + timedelta(days=1),
        slot_days,
        result,
    )
    session.commit()
    return result


def _seed_zones(
    session: Session,
    result: SeedResult,
) -> list[Zone]:
    zones: list[Zone] = []
    for name in ZONE_NAMES:
        zone = session.exec(select(Zone).where(Zone.name == name)).first()
        if zone is None:
            zone = Zone(name=name)
            session.add(zone)
            session.flush()
            result.zones += 1
        zones.append(zone)
    return zones


def _seed_prices(session: Session, result: SeedResult) -> None:
    for garment, unit_price in GARMENT_PRICES.items():
        price = session.exec(
            select(PriceList).where(PriceList.garment == garment)
        ).first()
        if price is None:
            session.add(
                PriceList(
                    garment=garment,
                    unit_price=unit_price,
                )
            )
            result.prices += 1


def _seed_ops_manager(
    session: Session,
    password: str,
    result: SeedResult,
) -> None:
    manager = session.exec(
        select(User).where(User.email == settings.OPS_MANAGER_EMAIL)
    ).first()
    if manager is None:
        session.add(
            User(
                name=settings.OPS_MANAGER_NAME,
                email=settings.OPS_MANAGER_EMAIL,
                hashed_password=hash_password(password),
                role=Role.OPS_MANAGER,
            )
        )
        result.ops_managers += 1


def _seed_slots(
    session: Session,
    zones: list[Zone],
    first_slot_date: date,
    slot_days: int,
    result: SeedResult,
) -> None:
    for day_offset in range(slot_days):
        slot_date = first_slot_date + timedelta(days=day_offset)
        for zone in zones:
            if zone.id is None:
                raise RuntimeError("Zone must be saved before creating slots")
            for start_at, stop_at in SLOT_WINDOWS:
                slot = session.exec(
                    select(Slot).where(
                        Slot.zone_id == zone.id,
                        Slot.date == slot_date,
                        Slot.start_at == start_at,
                    )
                ).first()
                if slot is None:
                    session.add(
                        Slot(
                            zone_id=zone.id,
                            capacity=5,
                            date=slot_date,
                            start_at=start_at,
                            stop_at=stop_at,
                        )
                    )
                    result.slots += 1


def main() -> None:
    if not settings.OPS_MANAGER_PASSWORD:
        raise SystemExit(
            "OPS_MANAGER_PASSWORD must be set before seeding initial data"
        )

    with Session(engine) as session:
        try:
            result = seed_initial_data(
                session,
                ops_password=settings.OPS_MANAGER_PASSWORD,
            )
        except Exception:
            session.rollback()
            raise

    print("Initial data is ready.")
    print(f"Created zones: {result.zones}")
    print(f"Created prices: {result.prices}")
    print(f"Created slots: {result.slots}")
    print(f"Created ops managers: {result.ops_managers}")


if __name__ == "__main__":
    main()
