import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.models.payment import Payment, PaymentStatus
from app.models.payment_event import PaymentEvent
from app.schemas.payment import WebhookResponse
from app.services.paystack import verify_paystack_signature


def process_paystack_webhook(
    session: Session,
    raw_body: bytes,
    signature: str | None,
) -> WebhookResponse:
    """Validate and process one Paystack webhook event."""
    if not verify_paystack_signature(raw_body, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = _parse_webhook(raw_body)
    event_name = payload["event"]
    data = payload["data"]
    event_id = _event_id(event_name, data, raw_body)

    if _event_was_processed(session, event_id):
        return WebhookResponse(duplicate=True)

    try:
        if event_name == "charge.success":
            _mark_payment_paid(session, data)

        session.add(PaymentEvent(event_id=event_id))
        session.commit()
        return WebhookResponse()
    except HTTPException:
        session.rollback()
        raise
    except IntegrityError:
        session.rollback()
        return WebhookResponse(duplicate=True)


def _parse_webhook(raw_body: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="Invalid webhook payload") from None

    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("event"), str)
        or not isinstance(payload.get("data"), dict)
    ):
        raise HTTPException(status_code=400, detail="Invalid webhook payload")
    return payload


def _event_id(
    event_name: str,
    data: dict[str, Any],
    raw_body: bytes,
) -> str:
    provider_id = data.get("id") or data.get("reference")
    if provider_id is None:
        provider_id = hashlib.sha256(raw_body).hexdigest()
    return f"{event_name}:{provider_id}"


def _event_was_processed(session: Session, event_id: str) -> bool:
    event = session.exec(
        select(PaymentEvent).where(PaymentEvent.event_id == event_id)
    ).first()
    return event is not None


def _mark_payment_paid(
    session: Session,
    data: dict[str, Any],
) -> None:
    reference = data.get("reference")
    if not isinstance(reference, str):
        return

    payment = session.exec(
        select(Payment)
        .where(Payment.reference == reference)
        .with_for_update()
    ).first()
    if payment is None:
        return

    currency = data.get("currency")
    if (
        data.get("status") != "success"
        or data.get("amount") != payment.amount
        or not isinstance(currency, str)
        or currency.upper() != payment.currency.upper()
    ):
        raise HTTPException(
            status_code=422,
            detail="Payment details do not match the order",
        )

    if payment.status != PaymentStatus.PAID:
        payment.status = PaymentStatus.PAID
        payment.paid_at = datetime.now(timezone.utc)
        session.add(payment)
