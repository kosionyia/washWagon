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
from app.models.user import User
from app.repositories.prices import get_price_by_garment
from app.schemas.order import CreateOrder


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
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
                selectinload(Order.items),
                selectinload(Order.pickup),
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
