import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("appointments", "0003_professionalprofile_welcome_email_sent_at"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReminderTestConfiguration",
            fields=[
                (
                    "id",
                    models.PositiveSmallIntegerField(
                        default=1,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "enabled",
                    models.BooleanField(
                        default=False,
                        verbose_name="Teste periódico ativo",
                    ),
                ),
                (
                    "destination_phone",
                    models.CharField(
                        blank=True,
                        help_text="Número que receberá as mensagens de teste.",
                        max_length=20,
                        verbose_name="WhatsApp de destino",
                    ),
                ),
                (
                    "interval_minutes",
                    models.PositiveIntegerField(
                        default=15,
                        help_text="Valor entre 1 e 1440 minutos.",
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(1440),
                        ],
                        verbose_name="Intervalo em minutos",
                    ),
                ),
                (
                    "last_attempt_at",
                    models.DateTimeField(
                        blank=True,
                        editable=False,
                        null=True,
                        verbose_name="Última tentativa",
                    ),
                ),
                (
                    "last_success_at",
                    models.DateTimeField(
                        blank=True,
                        editable=False,
                        null=True,
                        verbose_name="Último envio bem-sucedido",
                    ),
                ),
                (
                    "last_result",
                    models.CharField(
                        blank=True,
                        default="Ainda não executado.",
                        editable=False,
                        max_length=255,
                        verbose_name="Resultado da última tentativa",
                    ),
                ),
            ],
            options={
                "verbose_name": "Configuração do teste de lembretes",
                "verbose_name_plural": "Configuração do teste de lembretes",
            },
        ),
    ]
