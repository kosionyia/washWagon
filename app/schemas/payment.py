from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.payment import PaymentMethod, PaymentStatus


class PaymentOut(BaseModel):
    id: int
    pickup_id: int
    amount: int
    status: PaymentStatus
    method: PaymentMethod
    currency: str
    reference: str
    authorization_url: str | None
    access_code: str | None
    paid_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaymentInitialization(BaseModel):
    payment: PaymentOut
    authorization_url: str
    access_code: str


class WebhookResponse(BaseModel):
    received: bool = True
    duplicate: bool = False
