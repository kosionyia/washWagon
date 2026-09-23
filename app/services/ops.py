from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.models.price_list import PriceList
from app.models.slots import Slot
from app.models.zones import Zone
from app.repositories.prices import get_price_by_garment
from app.repositories.slots import create_slot_record, get_slot_by_zone_and_start
from app.repositories.zones import get_zone_by_id, get_zone_by_name
from app.schemas.price_list import PriceListUpdate
from app.schemas.slot import CreateSlot
from app.schemas.zone import CreateZone


def create_zone(
    session: Session,
    data: CreateZone,
) -> Zone:

    existing_zone = get_zone_by_name(
        session,
        data.name,
    )

    if existing_zone:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Zone already exists",
        )

    zone = Zone(
        name=data.name,
    )

    session.add(zone)

    try:
        session.commit()
        session.refresh(zone)

        return zone

    except IntegrityError:
        session.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Zone already exists",
        ) from None


def create_slot(
    session: Session,
    data: CreateSlot,
) -> Slot:

    # 1. Zone must exist
    
    zone = get_zone_by_id(
        session,
        data.zone_id,
    )

    if zone is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Zone does not exist",
        )

    # 2. Capacity must make sense

    if data.capacity <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Capacity must be greater than zero",
        )

    # 3. Slot cannot be in the past

    slot_start = datetime.combine(
        data.date,
        data.start_at,
        tzinfo=timezone.utc,
    )

    if slot_start <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Slot must be in the future",
        )

    # 4. Same zone cannot have duplicate start time

    existing_slot = get_slot_by_zone_and_start(
        session=session,
        zone_id=data.zone_id,
        slot_date=data.date,
        start_at=data.start_at,
    )

    if existing_slot:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A slot already exists for this zone and start time",
        )

    slot = Slot(
        zone_id=data.zone_id,
        date=data.date,
        start_at=data.start_at,
        stop_at=data.stop_at,
        capacity=data.capacity,
        booked_count=0,
    )

    try:
        create_slot_record(
            session,
            slot,
        )

        session.commit()
        session.refresh(slot)

        return slot

    except IntegrityError:
        session.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A slot already exists for this zone and start time",
        )


def set_garment_price(
    session: Session,
    data: PriceListUpdate,
) -> PriceList:

    if data.unit_price <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unit price must be greater than zero",
        )

    garment = data.garment

    price = get_price_by_garment(
        session,
        garment,
    )

    if price:
        price.unit_price = data.unit_price

    else:
        price = PriceList(
            garment=garment,
            unit_price=data.unit_price,
        )

        session.add(price)

    try:
        session.commit()
        session.refresh(price)

        return price

    except IntegrityError:
        session.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A price already exists for this garment",
        ) from None
