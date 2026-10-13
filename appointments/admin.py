from django.contrib import admin

from .models import (
    Appointment,
    Availability,
    ProfessionalProfile,
    Service,
    WhatsAppReminder,
)


@admin.register(ProfessionalProfile)
class ProfessionalProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'whatsapp_number', 'slug', 'created_at')
    search_fields = ('user__username', 'whatsapp_number', 'slug')


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'professional', 'price', 'duration_minutes')
    search_fields = ('name',)


admin.site.register(Availability)
admin.site.register(Appointment)
admin.site.register(WhatsAppReminder)
