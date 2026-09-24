from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.models.orders import Order, OrderStatus
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.pickups import Pickup
from app.models.user import Role, User
from app.schemas.payment import PaymentInitialization
from app.services.paystack import initialize_paystack_payment
from app.utils.config import settings


def _payment_for_order(session: Session, order_id: int) -> Payment | None:
    return session.exec(
        select(Payment)
        .join(Pickup, Payment.pickup_id == Pickup.id)
        .where(Pickup.order_id == order_id)
    ).first()


def get_order_payment(
    session: Session,
    order_id: int,
    viewer: User,
) -> Payment:
    order = session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    payment = _payment_for_order(session, order_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")

    pickup = session.get(Pickup, payment.pickup_id)
    if not _can_view_payment(order, pickup, viewer):
        raise HTTPException(status_code=403, detail="Access denied")
    return payment


def initialize_online_payment(
    session: Session,
    order_id: int,
    customer: User,
) -> PaymentInitialization:
    try:
        order = session.exec(
            select(Order).where(Order.id == order_id).with_for_update()
        ).first()
        if order is None:
            raise HTTPException(status_code=404, detail="Order not found")
        if order.customer_id != customer.id:
            raise HTTPException(status_code=403, detail="Please select your order ID")
        if order.status == OrderStatus.CANCELLED:
            raise HTTPException(status_code=409, detail="A cancelled order cannot be paid")

        pickup = session.exec(
            select(Pickup).where(Pickup.order_id == order_id).with_for_update()
        ).first()
        if pickup is None or pickup.id is None:
            raise HTTPException(status_code=409, detail="Order has no pickup booking")

        payment = session.exec(
            select(Payment).where(Payment.pickup_id == pickup.id).with_for_update()
        ).first()
        if payment is not None:
            if payment.status == PaymentStatus.PAID:
                raise HTTPException(status_code=409, detail="Order is already paid")
            if payment.authorization_url and payment.access_code:
                return PaymentInitialization(
                    payment=payment,
                    authorization_url=payment.authorization_url,
                    access_code=payment.access_code,
                )

        reference = f"ww-{order_id}-{uuid4().hex}"
        provider_response = initialize_paystack_payment(
            email=str(customer.email),
            amount=order.total,
            reference=reference,
        )
        provider_data = provider_response.get("data")
        if (
            provider_response.get("status") is not True
            or not isinstance(provider_data, dict)
            or not isinstance(provider_data.get("authorization_url"), str)
            or not isinstance(provider_data.get("access_code"), str)
            or provider_data.get("reference") != reference
        ):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Paystack returned an unexpected response",
            )

        if payment is None:
            payment = Payment(
                pickup_id=pickup.id,
                amount=order.total,
                reference=reference,
            )
        else:
            payment.amount = order.total
            payment.reference = reference
            payment.status = PaymentStatus.PENDING

        payment.method = PaymentMethod.ONLINE
        payment.currency = settings.PAYSTACK_CURRENCY.upper()
        payment.authorization_url = provider_data["authorization_url"]
        payment.access_code = provider_data["access_code"]
        session.add(payment)
        session.commit()
        session.refresh(payment)
        return PaymentInitialization(
            payment=payment,
            authorization_url=payment.authorization_url,
            access_code=payment.access_code,
        )
    except HTTPException:
        session.rollback()
        raise
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="Payment already exists") from None
    except Exception:
        session.rollback()
        raise


def record_cash_payment(
    session: Session,
    order_id: int,
    courier: User,
) -> Payment:
    try:
        order = session.get(Order, order_id)
        if order is None:
            raise HTTPException(status_code=404, detail="Order not found")

        pickup = session.exec(
            select(Pickup).where(Pickup.order_id == order_id).with_for_update()
        ).first()
        if pickup is None or pickup.id is None:
            raise HTTPException(status_code=409, detail="Order has no pickup booking")
        if courier.role != Role.COURIER or pickup.courier_id != courier.id:
            raise HTTPException(
                status_code=403,
                detail="Only the assigned courier can record cash payment",
            )

        payment = session.exec(
            select(Payment).where(Payment.pickup_id == pickup.id).with_for_update()
        ).first()
        if payment is not None:
            if payment.status == PaymentStatus.PAID:
                return payment
            raise HTTPException(
                status_code=409,
                detail="An online payment is already pending for this order",
            )

        payment = Payment(
            pickup_id=pickup.id,
            amount=order.total,
            status=PaymentStatus.PAID,
            method=PaymentMethod.CASH,
            currency=settings.PAYSTACK_CURRENCY.upper(),
            reference=f"cash-{order_id}-{uuid4().hex}",
            paid_at=datetime.now(timezone.utc),
        )
        session.add(payment)
        session.commit()
        session.refresh(payment)
        return payment
    except HTTPException:
        session.rollback()
        raise
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="Payment already exists") from None


def _can_view_payment(
    order: Order,
    pickup: Pickup | None,
    viewer: User,
) -> bool:
    if viewer.role == Role.OPS_MANAGER:
        return True
    if viewer.role == Role.CUSTOMER:
        return order.customer_id == viewer.id
    return pickup is not None and pickup.courier_id == viewer.id
