import logging
import re

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

from urllib.parse import urlencode
from django.urls import reverse

def normalize_brazilian_phone(number: str) -> str:
    """Normalize a Brazilian mobile number to the full WhatsApp format."""
    digits = re.sub(r"\D", "", number)

    if digits.startswith("55") and len(digits) in (12, 13):
        digits = digits[2:]

    if len(digits) not in (10, 11):
        raise ValueError("Invalid Brazilian phone number.")

    area_code = int(digits[:2])
    subscriber = digits[2:]

    if not 11 <= area_code <= 99:
        raise ValueError("Invalid Brazilian area code.")

    if len(subscriber) == 8:
        subscriber = f"9{subscriber}"
    elif len(subscriber) == 9 and subscriber[0] != "9":
        raise ValueError("Invalid Brazilian mobile number.")

    return f"55{digits[:2]}{subscriber}"


def send_whatsapp_message(number: str, text: str) -> bool:
    number = normalize_brazilian_phone(number)

    """Send a text message through the Evolution API."""
    url = (
        f'{settings.EVOLUTION_API_URL.rstrip("/")}'
        f'/message/sendText/{settings.EVOLUTION_INSTANCE_NAME}'
    )
    headers = {
        'apikey': settings.EVOLUTION_API_KEY,
        'Content-Type': 'application/json',
    }
    payload = {
        'number': number,
        'text': text,
    }

    try:
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=10,
        )
    except requests.RequestException:
        logger.exception(
            'Evolution API request failed for number %s.',
            number,
        )
        return False

    if not response.ok:
        logger.error(
            'Evolution API returned HTTP %s for number %s: %s',
            response.status_code,
            number,
            response.text[:1000],
        )
        return False

    logger.info(
        'WhatsApp message sent successfully to %s.',
        number,
    )
    return True


def send_whatsapp_poll(number: str, question: str, options: list[str]) -> bool:
    number = normalize_brazilian_phone(number)
    
    """Send a single-choice poll through the Evolution API."""
    url = (
        f'{settings.EVOLUTION_API_URL.rstrip("/")}'
        f'/message/sendPoll/{settings.EVOLUTION_INSTANCE_NAME}'
    )
    headers = {
        'apikey': settings.EVOLUTION_API_KEY,
        'Content-Type': 'application/json',
    }
    payload = {
        'number': number,
        'name': question,
        'selectableCount': 1,
        'values': options,
    }

    try:
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=10,
        )
    except requests.RequestException:
        logger.exception(
            'Evolution API poll request failed for number %s.',
            number,
        )
        return False

    if not response.ok:
        logger.error(
            'Evolution API returned HTTP %s when sending poll to %s: %s',
            response.status_code,
            number,
            response.text[:1000],
        )
        return False

    logger.info('WhatsApp poll sent successfully to %s.', number)
    return True



def send_signup_continuation_message(subscription_id) -> bool:
    """Send the signup continuation link for an active subscription."""
    from billing.models import Subscription

    try:
        subscription = Subscription.objects.get(pk=subscription_id)
    except Subscription.DoesNotExist:
        logger.error(
            "Cannot send signup link: subscription %s does not exist.",
            subscription_id,
        )
        return False

    if subscription.status != Subscription.STATUS_ACTIVE:
        logger.warning(
            "Cannot send signup link for inactive subscription %s.",
            subscription_id,
        )
        return False

    if subscription.professional_id:
        logger.info(
            "Signup already completed for subscription %s.",
            subscription_id,
        )
        return False

    if not subscription.customer_whatsapp:
        logger.error(
            "Cannot send signup link: subscription %s has no WhatsApp number.",
            subscription_id,
        )
        return False

    base_url = getattr(settings, "SITE_URL", "").rstrip("/")

    if not base_url:
        hosts = [
            host
            for host in settings.ALLOWED_HOSTS
            if host not in {"*", "localhost", "127.0.0.1", "testserver"}
        ]
        if not hosts:
            logger.error(
                "Cannot send signup link: configure SITE_URL "
                "or a public host in ALLOWED_HOSTS."
            )
            return False

        base_url = f"https://{hosts[0]}"

    query_string = urlencode({"subscription": str(subscription.pk)})
    signup_url = (
        f"{base_url}{reverse('accounts:signup')}?{query_string}"
    )

    message = (
        "Olá! Seu pagamento foi confirmado e seu acesso ao AvisanoZap "
        "está ativo.\n\n"
        "Para concluir seu cadastro e começar a usar a plataforma, "
        "acesse o link abaixo:\n"
        f"{signup_url}\n\n"
        "Use o mesmo e-mail informado na compra."
    )

    try:
        return send_whatsapp_message(
            subscription.customer_whatsapp,
            message,
        )
    except (ValueError, TypeError):
        logger.exception(
            "Could not send signup link for subscription %s.",
            subscription_id,
        )
        return False
