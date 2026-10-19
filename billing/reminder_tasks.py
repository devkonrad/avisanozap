import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from core.emailing import send_templated_email
from billing.models import (
    PROVIDER_MERCADO_PAGO,
    Subscription,
)

logger = logging.getLogger(__name__)

REMINDER_DAYS = 3


@shared_task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def send_subscription_expiration_reminder(subscription_id):
    with transaction.atomic():
        try:
            subscription = (
                Subscription.objects
                .select_for_update()
                .select_related(
                    "professional",
                    "professional__user",
                    "billing_plan",
                )
                .get(pk=subscription_id)
            )
        except Subscription.DoesNotExist:
            logger.warning(
                "Subscription %s not found; reminder skipped.",
                subscription_id,
            )
            return

        now = timezone.now()

        if subscription.provider != PROVIDER_MERCADO_PAGO:
            return

        if subscription.status != Subscription.STATUS_ACTIVE:
            return

        if subscription.expiration_reminder_sent_at:
            return

        if not subscription.expires_at:
            return

        if not now < subscription.expires_at <= (
            now + timedelta(days=REMINDER_DAYS)
        ):
            return

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
                "Subscription %s has no email recipient.",
                subscription.pk,
            )
            return

        renewal_url = (
            f"{settings.SITE_URL}/#planos"
        )

        send_templated_email(
            subject="Sua assinatura AvisanoZap está perto do vencimento",
            recipient=recipient,
            template_name="subscription_expiring",
            context={
                "name": name,
                "expires_at": timezone.localtime(
                    subscription.expires_at
                ).strftime("%d/%m/%Y"),
                "renewal_url": renewal_url,
            },
        )

        subscription.expiration_reminder_sent_at = timezone.now()
        subscription.save(
            update_fields=["expiration_reminder_sent_at"],
        )


@shared_task
def find_subscriptions_near_expiration():
    now = timezone.now()
    cutoff = now + timedelta(days=REMINDER_DAYS)

    subscription_ids = Subscription.objects.filter(
        provider=PROVIDER_MERCADO_PAGO,
        status=Subscription.STATUS_ACTIVE,
        expires_at__gt=now,
        expires_at__lte=cutoff,
        expiration_reminder_sent_at__isnull=True,
    ).values_list("pk", flat=True)

    for subscription_id in subscription_ids.iterator():
        send_subscription_expiration_reminder.delay(
            str(subscription_id)
        )
