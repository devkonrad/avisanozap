from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from .auth_views import (
    ProfessionalLoginView,
    ProfessionalLogoutView,
    SignUpView,
)
from .password_reset_views import AvisanoZapPasswordResetView

app_name = "accounts"

urlpatterns = [
    path("signup/", SignUpView.as_view(), name="signup"),
    path("login/", ProfessionalLoginView.as_view(), name="login"),
    path("logout/", ProfessionalLogoutView.as_view(), name="logout"),
    path(
        "password-reset/",
        AvisanoZapPasswordResetView.as_view(
            template_name="registration/password_reset_form.html",
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="registration/password_reset_done.html",
        ),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="registration/password_reset_confirm.html",
            success_url=reverse_lazy(
                "accounts:password_reset_complete",
            ),
        ),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="registration/password_reset_complete.html",
        ),
        name="password_reset_complete",
    ),
]
