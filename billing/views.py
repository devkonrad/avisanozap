import json
import logging
from django.utils import timezone

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

from appointments.models import ProfessionalProfile

from .models import (
    PROVIDER_ASAAS,
    PROVIDER_MERCADO_PAGO,
    BillingPlan,
    BillingSettings,
    MercadoPagoWebhookEvent,
    Payment,
    Subscription,
)
from .services.mercado_pago_webhooks import (
    MercadoPagoWebhookProcessingError,
    process_mercado_pago_order,
)
from .services.asaas import (
    AsaasError,
    create_checkout as create_asaas_checkout,
)
from .services.mercado_pago import (
    MercadoPagoError,
    create_checkout as create_mercado_pago_checkout,
    validate_webhook_signature,
)

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

    existing = Subscription.objects.filter(
        professional=profile,
        status__in=[
            Subscription.STATUS_PENDING,
            Subscription.STATUS_ACTIVE,
        ],
    ).first()

    if existing and existing.status == Subscription.STATUS_ACTIVE:
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

    if existing:
        subscription = existing
    else:
        billing_settings = BillingSettings.objects.filter(
            pk=1,
        ).first()
        provider = (
            billing_settings.checkout_provider
            if billing_settings
            else PROVIDER_ASAAS
        )

        if provider not in {
            PROVIDER_ASAAS,
            PROVIDER_MERCADO_PAGO,
        }:
            logger.error(
                "Unsupported checkout provider: %s",
                provider,
            )
            messages.error(
                request,
                "O pagamento está temporariamente indisponível. "
                "Tente novamente mais tarde.",
            )
            return redirect("home")

        try:
            with transaction.atomic():
                subscription = Subscription.objects.create(
                    professional=profile,
                    plan=(
                        Subscription.PLAN_MONTHLY
                        if plan.billing_type == BillingPlan.TYPE_MONTHLY
                        else Subscription.PLAN_PIX
                    ),
                    billing_plan=plan,
                    amount=plan.amount,
                    status=Subscription.STATUS_PENDING,
                    provider=provider,
                )
        except IntegrityError:
            messages.error(
                request,
                "Não foi possível iniciar outra contratação. "
                "Verifique se já existe uma assinatura pendente.",
            )
            return redirect("home")

    if subscription.provider_checkout_url:
        return redirect(subscription.provider_checkout_url)

    callback_url = request.build_absolute_uri(reverse("home"))

    try:
        if subscription.provider == PROVIDER_ASAAS:
            checkout_data = create_asaas_checkout(
                subscription=subscription,
                plan=plan,
                callback_url=callback_url,
            )
        elif subscription.provider == PROVIDER_MERCADO_PAGO:
            checkout_data = create_mercado_pago_checkout(
                subscription=subscription,
                plan=plan,
                callback_url=callback_url,
                payer_email=request.user.email,
            )
        else:
            logger.error(
                "Unsupported subscription provider: %s",
                subscription.provider,
            )
            messages.error(
                request,
                "O pagamento está temporariamente indisponível. "
                "Tente novamente mais tarde.",
            )
            return redirect("home")
    except (AsaasError, MercadoPagoError):
        logger.exception(
            "Failed to create checkout for subscription %s",
            subscription.id,
        )
        messages.error(
            request,
            "Não foi possível iniciar o pagamento. "
            "Tente novamente mais tarde.",
        )
        return redirect("home")

    subscription.provider_checkout_id = checkout_data["id"]
    subscription.provider_checkout_url = checkout_data["url"]

    update_fields = [
        "provider_checkout_id",
        "provider_checkout_url",
        "updated_at",
    ]

    if (
        subscription.provider == PROVIDER_MERCADO_PAGO
        and plan.billing_type == BillingPlan.TYPE_MONTHLY
    ):
        subscription.provider_subscription_id = (
            checkout_data["subscription_id"]
        )
        update_fields.append("provider_subscription_id")

    subscription.save(update_fields=update_fields)

    return redirect(subscription.provider_checkout_url)


@csrf_exempt
def mercado_pago_webhook(request):
    """Validate, store, and process Mercado Pago webhook notifications."""
    if request.method != "POST":
        return HttpResponse(status=405)

    secret = settings.MERCADO_PAGO_WEBHOOK_SECRET
    if not secret:
        logger.error("Mercado Pago webhook secret is not configured.")
        return HttpResponse(status=503)

    data_id = request.GET.get("data.id", "")
    is_valid = validate_webhook_signature(
        signature=request.headers.get("x-signature", ""),
        request_id=request.headers.get("x-request-id", ""),
        data_id=data_id,
        secret=secret,
    )

    if not is_valid:
        logger.warning("Rejected Mercado Pago webhook with invalid signature.")
        return HttpResponse(status=401)

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {"error": "Invalid JSON payload."},
            status=400,
        )

    if not isinstance(payload, dict) or not payload.get("id"):
        return JsonResponse(
            {"error": "Missing webhook event ID."},
            status=400,
        )

    event_id = str(payload["id"])
    event_type = str(
        payload.get("action") or payload.get("type") or "unknown"
    )

    event, _ = MercadoPagoWebhookEvent.objects.get_or_create(
        event_id=event_id,
        defaults={
            "event_type": event_type,
            "payload": payload,
        },
    )

    if event.status == MercadoPagoWebhookEvent.STATUS_PROCESSED:
        return HttpResponse(status=200)

    if not event_type.startswith("order"):
        event.status = MercadoPagoWebhookEvent.STATUS_PROCESSED
        event.processed_at = timezone.now()
        event.error_message = ""
        event.save(
            update_fields=[
                "status",
                "processed_at",
                "error_message",
            ]
        )
        return HttpResponse(status=200)

    event.status = MercadoPagoWebhookEvent.STATUS_PROCESSING
    event.error_message = ""
    event.save(update_fields=["status", "error_message"])

    try:
        process_mercado_pago_order(
            str((payload.get("data") or {}).get("id") or data_id)
        )
    except MercadoPagoError as exc:
        event.status = MercadoPagoWebhookEvent.STATUS_FAILED
        event.error_message = str(exc)[:2000]
        event.save(update_fields=["status", "error_message"])
        logger.exception("Mercado Pago order processing failed.")
        return HttpResponse(status=500)
    except MercadoPagoWebhookProcessingError as exc:
        event.status = MercadoPagoWebhookEvent.STATUS_FAILED
        event.error_message = str(exc)[:2000]
        event.save(update_fields=["status", "error_message"])
        logger.warning("Mercado Pago order rejected: %s", exc)
        return HttpResponse(status=200)

    event.status = MercadoPagoWebhookEvent.STATUS_PROCESSED
    event.processed_at = timezone.now()
    event.error_message = ""
    event.save(
        update_fields=[
            "status",
            "processed_at",
            "error_message",
        ]
    )

    return HttpResponse(status=200)

