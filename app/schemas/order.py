from pydantic import BaseModel, ConfigDict, Field

from enum import Enum
from datetime import datetime

from app.models.orders import OrderStatus


class GarmentType(str, Enum):
    SHIRT = "shirt"
    JEAN = "jean"
    JOGGER = "jogger"
    DRESS = "dress"
    SKIRT = "skirt"
    JACKET = "jacket"
    SWEATER = "sweater"
    SHOES = "shoes"

class CreateOrderItem(BaseModel):
    garment: GarmentType
    quantity: int = Field(gt=0)


class CreateOrder(BaseModel):
    slot_id: int = Field(gt=0)
    items: list[CreateOrderItem] = Field(min_length=1)


class OrderItemOut(BaseModel):
    id: int
    garment: GarmentType
    quantity: int
    unit_price: int = Field(
            description="Captured unit price in kobo",
        )
    model_config = ConfigDict(from_attributes=True)


class PickupSummary(BaseModel):
    id: int
    slot_id: int
    courier_id: int | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AssignCourier(BaseModel):
    courier_id: int = Field(gt=0)


class UpdateOrderStatus(BaseModel):
    status: OrderStatus


class StatusHistoryOut(BaseModel):
    id: int
    actor_id: int
    stage: OrderStatus
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    model_config = ConfigDict(from_attributes=True)


class PickupSummary(BaseModel):
    id: int
    slot_id: int
    courier_id: int | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrderOut(BaseModel):
    id: int
    customer_id: int
    total: int = Field(
        description="Order total in kobo",
    )    
    status: str
    created_at: datetime
    items: list[OrderItemOut]
    pickup: PickupSummary

    model_config = ConfigDict(from_attributes=True)
