from decimal import Decimal
from .models import Appointment, Service

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.db import transaction

from django.utils import timezone
from .models import ProfessionalProfile
from .services import normalize_brazilian_phone

class ProfessionalSignUpForm(UserCreationForm):
    first_name = forms.CharField(
        label="Nome",
        max_length=150,
    )
    email = forms.EmailField(label="E-mail")
    whatsapp_number = forms.CharField(
        label="WhatsApp com DDD",
        max_length=20,
    )
    slug = forms.SlugField(
        label="Endereço público",
        max_length=50,
        help_text="Exemplo: dra-ana",
    )

    class Meta:
        model = User
        fields = (
            "username",
            "first_name",
            "email",
            "whatsapp_number",
            "slug",
        )
        labels = {
            "username": "Nome de usuário",
        }

    def __init__(self, *args, subscription=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.subscription = subscription

        if subscription and not subscription.professional_id:
            self.initial["email"] = subscription.customer_email
            self.fields["email"].widget.attrs["readonly"] = True

            if subscription.customer_whatsapp:
                self.initial["whatsapp_number"] = (
                    subscription.customer_whatsapp
                )
                self.fields["whatsapp_number"].widget.attrs["readonly"] = True

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()

        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "Já existe uma conta cadastrada com este e-mail."
            )

        return email

    def clean_slug(self):
        slug = self.cleaned_data["slug"].strip().lower()

        if ProfessionalProfile.objects.filter(slug=slug).exists():
            raise forms.ValidationError(
                "Este endereço público já está em uso."
            )

        return slug

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data["first_name"].strip()
        user.email = self.cleaned_data["email"]

        if commit:
            user.save()
            ProfessionalProfile.objects.create(
                user=user,
                whatsapp_number=(
                    self.cleaned_data["whatsapp_number"].strip()
                ),
                slug=self.cleaned_data["slug"],
            )

        return user


class ProfessionalProfileUpdateForm(forms.Form):
    first_name = forms.CharField(
        label="Nome",
        max_length=150,
    )
    email = forms.EmailField(label="E-mail")
    whatsapp_number = forms.CharField(
        label="WhatsApp com DDD",
        max_length=20,
    )
    slug = forms.SlugField(
        label="Endereço público",
        max_length=50,
        help_text="Este endereço é usado na sua página de agendamento.",
    )

    def __init__(self, *args, user, profile, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.profile = profile

        if not self.is_bound:
            self.initial.update(
                {
                    "first_name": user.first_name,
                    "email": user.email,
                    "whatsapp_number": profile.whatsapp_number,
                    "slug": profile.slug,
                }
            )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()

        if User.objects.filter(
            email__iexact=email,
        ).exclude(pk=self.user.pk).exists():
            raise forms.ValidationError(
                "Já existe uma conta cadastrada com este e-mail."
            )

        return email

    def clean_slug(self):
        slug = self.cleaned_data["slug"].strip().lower()

        if ProfessionalProfile.objects.filter(
            slug=slug,
        ).exclude(pk=self.profile.pk).exists():
            raise forms.ValidationError(
                "Este endereço público já está em uso."
            )

        return slug

    def save(self):
        self.user.first_name = self.cleaned_data["first_name"].strip()
        self.user.email = self.cleaned_data["email"]
        self.user.save(update_fields=["first_name", "email"])

        self.profile.whatsapp_number = (
            self.cleaned_data["whatsapp_number"].strip()
        )
        self.profile.slug = self.cleaned_data["slug"]
        self.profile.save(
            update_fields=["whatsapp_number", "slug"],
        )

        return self.profile


class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = (
            "name",
            "duration_minutes",
            "price",
            "is_active",
        )
        labels = {
            "name": "Nome do serviço",
            "duration_minutes": "Duração (minutos)",
            "price": "Preço (R$)",
            "is_active": "Serviço ativo",
        }
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "placeholder": "Ex.: Consulta inicial",
                }
            ),
            "duration_minutes": forms.NumberInput(
                attrs={
                    "min": 1,
                    "step": 1,
                }
            ),
            "price": forms.NumberInput(
                attrs={
                    "min": "0.00",
                    "step": "0.01",
                }
            ),
            "is_active": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not self.instance.pk:
            self.fields["is_active"].initial = True

    def clean_name(self):
        name = self.cleaned_data["name"].strip()

        if not name:
            raise forms.ValidationError(
                "Informe o nome do serviço."
            )

        return name

    def clean_duration_minutes(self):
        duration = self.cleaned_data["duration_minutes"]

        if duration < 1:
            raise forms.ValidationError(
                "A duração deve ser de pelo menos 1 minuto."
            )

        return duration

    def clean_price(self):
        price = self.cleaned_data["price"]

        if price < Decimal("0.00"):
            raise forms.ValidationError(
                "O preço não pode ser negativo."
            )

        return price


class DashboardAppointmentForm(forms.ModelForm):
    class Meta:
        model = Appointment
        fields = (
            "client_name",
            "client_whatsapp",
            "service",
            "start_datetime",
        )
        labels = {
            "client_name": "Nome do cliente",
            "client_whatsapp": "WhatsApp do cliente com DDD",
            "service": "Serviço",
            "start_datetime": "Data e horário",
        }
        widgets = {
            "client_name": forms.TextInput(
                attrs={"placeholder": "Nome completo do cliente"}
            ),
            "client_whatsapp": forms.TextInput(
                attrs={"placeholder": "(11) 99999-9999"}
            ),
            "start_datetime": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
        }

    def __init__(self, *args, professional, **kwargs):
        super().__init__(*args, **kwargs)
        self.professional = professional
        self.fields["service"].queryset = (
            Service.objects.filter(professional=professional)
            .order_by("name")
        )

    def clean_client_name(self):
        return self.cleaned_data["client_name"].strip()

    def clean_client_whatsapp(self):
        number = self.cleaned_data["client_whatsapp"]

        try:
            return normalize_brazilian_phone(number)
        except ValueError as exc:
            raise forms.ValidationError(
                "Informe um número de WhatsApp brasileiro válido com DDD."
            ) from exc

    def clean_start_datetime(self):
        start_datetime = self.cleaned_data["start_datetime"]

        if timezone.is_naive(start_datetime):
            return timezone.make_aware(
                start_datetime,
                timezone.get_current_timezone(),
            )

        return start_datetime
