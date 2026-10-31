import logging

from celery import shared_task
from django.db import transaction

from billing.analytics import send_event_to_ga4
from billing.models import GA4Event

logger = logging.getLogger(__name__)


@shared_task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def send_ga4_event(event_id):
    """Deliver a pending GA4 event."""
    with transaction.atomic():
        try:
            event = (
                GA4Event.objects
                .select_for_update()
                .get(pk=event_id)
            )
        except GA4Event.DoesNotExist:
            logger.warning("GA4 event %s not found.", event_id)
            return

        if event.sent_at:
            return

        event.attempts += 1
        event.save(update_fields=["attempts"])

        send_event_to_ga4(event)
