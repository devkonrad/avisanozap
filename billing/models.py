import uuid

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

PROVIDER_ASAAS = "ASAAS"
PROVIDER_MERCADO_PAGO = "MERCADO_PAGO"

PROVIDER_CHOICES = [
    (PROVIDER_ASAAS, "Asaas"),
    (PROVIDER_MERCADO_PAGO, "Mercado Pago"),
]

class BillingPlan(models.Model):
    TYPE_MONTHLY = 'MONTHLY'
    TYPE_ONE_TIME = 'ONE_TIME'

    TYPE_CHOICES = [
        (TYPE_MONTHLY, 'Recorrente mensal'),
        (TYPE_ONE_TIME, 'Pagamento único'),
    ]

    PAYMENT_PIX = 'PIX'
    PAYMENT_CREDIT_CARD = 'CREDIT_CARD'
    PAYMENT_BOTH = 'BOTH'

    PAYMENT_CHOICES = [
        (PAYMENT_PIX, 'Pix'),
        (PAYMENT_CREDIT_CARD, 'Cartão de crédito'),
        (PAYMENT_BOTH, 'Pix e cartão de crédito'),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    code = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    billing_type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default=TYPE_ONE_TIME,
    )
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_CHOICES,
        default=PAYMENT_PIX,
    )
    access_days = models.PositiveSmallIntegerField(default=30)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = 'Plano'
        verbose_name_plural = 'Planos'

    def clean(self):
        super().clean()

        if self.billing_type == self.TYPE_MONTHLY:
            if self.payment_method != self.PAYMENT_CREDIT_CARD:
                from django.core.exceptions import ValidationError

                raise ValidationError({
                    'payment_method': (
                        'Planos recorrentes devem usar cartão de crédito.'
                    ),
                })

    def __str__(self):
        return f'{self.name} - R$ {self.amount}'


class Subscription(models.Model):
    PLAN_MONTHLY = 'MONTHLY'
    PLAN_PIX = 'PIX'

    PLAN_CHOICES = [
        (PLAN_MONTHLY, 'Mensal'),
        (PLAN_PIX, 'Pix por 30 dias'),
    ]

    STATUS_PENDING = 'PENDING'
    STATUS_ACTIVE = 'ACTIVE'
    STATUS_CANCELED = 'CANCELED'
    STATUS_EXPIRED = 'EXPIRED'
    STATUS_PAST_DUE = 'PAST_DUE'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pendente'),
        (STATUS_ACTIVE, 'Ativo'),
        (STATUS_CANCELED, 'Cancelado'),
        (STATUS_EXPIRED, 'Expirado'),
        (STATUS_PAST_DUE, 'Em atraso'),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    professional = models.ForeignKey(
        "appointments.ProfessionalProfile",
        on_delete=models.PROTECT,
        related_name="subscriptions",
        null=True,
        blank=True,
    )
    customer_email = models.EmailField(
        max_length=254,
        blank=True,
        default="",
    )
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )
    amount = models.DecimalField(max_digits=8, decimal_places=2)

    provider = models.CharField(
        max_length=20,
        choices=PROVIDER_CHOICES,
        default=PROVIDER_ASAAS,
    )
    provider_customer_id = models.CharField(
        max_length=100,
        blank=True,
    )
    provider_subscription_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
    )
    provider_checkout_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
    )
    provider_checkout_url = models.URLField(blank=True)

    billing_plan = models.ForeignKey(
        BillingPlan,
        on_delete=models.PROTECT,
        related_name='subscriptions',
        null=True,
        blank=True,
    )

    started_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'appointments_subscription'
        constraints = [
            models.UniqueConstraint(
                fields=['professional'],
                condition=Q(status__in=['PENDING', 'ACTIVE']),
                name='unique_open_subscription_per_professional',
            ),
            models.UniqueConstraint(
                fields=["provider", "provider_subscription_id"],
                condition=(
                    Q(provider_subscription_id__isnull=False)
                    & ~Q(provider_subscription_id="")
                ),
                name="unique_provider_subscription_id",
            ),
            models.UniqueConstraint(
                fields=["provider", "provider_checkout_id"],
                condition=(
                    Q(provider_checkout_id__isnull=False)
                    & ~Q(provider_checkout_id="")
                ),
                name="unique_provider_checkout_id",
            ),
            models.UniqueConstraint(
                fields=["customer_email"],
                condition=(
                    Q(professional__isnull=True)
                    & ~Q(customer_email="")
                    & Q(status__in=["PENDING", "ACTIVE"])
                ),
                name="unique_open_guest_subscription_per_email",
            ),
        ]

    def __str__(self):
        return (
            f'{self.professional} - {self.get_plan_display()} '
            f'({self.get_status_display()})'
        )


class Payment(models.Model):
    STATUS_PENDING = 'PENDING'
    STATUS_CONFIRMED = 'CONFIRMED'
    STATUS_RECEIVED = 'RECEIVED'
    STATUS_OVERDUE = 'OVERDUE'
    STATUS_REFUNDED = 'REFUNDED'
    STATUS_CANCELED = 'CANCELED'
    STATUS_FAILED = 'FAILED'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pendente'),
        (STATUS_CONFIRMED, 'Confirmado'),
        (STATUS_RECEIVED, 'Recebido'),
        (STATUS_OVERDUE, 'Vencido'),
        (STATUS_REFUNDED, 'Estornado'),
        (STATUS_CANCELED, 'Cancelado'),
        (STATUS_FAILED, 'Falhou'),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.PROTECT,
        related_name='payments',
    )
    provider = models.CharField(
        max_length=20,
        choices=PROVIDER_CHOICES,
        default=PROVIDER_ASAAS,
    )
    provider_payment_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
    )
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )
    due_date = models.DateField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "appointments_payment"
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_payment_id"],
                condition=(
                    Q(provider_payment_id__isnull=False)
                    & ~Q(provider_payment_id="")
                ),
                name="unique_provider_payment_id",
            ),
        ]

    def __str__(self):
        return (
            f'{self.subscription.professional} - '
            f'R$ {self.amount} ({self.get_status_display()})'
        )


class BillingSettings(models.Model):
    checkout_provider = models.CharField(
        max_length=20,
        choices=PROVIDER_CHOICES,
        default=PROVIDER_MERCADO_PAGO,
        verbose_name="Provedor padrão de checkout",
        help_text=(
            "Provedor utilizado nas novas contratações. "
            "Assinaturas existentes mantêm seu provedor original."
        ),
    )
    reminder_business_days = models.PositiveSmallIntegerField(
        default=3,
        validators=[
            MinValueValidator(1),
            MaxValueValidator(30),
        ],
        verbose_name='Antecedência do lembrete Pix (dias úteis)',
        help_text=(
            'Quantidade de dias úteis antes do vencimento '
            'para enviar o lembrete de pagamento.'
        ),
    )

    class Meta:
        db_table = 'appointments_billingsettings'
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    reminder_business_days__gte=1,
                    reminder_business_days__lte=30,
                ),
                name='valid_billing_reminder_business_days',
            ),
        ]
        verbose_name = 'Configuração de cobrança'
        verbose_name_plural = 'Configurações de cobrança'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f'Lembrete Pix: {self.reminder_business_days} '
            'dias úteis antes do vencimento'
        )


class AsaasWebhookEvent(models.Model):
    STATUS_RECEIVED = 'RECEIVED'
    STATUS_PROCESSING = 'PROCESSING'
    STATUS_PROCESSED = 'PROCESSED'
    STATUS_FAILED = 'FAILED'

    STATUS_CHOICES = [
        (STATUS_RECEIVED, 'Recebido'),
        (STATUS_PROCESSING, 'Em processamento'),
        (STATUS_PROCESSED, 'Processado'),
        (STATUS_FAILED, 'Falhou'),
    ]

    event_id = models.CharField(max_length=100, unique=True)
    event_type = models.CharField(max_length=100)
    payload = models.JSONField(default=dict)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_RECEIVED,
    )
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        db_table = 'appointments_asaaswebhookevent'
        ordering = ['-received_at']
        verbose_name = 'Evento de webhook Asaas'
        verbose_name_plural = 'Eventos de webhook Asaas'

    def __str__(self):
        return f'{self.event_type} - {self.event_id}'


class MercadoPagoWebhookEvent(models.Model):
    STATUS_RECEIVED = 'RECEIVED'
    STATUS_PROCESSING = 'PROCESSING'
    STATUS_PROCESSED = 'PROCESSED'
    STATUS_FAILED = 'FAILED'

    STATUS_CHOICES = [
        (STATUS_RECEIVED, 'Recebido'),
        (STATUS_PROCESSING, 'Em processamento'),
        (STATUS_PROCESSED, 'Processado'),
        (STATUS_FAILED, 'Falhou'),
    ]

    event_id = models.CharField(max_length=100, unique=True)
    event_type = models.CharField(max_length=100)
    payload = models.JSONField(default=dict)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_RECEIVED,
    )
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        db_table = 'appointments_mercadopagowebhookevent'
        ordering = ['-received_at']
        verbose_name = 'Evento de webhook Mercado Pago'
        verbose_name_plural = 'Eventos de webhook Mercado Pago'

    def __str__(self):
        return f'{self.event_type} - {self.event_id}'
