from django import forms
from appointments.services import normalize_brazilian_phone

class CheckoutEmailForm(forms.Form):
    email = forms.EmailField(
        label="E-mail",
        max_length=254,
        widget=forms.EmailInput(
            attrs={
                "autocomplete": "email",
                "placeholder": "suaempresa@avisanozap.com.br",
            }
        ),
    )
    whatsapp_number = forms.CharField(
        label="WhatsApp com DDD",
        max_length=20,
        help_text="Informe um número brasileiro com DDD.",
    )

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()

    def clean_whatsapp_number(self):
        number = self.cleaned_data["whatsapp_number"]

        try:
            return normalize_brazilian_phone(number)
        except ValueError as exc:
            raise forms.ValidationError(
                "Informe um número de WhatsApp válido com DDD."
            ) from exc
