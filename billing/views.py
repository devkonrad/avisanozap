from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from appointments.models import ProfessionalProfile
from .models import BillingPlan, Subscription
from .services.asaas import AsaasError, create_checkout

import logging

logger = logging.getLogger(__name__)

@login_required
def checkout(request, plan_code):
    plan = get_object_or_404(
        BillingPlan,
        code=plan_code,
        is_active=True,
    )

    profile = get_object_or_404(
        ProfessionalProfile,
        user=request.user,
    )

    if request.method == "GET":
        return render(
            request,
            "billing/checkout_confirm.html",
            {"plan": plan},
        )

    if request.method != "POST":
        return redirect("home")

    open_subscriptions = Subscription.objects.filter(
        professional=profile,
        status__in=["PENDING", "ACTIVE"],
    )

    existing = open_subscriptions.first()

    if existing and existing.status == "ACTIVE":
        messages.info(
            request,
            "Você já possui uma assinatura ativa.",
        )
        return redirect("home")

    if existing and existing.billing_plan_id != plan.id:
        messages.error(
            request,
            "Você já possui uma contratação pendente. "
            "Conclua ou resolva essa contratação antes de "
            "escolher outro plano.",
        )
        return redirect("home")

    if existing and existing.asaas_checkout_url:
        return redirect(existing.asaas_checkout_url)

    if existing:
        subscription = existing
    else:
        try:
            with transaction.atomic():
                subscription = Subscription.objects.create(
                    professional=profile,
                    plan=(
                        "MONTHLY"
                        if plan.billing_type == "MONTHLY"
                        else "PIX"
                    ),
                    billing_plan=plan,
                    amount=plan.amount,
                    status="PENDING",
                )
        except IntegrityError:
            messages.error(
                request,
                "Não foi possível iniciar outra contratação. "
                "Verifique se já existe uma assinatura pendente.",
            )
            return redirect("home")

    callback_url = request.build_absolute_uri(
        reverse("home")
    )

    try:
        checkout_data = create_checkout(
            subscription=subscription,
            plan=plan,
            callback_url=callback_url,
        )
    except AsaasError:
        logger.exception("Failed to create Asaas checkout")
        subscription.status = "CANCELED"
        subscription.save(
            update_fields=["status", "updated_at"],
        )
        messages.error(
            request,
            "Não foi possível iniciar o pagamento. "
            "Consulte os logs para identificar o problema.",
        )
        return redirect("home")

    subscription.asaas_checkout_id = checkout_data["id"]
    subscription.asaas_checkout_url = checkout_data["url"]
    subscription.save(
        update_fields=[
            "asaas_checkout_id",
            "asaas_checkout_url",
            "updated_at",
        ]
    )

    return redirect(subscription.asaas_checkout_url)
