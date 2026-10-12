from django.contrib import admin
from django.urls import path
from .views import LandingPageView
from appointments.api import api
from appointments.views import public_schedule_view

urlpatterns = [
    path('', LandingPageView.as_view(), name='home'),
    path('admin/', admin.site.urls),
    path('api/', api.urls),
    path('<slug:slug>/', public_schedule_view, name='public_schedule'),
]
