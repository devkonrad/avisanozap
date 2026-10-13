import uuid
from django.db import models
from django.contrib.auth.models import User

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

class ProfessionalProfile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    whatsapp_number = models.CharField(max_length=20)
    slug = models.SlugField(unique=True, help_text="avisanozap.com.br/dra-ana")
    whatsapp_session_status = models.CharField(max_length=20, default='DISCONNECTED')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} ({self.slug})"

class Service(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    professional = models.ForeignKey(ProfessionalProfile, on_delete=models.CASCADE, related_name='services')
    name = models.CharField(max_length=150)
    duration_minutes = models.IntegerField(default=30)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} - R$ {self.price}"

class Availability(models.Model):
    DAYS_OF_WEEK = [
        (0, 'Segunda-feira'), (1, 'Terça-feira'), (2, 'Quarta-feira'),
        (3, 'Quinta-feira'), (4, 'Sexta-feira'), (5, 'Sábado'), (6, 'Domingo')
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    professional = models.ForeignKey(ProfessionalProfile, on_delete=models.CASCADE, related_name='availabilities')
    day_of_week = models.IntegerField(choices=DAYS_OF_WEEK)
    start_time = models.TimeField()
    end_time = models.TimeField()

class Appointment(models.Model):
    STATUS_CHOICES = [('CONFIRMED', 'Confirmado'), ('CANCELED', 'Cancelado'), ('COMPLETED', 'Concluído')]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    professional = models.ForeignKey(ProfessionalProfile, on_delete=models.CASCADE, related_name='appointments')
    service = models.ForeignKey(Service, on_delete=models.SET_NULL, null=True)
    client_name = models.CharField(max_length=200)
    client_whatsapp = models.CharField(max_length=20)
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='CONFIRMED')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.client_name} - {self.start_datetime.strftime('%d/%m/%Y %H:%M')}"

class WhatsAppReminder(models.Model):
    REMINDER_TYPES = [('IMMEDIATE', 'Confirmação Imediata'), ('24H', 'Lembrete 24h'), ('2H', 'Lembrete 2h')]
    STATUS_CHOICES = [('PENDING', 'Pendente'), ('SENT', 'Enviado'), ('FAILED', 'Falhou')]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name='reminders')
    scheduled_for = models.DateTimeField()
    reminder_type = models.CharField(max_length=20, choices=REMINDER_TYPES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    sent_at = models.DateTimeField(null=True, blank=True)
