from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Appointment, ProfessionalProfile, WhatsAppReminder

import logging
from django.utils import timezone

from .services import send_whatsapp_message

from .forms import ProfessionalProfileUpdateForm

logger = logging.getLogger(__name__)

def public_schedule_view(request, slug):
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

    context = {
        "page_obj": page_obj,
        "client_name": client_name,
        "date_from": date_from,
        "date_to": date_to,
    }
    return render(
        request,
        "appointments/dashboard.html",
        context,
    )

@login_required
@require_POST
def cancel_appointment_view(request, appointment_id):
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

        if appointment.status != "CONFIRMED":
            return redirect("appointments_dashboard")

        appointment.status = "CANCELED"
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
        {
            "form": form,
        },
    )
