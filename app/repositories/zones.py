from sqlmodel import Session, select

from app.models.zones import Zone


def get_zone_by_name(
    session: Session,
    name: str,
) -> Zone | None:
    statement = select(Zone).where(Zone.name == name)
    return session.exec(statement).first()


def get_zone_by_id(
    session: Session,
    zone_id: int,
) -> Zone | None:
    return session.get(Zone, zone_id)
