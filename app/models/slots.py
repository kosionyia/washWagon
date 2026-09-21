from datetime import time, date
from typing import TYPE_CHECKING

from sqlalchemy import UniqueConstraint
from sqlmodel import SQLModel, Field, Relationship

if TYPE_CHECKING:
    from app.models.zones import Zone
    from app.models.pickups import Pickup

class Slot(SQLModel, table=True):

    __tablename__ = "slots"
    __table_args__ = (
        UniqueConstraint(
            "zone_id",
            "date",
            "start_at",
            name="uq_slots_zone_date_start",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    zone_id: int = Field(foreign_key="zones.id")
    capacity: int = Field(default=5, gt=0)
    booked_count: int =Field(default=0, ge=0)
    date: date
    start_at: time
    stop_at: time
    
    zone: "Zone" = Relationship(back_populates="slots")
    pickups: list["Pickup"] = Relationship(back_populates="slot")
