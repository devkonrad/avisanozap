from django.contrib import admin
from django.utils import timezone

from .models import (
    Appointment,
    Availability,
    ProfessionalProfile,
    ReminderTestConfiguration,
    Service,
    WhatsAppReminder,
)


@admin.register(ProfessionalProfile)
class ProfessionalProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "whatsapp_number", "slug", "created_at")
    search_fields = ("user__username", "whatsapp_number", "slug")


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("name", "professional", "price", "duration_minutes")
    search_fields = ("name",)


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = (
        "client_name",
        "professional",
        "local_start_datetime",
        "local_end_datetime",
        "status",
    )
    list_filter = ("status", "professional")
    search_fields = ("client_name", "client_whatsapp")

    @admin.display(description="Início (Brasília)", ordering="start_datetime")
    def local_start_datetime(self, obj):
        return timezone.localtime(obj.start_datetime).strftime(
            "%d/%m/%Y %H:%M"
        )

    @admin.display(description="Fim (Brasília)", ordering="end_datetime")
    def local_end_datetime(self, obj):
        return timezone.localtime(obj.end_datetime).strftime(
            "%d/%m/%Y %H:%M"
        )


@admin.register(ReminderTestConfiguration)
class ReminderTestConfigurationAdmin(admin.ModelAdmin):
    list_display = (
        "enabled",
        "destination_phone",
        "interval_minutes",
        "last_attempt_at",
        "last_success_at",
        "last_result",
    )
    fields = (
        "enabled",
        "destination_phone",
        "interval_minutes",
        "last_attempt_at",
        "last_success_at",
        "last_result",
    )
    readonly_fields = (
        "last_attempt_at",
        "last_success_at",
        "last_result",
    )

    def has_add_permission(self, request):
        return (
            super().has_add_permission(request)
            and not ReminderTestConfiguration.objects.exists()
        )

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Availability)
admin.site.register(WhatsAppReminder)
