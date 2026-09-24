from fastapi import APIRouter, Depends, Header, Request, status
from sqlmodel import Session

from app.dependencies import get_current_user, require_role
from app.models.user import Role, User
from app.schemas.payment import PaymentInitialization, PaymentOut, WebhookResponse
from app.services.payment_webhooks import process_paystack_webhook
from app.services.payments import (
    get_order_payment,
    initialize_online_payment,
    record_cash_payment,
)
from app.utils.database import get_session


router = APIRouter(tags=["Payments"])


@router.post(
    "/payments/orders/{order_id}/initialize",
    response_model=PaymentInitialization,
    status_code=status.HTTP_201_CREATED,
)
def initialize_payment(
    order_id: int,
    session: Session = Depends(get_session),
    customer: User = Depends(require_role(Role.CUSTOMER)),
):
    return initialize_online_payment(session, order_id, customer)


@router.get(
    "/payments/orders/{order_id}",
    response_model=PaymentOut,
)
def read_payment(
    order_id: int,
    session: Session = Depends(get_session),
    viewer: User = Depends(get_current_user),
):
    return get_order_payment(session, order_id, viewer)


@router.post(
    "/payments/orders/{order_id}/cash",
    response_model=PaymentOut,
)
def collect_cash_payment(
    order_id: int,
    session: Session = Depends(get_session),
    courier: User = Depends(require_role(Role.COURIER)),
):
    return record_cash_payment(session, order_id, courier)


@router.post(
    "/webhooks/payment",
    response_model=WebhookResponse,
)
async def paystack_webhook(
    request: Request,
    x_paystack_signature: str | None = Header(default=None),
    session: Session = Depends(get_session),
):
    raw_body = await request.body()
    return process_paystack_webhook(session, raw_body, x_paystack_signature)
