from datetime import date, time

from sqlmodel import Session, select

from app.models.slots import Slot


def get_slot_by_zone_and_start(
    session: Session,
    zone_id: int,
    slot_date: date,
    start_at: time,
) -> Slot | None:
    statement = select(Slot).where(
        Slot.zone_id == zone_id,
        Slot.date == slot_date,
        Slot.start_at == start_at,
    )
    return session.exec(statement).first()


def create_slot_record(
    session: Session,
    slot: Slot,
) -> Slot:
    session.add(slot)
    session.flush()
    return slot
