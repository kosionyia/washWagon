from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.models.orders import Order
from app.models.pickups import Pickup
from app.models.slots import Slot
from app.models.user import Role, User
from app.schemas.order import AssignCourier
from app.services.order_queries import get_order_with_booking


def assign_courier(
    session: Session,
    order_id: int,
    data: AssignCourier,
) -> Order:
    courier = session.get(User, data.courier_id)
    if courier is None or courier.role != Role.COURIER:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The selected user is not a courier",
        )
    return _assign_pickup(session, order_id, courier, allow_reassignment=True)


def accept_order(
    session: Session,
    order_id: int,
    courier: User,
) -> Order:
    """Assign an unclaimed pickup to the courier accepting it."""
    if courier.id is None or courier.role != Role.COURIER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only couriers can accept pickups",
        )
    return _assign_pickup(session, order_id, courier, allow_reassignment=False)


def _assign_pickup(
    session: Session,
    order_id: int,
    courier: User,
    *,
    allow_reassignment: bool,
) -> Order:
    try:
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
        if order.status.is_terminal():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A completed order cannot be assigned",
            )

        pickup = session.exec(
            select(Pickup)
            .where(Pickup.order_id == order_id)
            .with_for_update()
        ).first()
        if pickup is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Order has no pickup booking",
            )

        if (
            pickup.courier_id is not None
            and pickup.courier_id != courier.id
            and not allow_reassignment
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Pickup has already been accepted",
            )

        slot = session.get(Slot, pickup.slot_id)
        if slot is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Pickup slot no longer exists",
            )
        if courier.zone_id != slot.zone_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Courier must belong to the pickup zone",
            )

        pickup.courier_id = courier.id
        session.add(pickup)
        session.commit()

        result = get_order_with_booking(session, order_id)
        if result is None:
            raise RuntimeError("Assigned order could not be reloaded")
        return result
    except HTTPException:
        session.rollback()
        raise
    except Exception:
        session.rollback()
        raise
