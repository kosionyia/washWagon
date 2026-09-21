from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.order import CreateOrderItem


class PickupCreate(BaseModel):
    slot_id: int = Field(gt=0)
    items: list[CreateOrderItem] = Field(min_length=1)


class PickupOut(BaseModel):
    id: int
    order_id: int
    slot_id: int
    courier_id: int | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
