import json
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .forms import (
    ProfessionalProfileUpdateForm,
    ServiceForm,
    DashboardAppointmentForm,
)
from .models import (
    Appointment,
    ProfessionalProfile,
    Service,
    WhatsAppReminder,
)
from .services import normalize_brazilian_phone, send_whatsapp_message
from .tasks import send_appointment_notifications

logger = logging.getLogger(__name__)


def public_schedule_view(request, slug):
    """Display the public scheduling page for a professional."""
    profile = get_object_or_404(ProfessionalProfile, slug=slug)
    services = profile.services.filter(is_active=True)

    context = {
        "profile_name": profile.slug.replace("-", " ").title(),
        "profile": profile,
        "services": services,
    }
    return render(request, "appointments/public_schedule.html", context)


@login_required
def appointments_dashboard_view(request):
    """Display and filter appointments for the logged-in professional."""
    profile = get_object_or_404(
        ProfessionalProfile,
        user=request.user,
    )

    appointments = (
        Appointment.objects.filter(professional=profile)
        .select_related("service")
        .order_by("-start_datetime", "-id")
    )

    client_name = request.GET.get("client_name", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()

    if client_name:
        appointments = appointments.filter(
            client_name__icontains=client_name,
        )

    if date_from:
        appointments = appointments.filter(
            start_datetime__date__gte=date_from,
        )

    if date_to:
        appointments = appointments.filter(
            start_datetime__date__lte=date_to,
        )

    paginator = Paginator(appointments, 20)
    page_obj = paginator.get_page(request.GET.get("page"))
    profile = request.user.profile

    context = {
        "page_obj": page_obj,
        "client_name": client_name,
        "date_from": date_from,
        "date_to": date_to,
        "profile": profile,
        "whatsapp_connected": (
            profile.whatsapp_session_status == "CONNECTED"
        ),
    }

    return render(
        request,
        "appointments/dashboard.html",
        context,
    )


@login_required
def services_dashboard_view(request):
    """List services belonging to the logged-in professional."""
    profile = get_object_or_404(
        ProfessionalProfile,
        user=request.user,
    )

    services = profile.services.order_by("name")

    return render(
        request,
        "appointments/services.html",
        {
            "profile": profile,
            "services": services,
        },
    )


@login_required
def service_create_view(request):
    """Create a service for the logged-in professional."""
    profile = get_object_or_404(
        ProfessionalProfile,
        user=request.user,
    )

    if request.method == "POST":
        form = ServiceForm(request.POST)

        if form.is_valid():
            service = form.save(commit=False)
            service.professional = profile
            service.save()

            return redirect("services_dashboard")
    else:
        form = ServiceForm()

    return render(
        request,
        "appointments/service_form.html",
        {
            "form": form,
            "profile": profile,
            "page_title": "Novo serviço",
        },
    )


@login_required
def service_edit_view(request, service_id):
    """Edit a service belonging to the logged-in professional."""
    profile = get_object_or_404(
        ProfessionalProfile,
        user=request.user,
    )

    service = get_object_or_404(
        Service,
        id=service_id,
        professional=profile,
    )

    if request.method == "POST":
        form = ServiceForm(request.POST, instance=service)

        if form.is_valid():
            form.save()
            return redirect("services_dashboard")
    else:
        form = ServiceForm(instance=service)

    return render(
        request,
        "appointments/service_form.html",
        {
            "form": form,
            "profile": profile,
            "service": service,
            "page_title": "Editar serviço",
        },
    )

@login_required
@require_POST
def cancel_appointment_view(request, appointment_id):
    """Cancel a confirmed appointment and notify the client."""
    profile = get_object_or_404(
        ProfessionalProfile,
        user=request.user,
    )

    with transaction.atomic():
        appointment = get_object_or_404(
            Appointment.objects.select_for_update(
                of=("self",),
            ).select_related(
                "service",
                "professional",
                "professional__user",
            ),
            id=appointment_id,
            professional=profile,
        )

        if appointment.status != Appointment.STATUS_CONFIRMED:
            return redirect("appointments_dashboard")

        appointment.status = Appointment.STATUS_CANCELED
        appointment.save(update_fields=["status"])

        WhatsAppReminder.objects.filter(
            appointment=appointment,
            status="PENDING",
        ).update(status="FAILED")

        client_name = appointment.client_name
        client_whatsapp = appointment.client_whatsapp
        professional_name = (
            appointment.professional.user.get_full_name()
            or appointment.professional.user.username
        )

    message = (
        f"Olá, {client_name}! 😊\n\n"
        f"Infelizmente, {professional_name} precisou cancelar "
        "seu atendimento por motivos de força maior.\n\n"
        "Pedimos desculpas pelo inconveniente.\n\n"
        "Por favor, entre em contato para obter mais informações "
        "e combinar um novo horário.\n\n"
        "Agradecemos a compreensão! 💚\n"
        "AvisanoZap"
    )

    try:
        sent = send_whatsapp_message(
            number=client_whatsapp,
            text=message,
        )
    except Exception:
        logger.exception(
            "Unexpected error sending cancellation notification "
            "for appointment %s.",
            appointment_id,
        )
    else:
        if not sent:
            logger.error(
                "Cancellation notification failed for appointment %s.",
                appointment_id,
            )

    return redirect("appointments_dashboard")


@login_required
def professional_profile_view(request):
    """Display and update the logged-in professional's profile."""
    profile = get_object_or_404(
        ProfessionalProfile,
        user=request.user,
    )

    if request.method == "POST":
        form = ProfessionalProfileUpdateForm(
            request.POST,
            user=request.user,
            profile=profile,
        )

        if form.is_valid():
            form.save()
            return redirect("professional_profile")
    else:
        form = ProfessionalProfileUpdateForm(
            user=request.user,
            profile=profile,
        )

    return render(
        request,
        "appointments/profile.html",
        {"form": form},
    )


@csrf_exempt
@require_POST
def evolution_webhook_view(request):
    """Process appointment confirmation replies from Evolution API."""
    expected_token = settings.EVOLUTION_WEBHOOK_TOKEN
    provided_token = request.headers.get("X-Webhook-Token", "")

    if not secrets.compare_digest(provided_token, expected_token):
        return JsonResponse(
            {"detail": "Invalid webhook token."},
            status=401,
        )

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {"detail": "Invalid JSON payload."},
            status=400,
        )

    if not isinstance(payload, dict):
        return JsonResponse(
            {"detail": "Expected a JSON object."},
            status=400,
        )

    event = payload.get("event")
    if not isinstance(event, str) or event.lower() != "messages.upsert":
        return JsonResponse({"received": True})

    data = payload.get("data")
    if not isinstance(data, dict):
        return JsonResponse({"received": True})

    key = data.get("key")
    message = data.get("message")

    if not isinstance(key, dict) or not isinstance(message, dict):
        return JsonResponse({"received": True})

    # Try the alternate JID first because remoteJid may contain a LID.
    phone = None

    for jid in (key.get("remoteJidAlt"), key.get("remoteJid")):
        if not isinstance(jid, str):
            continue

        raw_phone = jid.split("@", 1)[0].split(":", 1)[0]

        try:
            phone = normalize_brazilian_phone(raw_phone)
            break
        except ValueError:
            continue

    if phone is None:
        logger.warning(
            "Ignoring webhook with an invalid Brazilian phone number."
        )
        return JsonResponse({"received": True})

    text = message.get("conversation", "")

    if not text:
        extended_text = message.get("extendedTextMessage", {})
        if isinstance(extended_text, dict):
            text = extended_text.get("text", "")

    if not isinstance(text, str):
        return JsonResponse({"received": True})

    answer = text.strip().upper()

    if answer not in {"SIM", "NÃO", "NAO"}:
        return JsonResponse({"received": True})

    legacy_phone = (
        f"{phone[:4]}{phone[5:]}"
        if len(phone) == 13
        else phone
    )

    # Lock matching pending appointments to avoid processing concurrent replies.
    with transaction.atomic():
        appointments = list(
            Appointment.objects.select_for_update(
                of=("self",),
            )
            .filter(
                Q(client_whatsapp=phone)
                | Q(client_whatsapp=legacy_phone),
                status=Appointment.STATUS_PENDING_CONFIRMATION,
            )
            .select_related("service", "professional")
            .order_by("-created_at", "-id")
        )

        if not appointments:
            logger.info(
                "No pending appointments found for phone %s.",
                phone,
            )
            return JsonResponse({"received": True})

        if answer != "SIM" and len(appointments) > 1:
            logger.info(
                "Cancellation reply not processed: found %s pending "
                "appointments for phone %s.",
                len(appointments),
                phone,
            )
            return JsonResponse({"received": True})

        # For SIM, confirm the newest pending appointment.
        appointment = appointments[0]
        confirmed = answer == "SIM"

        if confirmed and len(appointments) > 1:
            other_ids = [item.id for item in appointments[1:]]

            deleted_count, _ = Appointment.objects.filter(
                id__in=other_ids,
                status=Appointment.STATUS_PENDING_CONFIRMATION,
            ).delete()

            logger.info(
                "Deleted %s duplicate pending appointments for phone %s.",
                deleted_count,
                phone,
            )

        appointment.status = (
            Appointment.STATUS_CONFIRMED
            if confirmed
            else Appointment.STATUS_CANCELED
        )
        appointment.save(update_fields=["status"])

    if confirmed:
        service_name = (
            appointment.service.name
            if appointment.service
            else "Serviço não informado"
        )

        professional = appointment.professional
        professional_name = (
            getattr(professional, "name", None)
            or getattr(professional, "slug", None)
            or "PROFISSIONAL"
        ).replace("-", "").upper()

        date_formatted = timezone.localtime(
            appointment.start_datetime
        ).strftime("%d/%m/%Y às %H:%M")

        notifications = [
            (
                appointment.client_whatsapp,
                (
                    f"Olá, {appointment.client_name}! 😊\n\n"
                    f"Seu agendamento de *{service_name}* com "
                    f"*{professional_name}* está confirmado para "
                    f"*{date_formatted}*.\n\n"
                    "Obrigado por usar o AvisanoZap!"
                ),
            ),
        ]

        if professional.whatsapp_number:
            notifications.append(
                (
                    professional.whatsapp_number,
                    (
                        "✅ *Agendamento confirmado!*\n\n"
                        f"O cliente *{appointment.client_name}* confirmou "
                        f"o agendamento de *{service_name}* para "
                        f"*{date_formatted}*."
                    ),
                )
            )

        for number, notification in notifications:
            try:
                sent = send_whatsapp_message(
                    number=number,
                    text=notification,
                )
            except Exception:
                logger.exception(
                    "Unexpected error sending confirmation notification "
                    "for appointment %s.",
                    appointment.id,
                )
                continue

            if not sent:
                logger.error(
                    "Failed to send confirmation notification "
                    "for appointment %s.",
                    appointment.id,
                )

    logger.info(
        "Appointment %s status updated to %s.",
        appointment.id,
        appointment.status,
    )
    return JsonResponse({"received": True})


@login_required
def appointment_create_view(request):
    """Create an appointment from the professional dashboard."""
    profile = get_object_or_404(
        ProfessionalProfile,
        user=request.user,
    )
    services = profile.services.all().order_by("name")

    if not services.exists():
        return render(
            request,
            "appointments/appointment_form.html",
            {
                "profile": profile,
                "services": services,
                "form": None,
            },
        )

    if request.method == "POST":
        form = DashboardAppointmentForm(
            request.POST,
            professional=profile,
        )

        if form.is_valid():
            appointment = form.save(commit=False)
            appointment.professional = profile
            appointment.end_datetime = (
                appointment.start_datetime
                + timedelta(
                    minutes=appointment.service.duration_minutes,
                )
            )
            appointment.status = (
                Appointment.STATUS_PENDING_CONFIRMATION
            )

            with transaction.atomic():
                appointment.save()

                now = timezone.now()
                reminder_intervals = (
                    ("24H", 24),
                    ("12H", 12),
                    ("6H", 6),
                )

                for reminder_type, hours_before in reminder_intervals:
                    reminder_time = (
                        appointment.start_datetime
                        - timedelta(hours=hours_before)
                    )

                    if reminder_time > now:
                        WhatsAppReminder.objects.create(
                            appointment=appointment,
                            scheduled_for=reminder_time,
                            reminder_type=reminder_type,
                            status="PENDING",
                        )

                transaction.on_commit(
                    lambda: send_appointment_notifications.delay(
                        str(appointment.id),
                    )
                )

            return redirect("appointments_dashboard")
    else:
        form = DashboardAppointmentForm(
            professional=profile,
        )

    return render(
        request,
        "appointments/appointment_form.html",
        {
            "profile": profile,
            "services": services,
            "form": form,
        },
    )
