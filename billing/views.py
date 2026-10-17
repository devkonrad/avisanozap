import json
import logging

from django.conf import settings
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from appointments.models import ProfessionalProfile
from billing.forms import CheckoutEmailForm
from billing.models import (
    PROVIDER_ASAAS,
    PROVIDER_MERCADO_PAGO,
    BillingPlan,
    BillingSettings,
    MercadoPagoWebhookEvent,
    Subscription,
)
from billing.services.asaas import (
    AsaasError,
    create_checkout as create_asaas_checkout,
)
from billing.services.mercado_pago import (
    MercadoPagoError,
    create_checkout as create_mercado_pago_checkout,
    validate_webhook_signature,
)
from billing.services.mercado_pago_webhooks import (
    MercadoPagoWebhookProcessingError,
    process_mercado_pago_order,
)

logger = logging.getLogger(__name__)


def checkout(request, plan_code):
    plan = get_object_or_404(
        BillingPlan,
        code=plan_code,
        is_active=True,
    )
    profile = None

    if request.user.is_authenticated:
        profile = ProfessionalProfile.objects.filter(
            user=request.user,
        ).first()

    if profile:
        email = profile.user.email.strip().lower()
        email_form = CheckoutEmailForm(
            initial={"email": email},
        )
    elif request.method == "POST":
        email_form = CheckoutEmailForm(request.POST)
        if not email_form.is_valid():
            return render(
                request,
                "billing/checkout_confirm.html",
                {
                    "plan": plan,
                    "email_form": email_form,
                },
                status=400,
            )
        email = email_form.cleaned_data["email"]
    else:
        email_form = CheckoutEmailForm(
            initial={
                "email": (
                    request.user.email
                    if request.user.is_authenticated
                    else ""
                ),
            },
        )
        return render(
            request,
            "billing/checkout_confirm.html",
            {
                "plan": plan,
                "email_form": email_form,
            },
        )

    if request.method == "GET":
        return render(
            request,
            "billing/checkout_confirm.html",
            {
                "plan": plan,
                "email_form": email_form,
            },
        )

    if request.method != "POST":
        return redirect("home")

    open_statuses = [
        Subscription.STATUS_PENDING,
        Subscription.STATUS_ACTIVE,
    ]
    subscriptions = Subscription.objects.filter(
        status__in=open_statuses,
    )

    if profile:
        subscriptions = subscriptions.filter(
            professional=profile,
        )
    else:
        subscriptions = subscriptions.filter(
            professional__isnull=True,
            customer_email=email,
        )

    existing = subscriptions.first()

    if existing and existing.status == Subscription.STATUS_ACTIVE:
        messages.info(
            request,
            "Você já possui uma assinatura ativa.",
        )
        return redirect("home")

    if existing and existing.billing_plan_id != plan.id:
        messages.error(
            request,
            "Já existe uma compra em andamento para este cadastro. "
            "Retome o checkout anterior antes de escolher outro plano.",
        )
        return redirect("home")

    if existing:
        subscription = existing
        provider = subscription.provider
    else:
        billing_settings = BillingSettings.objects.filter(
            pk=1,
        ).first()
        provider = (
            billing_settings.checkout_provider
            if billing_settings and billing_settings.checkout_provider
            else PROVIDER_MERCADO_PAGO
        )

        if provider not in {
            PROVIDER_ASAAS,
            PROVIDER_MERCADO_PAGO,
        }:
            messages.error(
                request,
                "O meio de pagamento está indisponível no momento.",
            )
            return redirect("home")

        subscription_plan = (
            Subscription.PLAN_MONTHLY
            if plan.billing_type == BillingPlan.TYPE_MONTHLY
            else Subscription.PLAN_PIX
        )

        try:
            with transaction.atomic():
                subscription = Subscription.objects.create(
                    professional=profile,
                    customer_email=email,
                    plan=subscription_plan,
                    billing_plan=plan,
                    amount=plan.amount,
                    status=Subscription.STATUS_PENDING,
                    provider=provider,
                )
        except IntegrityError:
            messages.error(
                request,
                "Já existe uma compra em andamento para este cadastro. "
                "Tente retomar o checkout anterior.",
            )
            return redirect("home")

    if subscription.provider_checkout_url:
        return redirect(subscription.provider_checkout_url)

    callback_url = request.build_absolute_uri(
        reverse("home"),
    )

    try:
        if provider == PROVIDER_ASAAS:
            checkout_data = create_asaas_checkout(
                subscription,
                plan,
                callback_url,
            )
        else:
            checkout_data = create_mercado_pago_checkout(
                subscription,
                plan,
                callback_url,
                payer_email=email,
            )
    except (AsaasError, MercadoPagoError):
        logger.exception(
            "Failed to create checkout for subscription %s.",
            subscription.id,
        )
        messages.error(
            request,
            "Não foi possível iniciar o pagamento. "
            "Tente novamente em instantes.",
        )
        return redirect("home")

    checkout_id = checkout_data["id"]
    checkout_url = checkout_data["url"]

    subscription.provider_checkout_id = checkout_id
    subscription.provider_checkout_url = checkout_url

    if (
        provider == PROVIDER_MERCADO_PAGO
        and plan.billing_type == BillingPlan.TYPE_MONTHLY
    ):
        subscription.provider_subscription_id = (
            checkout_data.get("subscription_id", checkout_id)
        )

    subscription.save(
        update_fields=[
            "provider_checkout_id",
            "provider_checkout_url",
            "provider_subscription_id",
            "updated_at",
        ],
    )

    return redirect(checkout_url)


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
        logger.warning(
            "Rejected Mercado Pago webhook with invalid signature.",
        )
        return HttpResponse(status=401)

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {"error": "Invalid JSON payload."},
            status=400,
        )

    if not isinstance(payload, dict):
        return JsonResponse(
            {"error": "Invalid webhook payload."},
            status=400,
        )

    event_type = str(
        payload.get("action") or payload.get("type") or "unknown"
    )

    data = payload.get("data")
    if not isinstance(data, dict):
        data = {}

    order_id = str(data.get("id") or data_id)

    if not order_id:
        return JsonResponse(
            {"error": "Missing webhook order ID."},
            status=400,
        )

    event_id = str(
        payload.get("id") or f"{event_type}:{order_id}"
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
            ],
        )
        return HttpResponse(status=200)

    event.status = MercadoPagoWebhookEvent.STATUS_PROCESSING
    event.error_message = ""
    event.save(
        update_fields=["status", "error_message"],
    )

    try:
        process_mercado_pago_order(order_id)
    except MercadoPagoError as exc:
        event.status = MercadoPagoWebhookEvent.STATUS_FAILED
        event.error_message = str(exc)[:2000]
        event.save(
            update_fields=["status", "error_message"],
        )
        logger.exception("Mercado Pago order processing failed.")
        return HttpResponse(status=500)
    except MercadoPagoWebhookProcessingError as exc:
        event.status = MercadoPagoWebhookEvent.STATUS_FAILED
        event.error_message = str(exc)[:2000]
        event.save(
            update_fields=["status", "error_message"],
        )
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
        ],
    )

    return HttpResponse(status=200)
