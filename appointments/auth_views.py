from django.contrib.auth import login
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import FormView

from .forms import ProfessionalSignUpForm


class SignUpView(FormView):
    template_name = "registration/signup.html"
    form_class = ProfessionalSignUpForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["next"] = (
            self.request.POST.get("next")
            or self.request.GET.get("next", "")
        )
        return context

    def form_valid(self, form):
        user = form.save()
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

        return redirect("home")


class ProfessionalLoginView(LoginView):
    template_name = "registration/login.html"
    redirect_authenticated_user = True
    next_page = "appointments_dashboard"


class ProfessionalLogoutView(LogoutView):
    next_page = "home"
