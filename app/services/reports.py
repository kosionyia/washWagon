from datetime import date

from sqlalchemy import func
from sqlmodel import Session, select

from app.models.orders import Order
from app.models.payment import Payment, PaymentStatus
from app.models.pickups import Pickup
from app.models.slots import Slot
from app.models.user import Role, User
from app.models.zones import Zone
from app.schemas.reports import (
    CourierBoardEntry,
    CourierPickup,
    ZoneRevenue,
)


def revenue_by_zone(
    session: Session,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[ZoneRevenue]:
    """Summarize confirmed payments by pickup zone."""
    statement = (
        select(
            Zone.id,
            Zone.name,
            func.count(Payment.id),
            func.sum(Payment.amount),
        )
        .join(Slot, Slot.zone_id == Zone.id)
        .join(Pickup, Pickup.slot_id == Slot.id)
        .join(Payment, Payment.pickup_id == Pickup.id)
        .where(Payment.status == PaymentStatus.PAID)
    )

    if date_from is not None:
        statement = statement.where(Slot.date >= date_from)
    if date_to is not None:
        statement = statement.where(Slot.date <= date_to)

    statement = statement.group_by(Zone.id, Zone.name).order_by(Zone.name)
    return [
        ZoneRevenue(
            zone_id=zone_id,
            zone_name=zone_name,
            paid_orders=paid_orders,
            revenue=revenue,
        )
        for zone_id, zone_name, paid_orders, revenue in session.exec(statement)
    ]


def courier_board(
    session: Session,
    board_date: date,
) -> list[CourierBoardEntry]:
    """Show every courier and their assigned pickups for a date."""
    couriers = session.exec(
        select(User)
        .where(User.role == Role.COURIER)
        .order_by(User.name, User.id)
    ).all()

    board: list[CourierBoardEntry] = []
    for courier in couriers:
        if courier.id is None:
            continue

        assignments = session.exec(
            select(Order, Pickup, Slot)
            .join(Pickup, Pickup.order_id == Order.id)
            .join(Slot, Slot.id == Pickup.slot_id)
            .where(
                Pickup.courier_id == courier.id,
                Slot.date == board_date,
            )
            .order_by(Slot.start_at, Order.id)
        ).all()

        board.append(
            CourierBoardEntry(
                courier_id=courier.id,
                courier_name=courier.name,
                zone_id=courier.zone_id,
                pickups=[
                    CourierPickup(
                        order_id=order.id,
                        pickup_id=pickup.id,
                        customer_id=order.customer_id,
                        slot_id=slot.id,
                        start_at=slot.start_at,
                        stop_at=slot.stop_at,
                        status=order.status,
                    )
                    for order, pickup, slot in assignments
                    if order.id is not None
                    and pickup.id is not None
                    and slot.id is not None
                ],
            )
        )

    return board
