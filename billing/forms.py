from django import forms


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

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()
