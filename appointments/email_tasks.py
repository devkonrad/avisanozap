import logging

from celery import shared_task
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from django.contrib.auth import get_user_model
from core.emailing import send_templated_email
from appointments.models import ProfessionalProfile
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def send_welcome_email(profile_id):
    with transaction.atomic():
        try:
            profile = (
                ProfessionalProfile.objects
                .select_for_update()
                .select_related("user")
                .get(pk=profile_id)
            )
        except ProfessionalProfile.DoesNotExist:
            logger.warning(
                "Profile %s not found; welcome email skipped.",
                profile_id,
            )
            return

        if profile.welcome_email_sent_at:
            return

        user = profile.user

        if not user.email:
            logger.warning(
                "User %s has no email; welcome email skipped.",
                user.pk,
            )
            return

        dashboard_url = (
            f"{settings.SITE_URL}"
            f"{reverse('appointments_dashboard')}"
        )

        send_templated_email(
            subject="Bem-vindo ao AvisanoZap!",
            recipient=user.email,
            template_name="welcome",
            context={
                "name": user.first_name or user.username,
                "dashboard_url": dashboard_url,
            },
        )

        profile.welcome_email_sent_at = timezone.now()
        profile.save(update_fields=["welcome_email_sent_at"])


@shared_task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def send_password_reset_email(user_id, uidb64, token):
    User = get_user_model()

    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return

    if not user.email:
        return

    reset_path = reverse(
        "accounts:password_reset_confirm",
        kwargs={
            "uidb64": uidb64,
            "token": token,
        },
    )

    send_templated_email(
        subject="Redefinição de senha - AvisanoZap",
        recipient=user.email,
        template_name="password_reset",
        context={
            "name": user.first_name or user.username,
            "reset_url": f"{settings.SITE_URL}{reset_path}",
        },
    )
