import logging

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from billing.models import GA4Event

logger = logging.getLogger(__name__)

GA4_ENDPOINT = "https://www.google-analytics.com/mp/collect"


def create_ga4_event(
    *,
    event_id,
    event_name,
    client_id,
    session_id="",
    params=None,
):
    """Persist a GA4 event and schedule its delivery."""
    if not client_id:
        logger.info(
            "GA4 event %s skipped because client_id is missing.",
            event_name,
        )
        return None

    event, created = GA4Event.objects.get_or_create(
        event_id=event_id,
        defaults={
            "event_name": event_name,
            "client_id": str(client_id),
            "session_id": str(session_id or ""),
            "params": params or {},
        },
    )

    if created:
        from billing.analytics_tasks import send_ga4_event

        transaction.on_commit(
            lambda: send_ga4_event.delay(str(event.pk))
        )

    return event


def send_event_to_ga4(event):
    """Send one persisted event using the GA4 Measurement Protocol."""
    measurement_id = settings.GA4_MEASUREMENT_ID
    api_secret = settings.GA4_API_SECRET

    if not measurement_id or not api_secret:
        raise RuntimeError("GA4 credentials are not configured.")

    params = dict(event.params)

    if event.session_id:
        try:
            params["session_id"] = int(event.session_id)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid GA4 session_id for event %s.",
                event.event_id,
            )

    params.setdefault("engagement_time_msec", 1)

    response = requests.post(
        GA4_ENDPOINT,
        params={
            "measurement_id": measurement_id,
            "api_secret": api_secret,
        },
        json={
            "client_id": event.client_id,
            "events": [
                {
                    "name": event.event_name,
                    "params": params,
                },
            ],
        },
        timeout=10,
    )
    response.raise_for_status()

    event.sent_at = timezone.now()
    event.last_error = ""
    event.save(update_fields=["sent_at", "last_error"])
