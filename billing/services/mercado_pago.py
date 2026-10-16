import hashlib
import hmac

from decimal import Decimal

import requests
from django.conf import settings


API_BASE_URL = "https://api.mercadopago.com"


class MercadoPagoError(Exception):
    """Raised when a Mercado Pago API request fails."""


def _request(
    method,
    endpoint,
    *,
    payload=None,
    idempotency_key=None,
):
    if not settings.MERCADO_PAGO_ACCESS_TOKEN:
        raise MercadoPagoError(
            "MERCADO_PAGO_ACCESS_TOKEN is not configured."
        )

    headers = {
        "Authorization": (
            f"Bearer {settings.MERCADO_PAGO_ACCESS_TOKEN}"
        ),
        "Content-Type": "application/json",
    }

    if idempotency_key:
        headers["X-Idempotency-Key"] = idempotency_key

    try:
        response = requests.request(
            method,
            f"{API_BASE_URL}{endpoint}",
            headers=headers,
            json=payload,
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        if isinstance(exc, requests.HTTPError) and exc.response is not None:
            error_detail = exc.response.text[:1000]
        else:
            error_detail = str(exc)

        raise MercadoPagoError(
            f"Mercado Pago API request failed: {error_detail}"
        ) from exc

    if not isinstance(data, dict):
        raise MercadoPagoError(
            "Mercado Pago returned an invalid response."
        )

    return data


def get_order(order_id):
    """Retrieve an order from Mercado Pago."""
    if not order_id:
        raise MercadoPagoError("An order ID is required.")

    return _request(
        "GET",
        f"/v1/orders/{order_id}",
    )


def get_payment(payment_id):
    """Retrieve a payment from Mercado Pago."""
    if not payment_id:
        raise MercadoPagoError("A payment ID is required.")

    return _request(
        "GET",
        f"/v1/payments/{payment_id}",
    )


def get_preapproval(preapproval_id):
    """Retrieve a recurring subscription from Mercado Pago."""
    if not preapproval_id:
        raise MercadoPagoError("A subscription ID is required.")

    return _request(
        "GET",
        f"/preapproval/{preapproval_id}",
    )


def create_pix_checkout(subscription, plan, callback_url, payer_email):
    amount = Decimal(subscription.amount).quantize(Decimal("0.01"))
    amount_str = str(amount)

    payload = {
        "type": "online",
        "processing_mode": "automatic",
        "total_amount": amount_str,
        "external_reference": str(subscription.id),
        "description": plan.name,
        "payer": {
            "email": payer_email,
        },
        "transactions": {
            "payments": [
                {
                    "amount": amount_str,
                    "payment_method": {
                        "id": "pix",
                        "type": "bank_transfer",
                    },
                }
            ],
        },
    }

    data = _request(
        "POST",
        "/v1/orders",
        payload=payload,
        idempotency_key=str(subscription.id),
    )

    order_id = data.get("id")
    payments = (
        data.get("transactions", {})
        .get("payments", [])
    )

    payment_method = (
        payments[0].get("payment_method", {})
        if payments
        else {}
    )

    checkout_url = payment_method.get("ticket_url")

    if not order_id or not checkout_url:
        raise MercadoPagoError(
            "Mercado Pago did not return the Pix payment URL."
        )

    return {
        "id": order_id,
        "url": checkout_url,
    }


def create_monthly_checkout(
    subscription,
    plan,
    callback_url,
    payer_email,
):
    amount = Decimal(subscription.amount).quantize(Decimal("0.01"))

    payload = {
        "reason": plan.name,
        "external_reference": str(subscription.id),
        "payer_email": payer_email,
        "back_url": callback_url,
        "auto_recurring": {
            "frequency": 1,
            "frequency_type": "months",
            "transaction_amount": float(amount),
            "currency_id": "BRL",
        },
    }

    data = _request(
        "POST",
        "/preapproval",
        payload=payload,
    )

    subscription_id = data.get("id")
    checkout_url = data.get("init_point")

    if not subscription_id or not checkout_url:
        raise MercadoPagoError(
            "Mercado Pago did not return a subscription ID and checkout URL."
        )

    return {
        "id": subscription_id,
        "url": checkout_url,
        "subscription_id": subscription_id,
    }


def create_checkout(subscription, plan, callback_url, payer_email):
    if not payer_email:
        raise MercadoPagoError(
            "The customer must have an email address to start checkout."
        )

    if plan.billing_type == "MONTHLY":
        return create_monthly_checkout(
            subscription,
            plan,
            callback_url,
            payer_email,
        )

    return create_pix_checkout(
        subscription,
        plan,
        callback_url,
        payer_email,
    )


def validate_webhook_signature(
    signature,
    request_id,
    data_id,
    secret,
):
    """Validate a Mercado Pago webhook signature."""
    if not all((signature, data_id, secret)):
        return False

    signature_parts = {}
    for part in signature.split(","):
        key, separator, value = part.strip().partition("=")
        if separator:
            signature_parts[key] = value

    timestamp = signature_parts.get("ts")
    received_signature = signature_parts.get("v1")

    if not timestamp or not received_signature:
        return False

    manifest_parts = [f"id:{data_id.lower()};"]

    if request_id:
        manifest_parts.append(f"request-id:{request_id};")

    manifest_parts.append(f"ts:{timestamp};")
    manifest = "".join(manifest_parts)

    expected_signature = hmac.new(
        secret.encode("utf-8"),
        manifest.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(
        expected_signature,
        received_signature,
    )
