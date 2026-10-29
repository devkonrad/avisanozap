
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path

from appointments.api import api
from appointments.views import (
    appointments_dashboard_view,
    appointment_create_view,
    cancel_appointment_view,
    evolution_webhook_view,
    professional_profile_view,
    public_schedule_view,
    service_create_view,
    service_edit_view,
    services_dashboard_view,
)

from core.views import LandingPageView


def google_site_verification_view(request):
    return HttpResponse(
        "google-site-verification: googled8a925164540d992.html",
        content_type="text/plain",
    )


urlpatterns = [
    path("", LandingPageView.as_view(), name="home"),
    path(
        "googled8a925164540d992.html",
        google_site_verification_view,
        name="google_site_verification",
    ),
    path("admin/", admin.site.urls),
    path("api/", api.urls),
    path("accounts/", include("appointments.auth_urls")),
    path(
        "dashboard/appointments/",
        appointments_dashboard_view,
        name="appointments_dashboard",
    ),
    path(
        "dashboard/appointments/<uuid:appointment_id>/cancel/",
        cancel_appointment_view,
        name="cancel_appointment",
    ),
    path("billing/", include("billing.urls")),
    path(
        "dashboard/profile/",
        professional_profile_view,
        name="professional_profile",
    ),
    path(
        "api/webhooks/evolution/",
        evolution_webhook_view,
        name="evolution_webhook",
    ),
    path(
        "dashboard/services/",
        services_dashboard_view,
        name="services_dashboard",
    ),
    path(
        "dashboard/services/new/",
        service_create_view,
        name="service_create",
    ),
    path(
        "dashboard/services/<uuid:service_id>/edit/",
        service_edit_view,
        name="service_edit",
    ),
    path(
        "dashboard/appointments/new/",
        appointment_create_view,
        name="appointment_create",
    ),
    path("<slug:slug>/", public_schedule_view, name="public_schedule"),
]
