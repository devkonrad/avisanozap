from django.contrib.auth import login
from django.contrib.auth.views import LoginView, LogoutView
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import FormView

from billing.models import Subscription

from .forms import ProfessionalSignUpForm
from .models import ProfessionalProfile


class SignUpView(FormView):
    template_name = "registration/signup.html"
    form_class = ProfessionalSignUpForm

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("appointments_dashboard")

        return super().dispatch(request, *args, **kwargs)

    def get_subscription_id(self):
        return (
            self.request.POST.get("subscription", "").strip()
            or self.request.GET.get("subscription", "").strip()
        )

    def get_subscription(self):
        subscription_id = self.get_subscription_id()

        if not subscription_id:
            return None

        try:
            return Subscription.objects.get(pk=subscription_id)
        except (
            Subscription.DoesNotExist,
            ValueError,
            ValidationError,
        ):
            return None

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["subscription"] = self.get_subscription()
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["next"] = (
            self.request.POST.get("next")
            or self.request.GET.get("next", "")
        )
        context["subscription_id"] = self.get_subscription_id()
        return context

    def form_valid(self, form):
        subscription_id = self.get_subscription_id()

        with transaction.atomic():
            subscription = None

            if subscription_id:
                try:
                    subscription = (
                        Subscription.objects.select_for_update()
                        .get(pk=subscription_id)
                    )
                except (
                    Subscription.DoesNotExist,
                    ValueError,
                    ValidationError,
                ):
                    form.add_error(
                        None,
                        "Não encontramos uma compra válida para este cadastro.",
                    )
                    return self.form_invalid(form)

                if subscription.status != Subscription.STATUS_ACTIVE:
                    form.add_error(
                        None,
                        "Sua assinatura ainda não foi confirmada. "
                        "Aguarde a confirmação do pagamento antes de criar "
                        "sua conta.",
                    )
                    return self.form_invalid(form)

                if subscription.professional_id is not None:
                    form.add_error(
                        None,
                        "Esta assinatura já está vinculada a uma conta.",
                    )
                    return self.form_invalid(form)

                email = form.cleaned_data["email"].strip().lower()
                subscription_email = (
                    subscription.customer_email.strip().lower()
                )

                if email != subscription_email:
                    form.add_error(
                        "email",
                        "Use o mesmo e-mail informado na compra.",
                    )
                    return self.form_invalid(form)

                if subscription.customer_whatsapp:
                    whatsapp_number = (
                        form.cleaned_data["whatsapp_number"].strip()
                    )
                    subscription_whatsapp = (
                        subscription.customer_whatsapp.strip()
                    )

                    if whatsapp_number != subscription_whatsapp:
                        form.add_error(
                            "whatsapp_number",
                            "Use o WhatsApp informado na compra.",
                        )
                        return self.form_invalid(form)

            user = form.save()
            profile = ProfessionalProfile.objects.get(user=user)

            if subscription:
                subscription.professional = profile
                subscription.save(update_fields=["professional"])

        login(self.request, user)

        next_url = (
            self.request.POST.get("next")
            or self.request.GET.get("next")
        )
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={self.request.get_host()},
            require_https=self.request.is_secure(),
        ):
            return redirect(next_url)

        return redirect("appointments_dashboard")


class ProfessionalLoginView(LoginView):
    template_name = "registration/login.html"
    redirect_authenticated_user = True
    next_page = "appointments_dashboard"


class ProfessionalLogoutView(LogoutView):
    next_page = "home"
