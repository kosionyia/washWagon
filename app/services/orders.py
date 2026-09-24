from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import Session, select

from app.models.order_item import OrderItem
from app.models.orders import Order, OrderStatus
from app.models.pickups import Pickup
from app.models.slots import Slot
from app.models.status_history import StatusHistory
from app.models.user import Role, User
from app.repositories.prices import get_price_by_garment
from app.schemas.order import AssignCourier, CreateOrder, UpdateOrderStatus


def get_order_with_booking(
    session: Session,
    order_id: int,
) -> Order | None:
    return session.exec(
        select(Order)
        .where(Order.id == order_id)
        .options(
            selectinload(Order.items),                   # type: ignore[arg-type]
            selectinload(Order.pickup),                      # type: ignore[arg-type]
        )
    ).first()


def create_order(
    session: Session,
    customer: User,
    data: CreateOrder,
) -> Order:
    try:
        if customer.id is None:
            raise RuntimeError("Cannot create an order for an unsaved customer")

        statement = (
            select(Slot)
            .where(Slot.id == data.slot_id)
            .with_for_update()
        )
        slot = session.exec(statement).first()

        if slot is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Slot does not exist",
            )

        if customer.zone_id is None or slot.zone_id != customer.zone_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Slot is not available for your zone",
            )

        slot_start = datetime.combine(
            slot.date,
            slot.start_at,
            tzinfo=timezone.utc,
        )
        if slot_start <= datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Cannot book a slot in the past",
            )

        if slot.booked_count >= slot.capacity:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Slot is full",
            )

        priced_items = []
        total = 0
        for item_data in data.items:
            price = get_price_by_garment(session, item_data.garment)
            if price is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"No price found for {item_data.garment.value}",
                )
            priced_items.append((item_data, price))
            total += price.unit_price * item_data.quantity

        order = Order(
            customer_id=customer.id,
            total=total,
            status=OrderStatus.BOOKED,
        )
        session.add(order)
        session.flush()
        if order.id is None:
            raise RuntimeError("The database did not assign an order ID")

        pickup = Pickup(order_id=order.id, slot_id=data.slot_id)
        session.add(pickup)
        session.flush()
        if pickup.id is None:
            raise RuntimeError("The database did not assign a pickup ID")

        for item_data, price in priced_items:
            if price.id is None:
                raise RuntimeError("The selected price has not been saved")
            session.add(
                OrderItem(
                    order_id=order.id,
                    price_list_id=price.id,
                    garment=item_data.garment,
                    quantity=item_data.quantity,
                    unit_price=price.unit_price,
                )
            )

        session.add(
            StatusHistory(
                pickup_id=pickup.id,
                actor_id=customer.id,
                stage=OrderStatus.BOOKED,
            )
        )
        slot.booked_count += 1
        session.add(slot)

        order_id = order.id
        session.commit()

        return session.exec(
            select(Order)
            .where(Order.id == order_id)
            .options(
                selectinload(Order.items),                   # type: ignore[arg-type]
                selectinload(Order.pickup),                      # type: ignore[arg-type]
            )
        ).one()

    except HTTPException:
        session.rollback()
        raise
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The booking could not be created",
        ) from None
    except Exception:
        session.rollback()
        raise


def assign_courier(
    session: Session,
    order_id: int,
    data: AssignCourier,
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
                detail="A courier cannot be assigned to a completed order",
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

        courier = session.get(User, data.courier_id)
        if courier is None or courier.role != Role.COURIER:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="The selected user is not a courier",
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
        if pickup is None:
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
            slot = session.exec(
                select(Slot)
                .where(Slot.id == pickup.slot_id)
                .with_for_update()
            ).first()
            if slot is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Pickup slot no longer exists",
                )
            slot.booked_count = max(0, slot.booked_count - 1)
            session.add(slot)

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
            .order_by(StatusHistory.created_at, StatusHistory.id)    # type: ignore[arg-type]
        ).all()
    )


def can_view_order(order: Order, pickup: Pickup, viewer: User) -> bool:
    if viewer.role == Role.OPS_MANAGER:
        return True
    if viewer.role == Role.CUSTOMER:
        return order.customer_id == viewer.id
    return viewer.role == Role.COURIER and pickup.courier_id == viewer.id


def _authorize_status_change(
    order: Order,
    pickup: Pickup,
    actor: User,
    next_status: OrderStatus,
) -> None:
    if actor.role == Role.OPS_MANAGER:
        return
    if actor.role == Role.CUSTOMER:
        if (
            order.customer_id == actor.id
            and order.status == OrderStatus.BOOKED
            and next_status == OrderStatus.CANCELLED
        ):
            return
    elif actor.role == Role.COURIER:
        courier_stages = {
            OrderStatus.COLLECTED,
            OrderStatus.OUT_FOR_DELIVERY,
            OrderStatus.DELIVERED,
        }
        if pickup.courier_id == actor.id and next_status in courier_stages:
            return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have permission to make this status change",
    )
