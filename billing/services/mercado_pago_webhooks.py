from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from datetime import timedelta

from billing.models import (
    PROVIDER_MERCADO_PAGO,
    BillingPlan,
    Payment,
    Subscription,
)
from billing.services.mercado_pago import get_order


class MercadoPagoWebhookProcessingError(Exception):
    """Raised when a Mercado Pago order cannot be safely processed."""


def process_mercado_pago_order(order_id):
    """Process a credited one-time order and activate its subscription."""
    if not order_id:
        raise MercadoPagoWebhookProcessingError(
            "The webhook does not contain an order ID."
        )

    order = get_order(order_id)

    if str(order.get("id")) != str(order_id):
        raise MercadoPagoWebhookProcessingError(
            "The returned order ID does not match the notification."
        )

    external_reference = order.get("external_reference")
    if not external_reference:
        raise MercadoPagoWebhookProcessingError(
            "The order has no external reference."
        )

    with transaction.atomic():
        try:
            subscription = (
                Subscription.objects.select_for_update(of=("self",))
                .select_related("billing_plan")
                .get(pk=external_reference)
            )
        except (Subscription.DoesNotExist, ValueError) as exc:
            raise MercadoPagoWebhookProcessingError(
                "The order does not reference a valid subscription."
            ) from exc

        if subscription.provider != PROVIDER_MERCADO_PAGO:
            raise MercadoPagoWebhookProcessingError(
                "The subscription uses a different payment provider."
            )

        if str(subscription.provider_checkout_id) != str(order_id):
            raise MercadoPagoWebhookProcessingError(
                "The order does not match the subscription checkout."
            )

        if (
            subscription.billing_plan is None
            or subscription.billing_plan.billing_type
            != BillingPlan.TYPE_ONE_TIME
        ):
            raise MercadoPagoWebhookProcessingError(
                "The subscription is not a one-time plan."
            )

        if subscription.status not in (
            Subscription.STATUS_PENDING,
            Subscription.STATUS_ACTIVE,
        ):
            raise MercadoPagoWebhookProcessingError(
                "The subscription is not eligible for activation."
            )

        if (
            order.get("status") != "processed"
            or order.get("status_detail") != "accredited"
        ):
            return False

        try:
            order_amount = Decimal(str(order["total_amount"]))
        except (KeyError, InvalidOperation, TypeError) as exc:
            raise MercadoPagoWebhookProcessingError(
                "The order has an invalid total amount."
            ) from exc

        if order_amount != subscription.amount:
            raise MercadoPagoWebhookProcessingError(
                "The order amount does not match the subscription amount."
            )

        transactions = order.get("transactions") or {}
        payments = transactions.get("payments") or []

        credited_payments = [
            payment
            for payment in payments
            if (
                payment.get("status") == "processed"
                and payment.get("status_detail") == "accredited"
            )
        ]

        if len(credited_payments) != 1:
            raise MercadoPagoWebhookProcessingError(
                "The order must contain exactly one credited payment."
            )

        provider_payment = credited_payments[0]
        provider_payment_id = provider_payment.get("id")

        if not provider_payment_id:
            raise MercadoPagoWebhookProcessingError(
                "The credited payment has no ID."
            )

        try:
            payment_amount = Decimal(
                str(
                    provider_payment.get("paid_amount")
                    or provider_payment["amount"]
                )
            )
        except (KeyError, InvalidOperation, TypeError) as exc:
            raise MercadoPagoWebhookProcessingError(
                "The credited payment has an invalid amount."
            ) from exc

        if payment_amount != subscription.amount:
            raise MercadoPagoWebhookProcessingError(
                "The payment amount does not match the subscription amount."
            )

        payment, created = Payment.objects.get_or_create(
            provider=PROVIDER_MERCADO_PAGO,
            provider_payment_id=str(provider_payment_id),
            defaults={
                "subscription": subscription,
                "amount": payment_amount,
                "status": Payment.STATUS_CONFIRMED,
                "paid_at": timezone.now(),
            },
        )

        if (
            payment.subscription_id != subscription.id
            or payment.amount != payment_amount
        ):
            raise MercadoPagoWebhookProcessingError(
                "The payment ID is already associated with another record."
            )

        if payment.status not in (
            Payment.STATUS_CONFIRMED,
            Payment.STATUS_RECEIVED,
        ):
            payment.status = Payment.STATUS_CONFIRMED
            payment.paid_at = payment.paid_at or timezone.now()
            payment.save(update_fields=["status", "paid_at", "updated_at"])

        if subscription.status == Subscription.STATUS_PENDING:
            started_at = timezone.now()
            subscription.status = Subscription.STATUS_ACTIVE
            subscription.started_at = started_at
            subscription.expires_at = (
                started_at
                + timedelta(
                    days=subscription.billing_plan.access_days
                )
            )
            subscription.save(
                update_fields=[
                    "status",
                    "started_at",
                    "expires_at",
                    "updated_at",
                ]
            )

        return created
