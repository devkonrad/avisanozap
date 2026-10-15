from django.contrib import admin
from django.urls import include, path

from appointments.api import api
from appointments.views import (
    appointments_dashboard_view,
    cancel_appointment_view,
    evolution_webhook_view,
    professional_profile_view,
    public_schedule_view,
)
from core.views import LandingPageView

urlpatterns = [
    path("", LandingPageView.as_view(), name="home"),
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
    path("<slug:slug>/", public_schedule_view, name="public_schedule"),
]
