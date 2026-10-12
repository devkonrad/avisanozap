from django.contrib import admin
from .models import ProfessionalProfile, Service, Availability, Appointment, WhatsAppReminder

admin.site.register(ProfessionalProfile)
admin.site.register(Service)
admin.site.register(Availability)
admin.site.register(Appointment)
admin.site.register(WhatsAppReminder)
