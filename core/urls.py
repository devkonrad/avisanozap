from django.contrib import admin
from django.urls import include, path

from appointments.api import api
from appointments.views import public_schedule_view
from core.views import LandingPageView

from django.urls import include

urlpatterns = [
    path("", LandingPageView.as_view(), name="home"),
    path("admin/", admin.site.urls),
    path("api/", api.urls),
    path("accounts/", include("appointments.auth_urls")),
    path("<slug:slug>/", public_schedule_view, name="public_schedule"),
    path("billing/", include("billing.urls")),
]
