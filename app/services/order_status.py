import logging

from fastapi import HTTPException, status
from redis.exceptions import RedisError
from sqlmodel import Session, select

from app.models.orders import Order, OrderStatus
from app.models.pickups import Pickup
from app.models.slots import Slot
from app.models.status_history import StatusHistory
from app.models.user import Role, User
from app.schemas.order import UpdateOrderStatus
from app.services.order_events import publish_order_status
from app.services.order_queries import get_order_with_booking


logger = logging.getLogger(__name__)


def update_order_status(
    session: Session,
    order_id: int,
    data: UpdateOrderStatus,
    actor: User,
) -> Order:
    try:
        if actor.id is None:
            raise RuntimeError("Cannot record an action for an unsaved user")

        order = session.exec(
            select(Order)
            .where(Order.id == order_id)
            .with_for_update()
        ).first()
        if order is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found",
            )

        pickup = session.exec(
            select(Pickup)
            .where(Pickup.order_id == order_id)
            .with_for_update()
        ).first()
        if pickup is None or pickup.id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Order has no pickup booking",
            )

        _authorize_status_change(order, pickup, actor, data.status)
        if not order.status.can_transition_to(data.status):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Order cannot move from {order.status.value} "
                    f"to {data.status.value}"
                ),
            )

        if data.status == OrderStatus.CANCELLED:
            _release_slot(session, pickup.slot_id)

        order.status = data.status
        session.add(order)
        session.add(
            StatusHistory(
                pickup_id=pickup.id,
                actor_id=actor.id,
                stage=data.status,
            )
        )
        session.commit()
        _publish_status_change(order_id, data.status)

        result = get_order_with_booking(session, order_id)
        if result is None:
            raise RuntimeError("Updated order could not be reloaded")
        return result
    except HTTPException:
        session.rollback()
        raise
    except Exception:
        session.rollback()
        raise


def _publish_status_change(
    order_id: int,
    order_status: OrderStatus,
) -> None:
    try:
        publish_order_status(order_id, order_status)
    except (RedisError, RuntimeError):
        logger.exception(
            "Order %s was updated, but its live event could not be published",
            order_id,
        )


def _release_slot(session: Session, slot_id: int) -> None:
    slot = session.exec(
        select(Slot).where(Slot.id == slot_id).with_for_update()
    ).first()
    if slot is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Pickup slot no longer exists",
        )
    slot.booked_count = max(0, slot.booked_count - 1)
    session.add(slot)


def _authorize_status_change(
    order: Order,
    pickup: Pickup,
    actor: User,
    next_status: OrderStatus,
) -> None:
    if actor.role == Role.OPS_MANAGER:
        return
    if (
        actor.role == Role.CUSTOMER
        and order.customer_id == actor.id
        and order.status == OrderStatus.BOOKED
        and next_status == OrderStatus.CANCELLED
    ):
        return

    courier_stages = {
        OrderStatus.COLLECTED,
        OrderStatus.WASHING,
        OrderStatus.READY,
        OrderStatus.OUT_FOR_DELIVERY,
        OrderStatus.DELIVERED,
    }
    if (
        actor.role == Role.COURIER
        and pickup.courier_id == actor.id
        and next_status in courier_stages
    ):
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have permission to make this status change",
    )
