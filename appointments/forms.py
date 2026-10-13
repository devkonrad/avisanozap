from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.db import transaction

from .models import ProfessionalProfile


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
