from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.models.order_item import OrderItem
from app.models.orders import Order, OrderStatus
from app.models.pickups import Pickup
from app.models.slots import Slot
from app.models.status_history import StatusHistory
from app.models.user import User
from app.repositories.prices import get_price_by_garment
from app.schemas.booking import PickupCreate


def create_pickup(
    session: Session,
    data: PickupCreate,
    customer: User,
) -> Pickup:

    try:
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

        for item in data.items:
            price = get_price_by_garment(
                session,
                item.garment,
            )

            if price is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"No price found for {item.garment.value}",
                )

            total += price.unit_price * item.quantity
            priced_items.append((item, price))

        order = Order(
            customer_id=customer.id,
            total=total,
            status=OrderStatus.BOOKED,
        )
        session.add(order)
        session.flush()

        pickup = Pickup(
            order_id=order.id,
            slot_id=slot.id,
            courier_id=None,
        )
        session.add(pickup)
        session.flush()

        for item, price in priced_items:
            session.add(
                OrderItem(
                    order_id=order.id,
                    price_list_id=price.id,
                    garment=item.garment,
                    quantity=item.quantity,
                    unit_price=price.unit_price,
                )
            )

        session.add(
            StatusHistory(
                pickup_id=pickup.id,
                stage=OrderStatus.BOOKED,
                actor_id=customer.id,
            )
        )

        slot.booked_count += 1
        session.add(slot)
        session.commit()
        session.refresh(pickup)

        return pickup

    except HTTPException:
        session.rollback()
        raise

    except Exception:
        session.rollback()
        raise
