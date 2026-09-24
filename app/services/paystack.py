import hashlib
import hmac
from typing import Any

import httpx
from fastapi import HTTPException, status

from app.utils.config import settings


def initialize_paystack_payment(
    email: str,
    amount: int,
    reference: str,
) -> dict[str, Any]:
    
    """Ask Paystack to create a checkout session."""
    
    payload: dict[str, Any] = {
        "email": email,
        "amount": amount,  # WashWagon stores amounts in kobo already.
        "currency": settings.PAYSTACK_CURRENCY.upper(),
        "reference": reference,
    }

    if settings.PAYSTACK_CALLBACK_URL:
        payload["callback_url"] = settings.PAYSTACK_CALLBACK_URL

    try:
        response = httpx.post(
            f"{settings.PAYSTACK_BASE_URL.rstrip('/')}"
            "/transaction/initialize",
            headers={
                "Authorization": (
                    f"Bearer {settings.PAYSTACK_SECRET_KEY.get_secret_value()}"
                ),
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30.0,
        )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise ValueError("Unexpected Paystack response")
        return body
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not initialize payment with Paystack",
        ) from exc


def verify_paystack_signature(
    raw_body: bytes,
    signature: str | None,
) -> bool:
    """Confirm that a webhook was signed with our Paystack secret."""
    if not signature:
        return False

    expected = hmac.new(
        settings.PAYSTACK_SECRET_KEY.get_secret_value().encode(),
        raw_body,
        hashlib.sha512,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
