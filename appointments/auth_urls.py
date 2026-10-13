from django.urls import path

from .auth_views import (
    ProfessionalLoginView,
    ProfessionalLogoutView,
    SignUpView,
)

app_name = "accounts"

urlpatterns = [
    path("signup/", SignUpView.as_view(), name="signup"),
    path("login/", ProfessionalLoginView.as_view(), name="login"),
    path("logout/", ProfessionalLogoutView.as_view(), name="logout"),
]
