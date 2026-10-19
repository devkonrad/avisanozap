import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from appointments.models import ProfessionalProfile
from core.emailing import send_templated_email
from billing.models import (
    PROVIDER_MERCADO_PAGO,
    Payment,
)

logger = logging.getLogger(__name__)


def format_brl(amount):
    formatted = f"{amount:,.2f}"
    formatted = formatted.replace(",", "X")
    formatted = formatted.replace(".", ",")
    formatted = formatted.replace("X", ".")
    return f"R$ {formatted}"


@shared_task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def send_payment_receipt(payment_id):
    with transaction.atomic():
        try:
            payment = (
                Payment.objects
                .select_for_update(of=("self",))
                .select_related(
                    "subscription",
                    "subscription__professional",
                    "subscription__billing_plan",
                )
                .get(pk=payment_id)
            )
        except Payment.DoesNotExist:
            logger.warning(
                "Payment %s not found; receipt skipped.",
                payment_id,
            )
            return

        if payment.provider != PROVIDER_MERCADO_PAGO:
            return

        if payment.status not in (
            Payment.STATUS_CONFIRMED,
            Payment.STATUS_RECEIVED,
        ):
            return

        if payment.receipt_email_sent_at:
            return

        subscription = payment.subscription
        professional = subscription.professional

        if professional:
            recipient = professional.user.email
            name = (
                professional.user.first_name
                or professional.user.username
            )
        else:
            recipient = subscription.customer_email
            name = "Cliente"

        if not recipient:
            logger.warning(
                "Payment %s has no recipient email.",
                payment.pk,
            )
            return

        plan_name = (
            subscription.billing_plan.name
            if subscription.billing_plan
            else subscription.get_plan_display()
        )

        send_templated_email(
            subject="Confirmação de pagamento - AvisanoZap",
            recipient=recipient,
            template_name="purchase_receipt",
            context={
                "name": name,
                "amount": format_brl(payment.amount),
                "paid_at": timezone.localtime(
                    payment.paid_at or timezone.now()
                ).strftime("%d/%m/%Y às %H:%M"),
                "plan_name": plan_name,
                "expires_at": (
                    timezone.localtime(
                        subscription.expires_at
                    ).strftime("%d/%m/%Y")
                    if subscription.expires_at
                    else None
                ),
            },
        )

        payment.receipt_email_sent_at = timezone.now()
        payment.save(
            update_fields=["receipt_email_sent_at"],
        )
