
import logging

from celery import shared_task
from django.utils import timezone

from .models import Appointment, WhatsAppReminder
from .services import send_whatsapp_message

logger = logging.getLogger(__name__)


@shared_task
def send_appointment_notifications(appointment_id):
    """Notify the client and professional about a new appointment."""
    try:
        appointment = Appointment.objects.select_related(
            'service',
            'professional',
            'professional__user',
        ).get(id=appointment_id)
    except Appointment.DoesNotExist:
        logger.warning(
            'Appointment %s not found; notifications skipped.',
            appointment_id,
        )
        return

    service_name = (
        appointment.service.name if appointment.service else 'Atendimento'
    )
    professional = appointment.professional
    professional_name = (
        professional.user.username
        if professional.user_id
        else professional.slug
    )
    date_formatted = timezone.localtime(
        appointment.start_datetime
    ).strftime('%d/%m/%Y às %H:%M')

    messages = [
        (
            appointment.client_whatsapp,
            (
                f'Olá, {appointment.client_name}! 👋\n\n'
                f'O seu agendamento de *{service_name}* com '
                f'*{professional_name}* foi confirmado para '
                f'*{date_formatted}*!\n\n'
                'Obrigado por usar o AvisanoZap.'
            ),
            'client',
        ),
    ]

    if professional.whatsapp_number:
        messages.append(
            (
                professional.whatsapp_number,
                (
                    '📅 *Novo agendamento recebido!*\n\n'
                    f'👤 *Cliente:* {appointment.client_name}\n'
                    f'📱 *WhatsApp:* {appointment.client_whatsapp}\n'
                    f'🛠 *Serviço:* {service_name}\n'
                    f'⏰ *Data/Hora:* {date_formatted}'
                ),
                'professional',
            )
        )

    for number, message, recipient in messages:
        try:
            success = send_whatsapp_message(number=number, text=message)
        except Exception:
            logger.exception(
                'Unexpected error sending appointment notification '
                'to %s for appointment %s.',
                recipient,
                appointment_id,
            )
            continue

        if not success:
            logger.error(
                'Failed to send appointment notification to %s '
                'for appointment %s.',
                recipient,
                appointment_id,
            )


@shared_task
def process_pending_reminders():
    """Send reminders that are due."""
    now = timezone.now()
    pending_reminders = (
        WhatsAppReminder.objects.filter(
            status='PENDING',
            scheduled_for__lte=now,
            appointment__status='CONFIRMED',
        )
        .select_related(
            'appointment',
            'appointment__service',
            'appointment__professional',
        )
    )

    for reminder in pending_reminders:
        appointment = reminder.appointment

        try:
            service_name = (
                appointment.service.name
                if appointment.service
                else 'Atendimento'
            )
            date_formatted = timezone.localtime(
                appointment.start_datetime
            ).strftime('%d/%m/%Y às %H:%M')

            message = (
                f'Olá, {appointment.client_name}! 👋\n\n'
                f'Passando para lembrar do seu agendamento de '
                f'*{service_name}* para *{date_formatted}*.\n\n'
                'Caso precise reagendar ou desmarcar, entre em '
                'contato conosco.'
            )

            success = send_whatsapp_message(
                number=appointment.client_whatsapp,
                text=message,
            )

            if success:
                reminder.status = 'SENT'
                reminder.sent_at = timezone.now()
            else:
                reminder.status = 'FAILED'

            reminder.save(update_fields=['status', 'sent_at'])

        except Exception:
            logger.exception(
                'Failed to process reminder %s.',
                reminder.id,
            )
