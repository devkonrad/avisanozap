
import requests
from django.conf import settings


class AsaasError(Exception):
    """Raised when the Asaas API request fails."""


def create_checkout(subscription, plan, callback_url):
    if not settings.ASAAS_API_KEY:
        raise AsaasError("ASAAS_API_KEY is not configured.")

    is_recurring = plan.billing_type == "MONTHLY"

    payload = {
        "billingTypes": ["CREDIT_CARD"] if is_recurring else ["PIX"],
        "chargeTypes": ["RECURRENT"] if is_recurring else ["DETACHED"],
        "minutesToExpire": 60,
        "externalReference": str(subscription.id),
        "callback": {
            "successUrl": callback_url,
            "cancelUrl": callback_url,
            "expiredUrl": callback_url,
        },
        "items": [
            {
                "name": plan.name,
                "description": plan.description or plan.name,
                "quantity": 1,
                "value": float(subscription.amount),
            }
        ],
    }

    if is_recurring:
        from datetime import timedelta
        from django.utils import timezone

        payload["subscription"] = {
            "cycle": "MONTHLY",
            "nextDueDate": (
                timezone.localdate() + timedelta(days=1)
            ).isoformat(),
        }

    try:
        response = requests.post(
            f"{settings.ASAAS_BASE_URL}/checkouts",
            headers={
                "access_token": settings.ASAAS_API_KEY,
                "Content-Type": "application/json",
            },
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

        raise AsaasError(
            f"Could not create the Asaas checkout: {error_detail}"
        ) from exc

    checkout_id = data.get("id")
    if not checkout_id:
        raise AsaasError("Asaas did not return a checkout ID.")

    return {
        "id": checkout_id,
        "url": (
            "https://asaas.com/checkoutSession/show"
            f"?id={checkout_id}"
        ),
    }
