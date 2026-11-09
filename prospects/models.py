
import uuid

from django.conf import settings
from django.db import models


class Prospect(models.Model):
    class Segment(models.TextChoices):
        BEAUTY_SALON = "beauty_salon", "Salão de beleza"
        BARBERSHOP = "barbershop", "Barbearia"
        AESTHETICS = "aesthetics", "Estética"
        NAIL_SALON = "nail_salon", "Esmalteria"
        MANICURE = "manicure", "Manicure"
        OTHER = "other", "Outro"

    class PhoneStatus(models.TextChoices):
        MOBILE_UNVERIFIED = (
            "mobile_unverified",
            "Celular - confirmar WhatsApp",
        )
        LANDLINE_UNVERIFIED = (
            "landline_unverified",
            "Telefone fixo - WhatsApp não confirmado",
        )
        AREA_CODE_TO_VERIFY = (
            "area_code_to_verify",
            "DDD divergente - verificar",
        )
        WHATSAPP_CONFIRMED = (
            "whatsapp_confirmed",
            "WhatsApp confirmado",
        )

    class SalesStatus(models.TextChoices):
        NEW = "new", "Novo"
        FIRST_CONTACT_SENT = (
            "first_contact_sent",
            "Primeiro contato enviado",
        )
        INTERESTED = "interested", "Demonstrou interesse"
        OFFER_SENT = "offer_sent", "Oferta enviada"
        DECLINED = "declined", "Não tem interesse"
        CONVERTED = "converted", "Cliente convertido"
        BLOCKED = "blocked", "Bloqueado"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    business_name = models.CharField(max_length=200)
    contact_name = models.CharField(max_length=150, blank=True)
    phone_number = models.CharField(max_length=20, db_index=True)
    phone_status = models.CharField(
        max_length=30,
        choices=PhoneStatus.choices,
        default=PhoneStatus.MOBILE_UNVERIFIED,
    )
    email = models.EmailField(blank=True)
    segment = models.CharField(
        max_length=30,
        choices=Segment.choices,
        default=Segment.OTHER,
    )
    sales_status = models.CharField(
        max_length=30,
        choices=SalesStatus.choices,
        default=SalesStatus.NEW,
        db_index=True,
    )
    city = models.CharField(max_length=100, blank=True)
    neighborhood = models.CharField(max_length=100, blank=True)
    source = models.CharField(max_length=100, blank=True)
    source_url = models.URLField(blank=True)
    notes = models.TextField(blank=True)

    whatsapp_opt_in_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    opt_out_at = models.DateTimeField(null=True, blank=True)
    contacted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["business_name"]
        verbose_name = "Potencial cliente"
        verbose_name_plural = "Potenciais clientes"

    def __str__(self):
        return self.business_name

    @property
    def can_receive_whatsapp(self):
        return True
        return (
            self.whatsapp_opt_in_at is not None
            and self.opt_out_at is None
            and self.sales_status not in {
                self.SalesStatus.DECLINED,
                self.SalesStatus.BLOCKED,
            }
        )


class ProspectInteraction(models.Model):
    class InteractionType(models.TextChoices):
        FIRST_CONTACT = "first_contact", "Primeiro contato"
        POSITIVE_REPLY = "positive_reply", "Resposta positiva"
        NEGATIVE_REPLY = "negative_reply", "Resposta negativa"
        OFFER_SENT = "offer_sent", "Oferta enviada"
        OTHER = "other", "Outra interação"

    class Direction(models.TextChoices):
        OUTBOUND = "outbound", "Enviada"
        INBOUND = "inbound", "Recebida"

    class Channel(models.TextChoices):
        WHATSAPP = "whatsapp", "WhatsApp"
        EMAIL = "email", "E-mail"
        PHONE = "phone", "Telefone"
        MANUAL = "manual", "Registro manual"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    prospect = models.ForeignKey(
        Prospect,
        on_delete=models.CASCADE,
        related_name="interactions",
        verbose_name="Potencial cliente",
    )
    interaction_type = models.CharField(
        max_length=30,
        choices=InteractionType.choices,
        default=InteractionType.OTHER,
    )
    direction = models.CharField(
        max_length=10,
        choices=Direction.choices,
    )
    channel = models.CharField(
        max_length=20,
        choices=Channel.choices,
        default=Channel.WHATSAPP,
    )
    message = models.TextField(blank=True)
    provider_message_id = models.CharField(
        max_length=200,
        blank=True,
        db_index=True,
    )
    is_automated = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prospect_interactions",
    )
    occurred_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at"]
        verbose_name = "Interação com potencial cliente"
        verbose_name_plural = "Histórico de interações"

    def __str__(self):
        return (
            f"{self.prospect.business_name} - "
            f"{self.get_interaction_type_display()}"
        )
