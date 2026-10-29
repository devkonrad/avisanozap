
import logging
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .models import (
    Appointment,
    ReminderTestConfiguration,
    WhatsAppReminder,
)
from .services import send_whatsapp_message

logger = logging.getLogger(__name__)


@shared_task
def send_appointment_notifications(appointment_id):
    """Notify the client and professional about a new appointment."""
    try:
        appointment = Appointment.objects.select_related(
            "service",
            "professional",
            "professional__user",
        ).get(id=appointment_id)
    except Appointment.DoesNotExist:
        logger.warning(
            "Appointment %s not found; notifications skipped.",
            appointment_id,
        )
        return

    if appointment.status not in (
        Appointment.STATUS_CONFIRMED,
        Appointment.STATUS_PENDING_CONFIRMATION,
    ):
        logger.info(
            "Appointment %s has status %s; notifications skipped.",
            appointment_id,
            appointment.status,
        )
        return

    service_name = (
        appointment.service.name if appointment.service else "Atendimento"
    )
    professional = appointment.professional
    professional_name = (
        professional.user.get_full_name()
        or professional.user.username
        if professional.user_id
        else professional.slug
    )
    date_formatted = timezone.localtime(
        appointment.start_datetime
    ).strftime("%d/%m/%Y às %H:%M")

    if appointment.status == Appointment.STATUS_PENDING_CONFIRMATION:
        client_message = (
            f"Olá, {appointment.client_name}! 👋\n\n"
            f"Seu agendamento de *{service_name}* com "
            f"*{professional_name}* está reservado para "
            f"*{date_formatted}*.\n\n"
            "Para confirmar, responda *SIM*.\n"
            "Para cancelar, responda *NÃO*.\n\n"
            "Aguardamos sua resposta!"
        )

        send_whatsapp_message(
            number=appointment.client_whatsapp,
            text=client_message,
        )

        professional_message = (
            "📅 *Novo agendamento aguardando confirmação!*\n\n"
            f"👤 *Cliente:* {appointment.client_name}\n"
            f"🛠 *Serviço:* {service_name}\n"
            f"⏰ *Data/Hora:* {date_formatted}\n\n"
            "Aguardando resposta do cliente."
        )
    else:
        send_whatsapp_message(
            number=appointment.client_whatsapp,
            text=(
                f"Olá, {appointment.client_name}! 👋\n\n"
                f"Seu agendamento de *{service_name}* com "
                f"*{professional_name}* foi confirmado para "
                f"*{date_formatted}*.\n\n"
                "Obrigado por usar o AvisanoZap."
            ),
        )

        professional_message = (
            "✅ *Agendamento confirmado!*\n\n"
            f"👤 *Cliente:* {appointment.client_name}\n"
            f"🛠 *Serviço:* {service_name}\n"
            f"⏰ *Data/Hora:* {date_formatted}"
        )

    if professional.whatsapp_number:
        success = send_whatsapp_message(
            number=professional.whatsapp_number,
            text=professional_message,
        )
        if not success:
            logger.error(
                "Failed to notify professional for appointment %s.",
                appointment_id,
            )


@shared_task
def process_pending_reminders():
    """Send reminders that are due."""
    now = timezone.now()
    pending_reminders = (
        WhatsAppReminder.objects.filter(
            status="PENDING",
            scheduled_for__lte=now,
            appointment__status=Appointment.STATUS_CONFIRMED,
        )
        .select_related(
            "appointment",
            "appointment__service",
            "appointment__professional",
        )
    )

    for reminder in pending_reminders:
        appointment = reminder.appointment

        try:
            service_name = (
                appointment.service.name
                if appointment.service
                else "Atendimento"
            )
            date_formatted = timezone.localtime(
                appointment.start_datetime
            ).strftime("%d/%m/%Y às %H:%M")

            message = (
                f"Olá, {appointment.client_name}! 👋\n\n"
                f"Passando para lembrar do seu agendamento de "
                f"*{service_name}* para *{date_formatted}*.\n\n"
                "Caso precise reagendar ou desmarcar, entre em "
                "contato conosco."
            )

            success = send_whatsapp_message(
                number=appointment.client_whatsapp,
                text=message,
            )

            if success:
                reminder.status = "SENT"
                reminder.sent_at = timezone.now()
            else:
                reminder.status = "FAILED"

            reminder.save(update_fields=["status", "sent_at"])

        except Exception:
            logger.exception(
                "Failed to process reminder %s.",
                reminder.id,
            )


@shared_task
def send_reminder_test_message():
    """Send a periodic WhatsApp test message when enabled and due."""
    with transaction.atomic():
        try:
            configuration = (
                ReminderTestConfiguration.objects.select_for_update().get(
                    pk=1
                )
            )
        except ReminderTestConfiguration.DoesNotExist:
            return "Test configuration not found."

        if not configuration.enabled:
            return "Periodic reminder test is disabled."

        destination_phone = configuration.destination_phone.strip()
        if not destination_phone:
            configuration.last_result = "Falha: WhatsApp de destino não configurado."
            configuration.save(update_fields=["last_result"])
            return configuration.last_result

        now = timezone.now()
        next_attempt_at = (
            configuration.last_attempt_at
            + timedelta(minutes=configuration.interval_minutes)
            if configuration.last_attempt_at
            else None
        )

        if next_attempt_at and now < next_attempt_at:
            return "Periodic reminder test is not due yet."

        configuration.last_attempt_at = now
        configuration.last_result = "Envio em andamento."
        configuration.save(
            update_fields=["last_attempt_at", "last_result"]
        )

        interval_minutes = configuration.interval_minutes

    message = (
        "🧪 *Teste de lembretes do AvisanoZap*\n\n"
        "Esta é uma mensagem automática para verificar o envio de "
        "WhatsApp pelo sistema.\n\n"
        f"Intervalo configurado: {interval_minutes} minuto(s).\n"
        f"Horário do teste: "
        f"{timezone.localtime(now).strftime('%d/%m/%Y às %H:%M:%S')}."
    )

    try:
        success = send_whatsapp_message(
            number=destination_phone,
            text=message,
        )
    except Exception:
        logger.exception("Unexpected error while sending test reminder.")
        success = False

    with transaction.atomic():
        configuration = ReminderTestConfiguration.objects.get(pk=1)

        if success:
            configuration.last_success_at = timezone.now()
            configuration.last_result = "Mensagem de teste enviada com sucesso."
        else:
            configuration.last_result = (
                "Falha no envio da mensagem de teste. "
                "Verifique os logs da aplicação e a Evolution API."
            )

        configuration.save(
            update_fields=["last_success_at", "last_result"]
        )

    if success:
        logger.info("Periodic WhatsApp reminder test sent successfully.")
        return "Test message sent successfully."

    logger.error("Periodic WhatsApp reminder test failed.")
    return "Test message failed."
