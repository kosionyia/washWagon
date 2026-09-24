from datetime import time

from pydantic import BaseModel

from app.models.orders import OrderStatus


class ZoneRevenue(BaseModel):
    zone_id: int
    zone_name: str
    paid_orders: int
    revenue: int


class CourierPickup(BaseModel):
    order_id: int
    pickup_id: int
    customer_id: int
    slot_id: int
    start_at: time
    stop_at: time
    status: OrderStatus


class CourierBoardEntry(BaseModel):
    courier_id: int
    courier_name: str
    zone_id: int | None
    pickups: list[CourierPickup]
