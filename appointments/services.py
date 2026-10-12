import logging
import re

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def normalize_brazilian_phone(number: str) -> str:
    """Normalize a Brazilian phone number to Evolution API format."""
    digits = re.sub(r'\D', '', number)

    if digits.startswith('55') and len(digits) in (12, 13):
        digits = digits[2:]

    if len(digits) not in (10, 11):
        raise ValueError('Invalid Brazilian phone number.')

    area_code = int(digits[:2])
    subscriber = digits[2:]

    if not 11 <= area_code <= 99:
        raise ValueError('Invalid Brazilian area code.')

    if len(subscriber) == 9 and subscriber[0] != '9':
        raise ValueError('Invalid Brazilian mobile number.')

    return f'55{digits}'


def send_whatsapp_message(number: str, text: str) -> bool:
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
