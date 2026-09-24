from fastapi import HTTPException, status
from sqlalchemy.orm import selectinload
from sqlmodel import Session, select

from app.models.orders import Order
from app.models.pickups import Pickup
from app.models.status_history import StatusHistory
from app.models.user import Role, User


def get_order_with_booking(
    session: Session,
    order_id: int,
) -> Order | None:
    return session.exec(
        select(Order)
        .where(Order.id == order_id)
        .options(
            selectinload(Order.items),  # type: ignore[arg-type]
            selectinload(Order.pickup),  # type: ignore[arg-type]
        )
    ).first()


def list_orders_for_user(
    session: Session,
    user: User,
) -> list[Order]:
    if user.role == Role.OPS_MANAGER:
        statement = select(Order)
    elif user.role == Role.CUSTOMER:
        statement = select(Order).where(Order.customer_id == user.id)
    else:
        statement = (
            select(Order)
            .join(Pickup)
            .where(Pickup.courier_id == user.id)
        )

    statement = statement.options(
        selectinload(Order.items),  # type: ignore[arg-type]
        selectinload(Order.pickup),  # type: ignore[arg-type]
    )
    return list(session.exec(statement).all())


def get_order_for_user(
    session: Session,
    order_id: int,
    user: User,
) -> Order:
    order = get_order_with_booking(session, order_id)
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )
    if order.pickup is None or not can_view_order(order, order.pickup, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this order",
        )
    return order


def get_order_history(
    session: Session,
    order_id: int,
    viewer: User,
) -> list[StatusHistory]:
    order = get_order_with_booking(session, order_id)
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    pickup = order.pickup
    if pickup is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Order has no pickup booking",
        )
    if not can_view_order(order, pickup, viewer):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this order",
        )

    return list(
        session.exec(
            select(StatusHistory)
            .where(StatusHistory.pickup_id == pickup.id)
            .order_by(  
                StatusHistory.created_at,   # type: ignore[arg-type]
                StatusHistory.id,      # type: ignore[arg-type]
            )
        ).all()
    )


def can_view_order(order: Order, pickup: Pickup, viewer: User) -> bool:
    if viewer.role == Role.OPS_MANAGER:
        return True
    if viewer.role == Role.CUSTOMER:
        return order.customer_id == viewer.id
    return viewer.role == Role.COURIER and pickup.courier_id == viewer.id
