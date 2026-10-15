
from datetime import timedelta

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import NinjaAPI

from .models import (
    Appointment,
    ProfessionalProfile,
    Service,
    WhatsAppReminder,
)
from .schemas import (
    AppointmentCreateSchema,
    AppointmentSchema,
    ServiceSchema,
)
from .services import normalize_brazilian_phone
from .tasks import send_appointment_notifications

api = NinjaAPI()


@api.get("/services/{professional_slug}", response=list[ServiceSchema])
def list_services(request, professional_slug: str):
    profile = get_object_or_404(
        ProfessionalProfile,
        slug=professional_slug,
    )
    return profile.services.filter(is_active=True)


@api.post("/appointments", response=AppointmentSchema)
def create_appointment(request, payload: AppointmentCreateSchema):
    professional = get_object_or_404(
        ProfessionalProfile,
        id=payload.professional_id,
    )
    service = get_object_or_404(
        Service,
        id=payload.service_id,
        professional=professional,
        is_active=True,
    )

    try:
        client_whatsapp = normalize_brazilian_phone(
            payload.client_whatsapp,
        )
    except ValueError:
        return 400, {
            'detail': (
                'Informe um número de WhatsApp brasileiro válido '
                'com DDD.'
            )
        }

    if payload.start_datetime <= timezone.now():
        return 400, {
            'detail': 'Escolha uma data e um horário futuros.'
        }

    end_datetime = payload.start_datetime + timedelta(
        minutes=service.duration_minutes,
    )

    with transaction.atomic():
        appointment = Appointment.objects.create(
            professional=professional,
            service=service,
            client_name=payload.client_name.strip(),
            client_whatsapp=client_whatsapp,
            start_datetime=payload.start_datetime,
            end_datetime=end_datetime,
            status=Appointment.STATUS_PENDING_CONFIRMATION,
        )

        reminder_time = appointment.start_datetime - timedelta(
            hours=24,
        )

        if reminder_time > timezone.now():
            WhatsAppReminder.objects.create(
                appointment=appointment,
                scheduled_for=reminder_time,
                reminder_type="24H",
                status="PENDING",
            )

        transaction.on_commit(
            lambda: send_appointment_notifications.delay(
                str(appointment.id),
            )
        )

    return appointment
