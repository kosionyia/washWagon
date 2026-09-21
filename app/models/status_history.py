from datetime import datetime, timezone
from sqlmodel import Relationship, SQLModel, Field

from app.models.orders import OrderStatus

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.pickups import Pickup


class StatusHistory(SQLModel, table=True):

    __tablename__ = "status_history"

    id: int | None = Field(default=None, primary_key=True)
    pickup_id: int = Field(foreign_key="pickups.id")
    actor_id: int = Field(foreign_key="users.id")
    stage: OrderStatus
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    pickup: "Pickup" = Relationship(back_populates="status_history")
