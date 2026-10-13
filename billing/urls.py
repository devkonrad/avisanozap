from django.urls import path

from . import views

app_name = "billing"

urlpatterns = [
    path(
        "checkout/<slug:plan_code>/",
        views.checkout,
        name="checkout",
    ),
]
