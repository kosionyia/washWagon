from sqlmodel import Session, select

from app.models.price_list import PriceList
from app.schemas.order import GarmentType


def get_price_by_garment(
    session: Session,
    garment: GarmentType,
) -> PriceList | None:
    statement = select(PriceList).where(
        PriceList.garment == garment,
    )
    return session.exec(statement).first()
