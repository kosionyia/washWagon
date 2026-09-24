from typing import Optional

from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.pickups import Pickup


class PaymentStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"


class PaymentMethod(str, Enum):
    ONLINE = "online"
    CASH = "cash"


class Payment(SQLModel, table=True):
    __tablename__ = "payments"

    id: Optional[int] = Field(default=None, primary_key=True)
    pickup_id: int = Field(foreign_key="pickups.id", unique=True)
    amount: int = Field(
        gt=0,
        description="Payment amount in kobo", 
        )
    status: PaymentStatus = Field(default=PaymentStatus.PENDING)
    method: PaymentMethod = Field(default=PaymentMethod.ONLINE)
    currency: str = Field(default="NGN", max_length=3)
    reference: str = Field(unique=True, index=True)
    authorization_url: Optional[str] = None
    access_code: Optional[str] = None
    paid_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    pickup: "Pickup" = Relationship(back_populates="payment")
