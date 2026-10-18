from django.urls import path

from . import views

app_name = "billing"

urlpatterns = [
    path(
        "checkout/<slug:plan_code>/",
        views.checkout,
        name="checkout",
    ),
    path(
        "webhooks/mercado-pago/",
        views.mercado_pago_webhook,
        name="mercado_pago_webhook",
    ),
    path(
        "return/<uuid:subscription_id>/",
        views.checkout_return,
        name="checkout_return",
    ),
]
