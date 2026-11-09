
import logging
import unicodedata

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from appointments.services import send_whatsapp_message

from .models import Prospect, ProspectInteraction


logger = logging.getLogger(__name__)


FIRST_CONTACT_MESSAGE = (
    "Olá! Tudo bem? 😊\n\n"
    "Aqui é da equipe AvisanoZap!\n\n"
    "Ajudamos salões de beleza e barbearias a organizar "
    "agendamentos e enviar lembretes automáticos pelo WhatsApp, "
    "facilitando a rotina e ajudando a reduzir faltas.\n\n"
    "Gostaria de conhecer nossa ferramenta e receber uma oferta "
    "especial para o seu estabelecimento?\n\n"
    "👉 Responda SIM para receber mais informações e conhecer "
    "nossa oferta especial.\n\n"
    "Se não tiver interesse, responda NÃO e encerraremos "
    "o contato comercial. Não enviaremos novas mensagens."
)

PROSPECT_OFFER_MESSAGE = (
    "Que ótimo! 😊\n\n"
    "O AvisanoZap ajuda salões de beleza e barbearias a organizar "
    "serviços e agendamentos e enviar lembretes automáticos pelo "
    "WhatsApp, reduzindo faltas e facilitando a rotina.\n\n"
    "Estamos com uma oferta especial: primeiro mês por apenas "
    "R$ 9,99!\n\n"
    "Você pode conhecer os recursos e fazer seu cadastro pelo site:\n"
    "https://avisanozap.com.br/\n\n"
    "Não precisa instalar nada no computador. É simples de usar!"
)


POSITIVE_REPLIES = {
    "sim",
    "quero",
    "tenho interesse",
    "pode enviar",
    "pode mandar",
    "manda",
    "envie",
    "pode",
}

NEGATIVE_REPLIES = {
    "nao",
    "nao tenho interesse",
    "nao quero",
    "sem interesse",
    "pare",
    "parar",
    "remova",
    "remover",
    "cancele",
}


def normalize_reply(text):
    """Normalize an incoming reply for comparison."""
    normalized = unicodedata.normalize("NFKD", text)
    normalized = "".join(
        char for char in normalized
        if not unicodedata.combining(char)
    )
    return " ".join(normalized.lower().strip().strip("!.,;:").split())


def classify_prospect_reply(text):
    """Return positive, negative, or other for an incoming reply."""
    normalized = normalize_reply(text)

    if normalized in POSITIVE_REPLIES:
        return "positive"

    if normalized in NEGATIVE_REPLIES:
        return "negative"

    if normalized.startswith(
        ("sim ", "quero ", "tenho interesse", "pode enviar", "pode mandar")
    ):
        return "positive"

    if normalized.startswith(
        ("nao ", "nao quero", "nao tenho interesse", "sem interesse")
    ):
        return "negative"

    return "other"


def send_prospect_first_contact(prospect, user=None):
    """Send and register the first commercial contact."""
    if not prospect.can_receive_whatsapp:
        return "not_authorized"

    if prospect.phone_status != Prospect.PhoneStatus.WHATSAPP_CONFIRMED:
        return "phone_not_confirmed"

    if prospect.sales_status != Prospect.SalesStatus.NEW:
        return "already_contacted"

    sent = send_whatsapp_message(
        number=prospect.phone_number,
        text=FIRST_CONTACT_MESSAGE,
    )

    if not sent:
        return "failed"

    now = timezone.now()

    prospect.sales_status = Prospect.SalesStatus.FIRST_CONTACT_SENT
    prospect.contacted_at = now
    prospect.save(
        update_fields=[
            "sales_status",
            "contacted_at",
            "updated_at",
        ]
    )

    ProspectInteraction.objects.create(
        prospect=prospect,
        interaction_type=ProspectInteraction.InteractionType.FIRST_CONTACT,
        direction=ProspectInteraction.Direction.OUTBOUND,
        channel=ProspectInteraction.Channel.WHATSAPP,
        message=FIRST_CONTACT_MESSAGE,
        is_automated=True,
        created_by=user,
        occurred_at=now,
    )

    return "sent"


def process_prospect_reply(phone, message, provider_message_id=""):
    """Register a prospect reply and send the offer when appropriate."""
    legacy_phone = (
        f"{phone[:4]}{phone[5:]}" if len(phone) == 13 else phone
    )

    offer_prospect_id = None
    now = timezone.now()

    with transaction.atomic():
        prospect = (
            Prospect.objects.select_for_update()
            .filter(phone_number__in={phone, legacy_phone})
            .order_by("-created_at")
            .first()
        )

        if prospect is None:
            return "not_found"

        if prospect.sales_status != Prospect.SalesStatus.FIRST_CONTACT_SENT:
            return "not_waiting_for_reply"

        if not prospect.can_receive_whatsapp:
            return "not_authorized"

        if provider_message_id and ProspectInteraction.objects.filter(
            provider_message_id=provider_message_id,
        ).exists():
            return "duplicate"

        reply_type = classify_prospect_reply(message)

        interaction_type = {
            "positive": ProspectInteraction.InteractionType.POSITIVE_REPLY,
            "negative": ProspectInteraction.InteractionType.NEGATIVE_REPLY,
            "other": ProspectInteraction.InteractionType.OTHER,
        }[reply_type]

        ProspectInteraction.objects.create(
            prospect=prospect,
            interaction_type=interaction_type,
            direction=ProspectInteraction.Direction.INBOUND,
            channel=ProspectInteraction.Channel.WHATSAPP,
            message=message,
            provider_message_id=provider_message_id,
            is_automated=True,
            occurred_at=now,
        )

        if reply_type == "negative":
            prospect.sales_status = Prospect.SalesStatus.DECLINED
            prospect.opt_out_at = now
            prospect.save(
                update_fields=[
                    "sales_status",
                    "opt_out_at",
                    "updated_at",
                ]
            )
            return "declined"

        if reply_type == "other":
            return "unrecognized"

        prospect.sales_status = Prospect.SalesStatus.INTERESTED
        prospect.save(
            update_fields=["sales_status", "updated_at"]
        )
        offer_prospect_id = prospect.pk

    # Send the offer outside the transaction to avoid holding a database lock.
    try:
        sent = send_whatsapp_message(
            number=phone,
            text=PROSPECT_OFFER_MESSAGE,
        )
    except Exception:
        logger.exception(
            "Unexpected error sending offer to prospect %s.",
            offer_prospect_id,
        )
        return "offer_failed"

    if not sent:
        logger.error(
            "Failed to send offer to prospect %s.",
            offer_prospect_id,
        )
        return "offer_failed"

    with transaction.atomic():
        prospect = Prospect.objects.select_for_update().get(
            pk=offer_prospect_id,
        )

        if prospect.sales_status != Prospect.SalesStatus.INTERESTED:
            return "status_changed"

        now = timezone.now()
        prospect.sales_status = Prospect.SalesStatus.OFFER_SENT
        prospect.save(
            update_fields=["sales_status", "updated_at"]
        )

        ProspectInteraction.objects.create(
            prospect=prospect,
            interaction_type=ProspectInteraction.InteractionType.OFFER_SENT,
            direction=ProspectInteraction.Direction.OUTBOUND,
            channel=ProspectInteraction.Channel.WHATSAPP,
            message=PROSPECT_OFFER_MESSAGE,
            is_automated=True,
            occurred_at=now,
        )

    return "offer_sent"
