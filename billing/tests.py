import hashlib
import hmac
import json
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from appointments.models import ProfessionalProfile
from billing.models import (
    PROVIDER_ASAAS,
    PROVIDER_MERCADO_PAGO,
    BillingPlan,
    BillingSettings,
    MercadoPagoWebhookEvent,
    Payment,
    Subscription,
)
from billing.services.asaas import AsaasError
from billing.services.mercado_pago import (
    MercadoPagoError,
    create_checkout,
    create_monthly_checkout,
    create_pix_checkout,
    get_order,
    get_payment,
    get_preapproval,
)
from billing.services.mercado_pago_webhooks import (
    MercadoPagoWebhookProcessingError,
    process_mercado_pago_order,
)


class CheckoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="professional",
            email="professional@example.com",
            password="test-password",
        )
        self.profile = ProfessionalProfile.objects.create(
            user=self.user,
            whatsapp_number="5511999999999",
            slug="professional",
        )
        self.pix_plan = BillingPlan.objects.create(
            code="pix-plan",
            name="Plano Pix",
            description="Acesso por 30 dias",
            amount=Decimal("49.90"),
            billing_type=BillingPlan.TYPE_ONE_TIME,
            payment_method=BillingPlan.PAYMENT_PIX,
            access_days=30,
        )
        self.monthly_plan = BillingPlan.objects.create(
            code="monthly-plan",
            name="Plano Mensal",
            amount=Decimal("79.90"),
            billing_type=BillingPlan.TYPE_MONTHLY,
            payment_method=BillingPlan.PAYMENT_CREDIT_CARD,
        )
        self.client.force_login(self.user)

    def checkout_url(self, plan=None):
        plan = plan or self.pix_plan
        return reverse(
            "billing:checkout",
            kwargs={"plan_code": plan.code},
        )

    def configure_provider(self, provider):
        BillingSettings.objects.update_or_create(
            pk=1,
            defaults={"checkout_provider": provider},
        )

    def create_subscription(
        self,
        *,
        plan=None,
        provider=PROVIDER_ASAAS,
        status=Subscription.STATUS_PENDING,
        checkout_id=None,
        checkout_url="",
    ):
        plan = plan or self.pix_plan

        return Subscription.objects.create(
            professional=self.profile,
            plan=(
                Subscription.PLAN_MONTHLY
                if plan.billing_type == BillingPlan.TYPE_MONTHLY
                else Subscription.PLAN_PIX
            ),
            billing_plan=plan,
            amount=plan.amount,
            provider=provider,
            status=status,
            provider_checkout_id=checkout_id,
            provider_checkout_url=checkout_url,
        )

    @patch("billing.views.create_asaas_checkout")
    def test_creates_asaas_checkout(self, create_checkout_mock):
        self.configure_provider(PROVIDER_ASAAS)
        create_checkout_mock.return_value = {
            "id": "asaas-checkout-123",
            "url": "https://asaas.example/checkout/123",
        }

        response = self.client.post(self.checkout_url())

        subscription = Subscription.objects.get(
            professional=self.profile,
        )

        self.assertRedirects(
            response,
            "https://asaas.example/checkout/123",
            fetch_redirect_response=False,
        )
        self.assertEqual(subscription.provider, PROVIDER_ASAAS)
        self.assertEqual(
            subscription.provider_checkout_id,
            "asaas-checkout-123",
        )
        self.assertEqual(
            subscription.provider_checkout_url,
            "https://asaas.example/checkout/123",
        )
        create_checkout_mock.assert_called_once_with(
            subscription=subscription,
            plan=self.pix_plan,
            callback_url="http://testserver/",
        )

    @patch("billing.views.create_mercado_pago_checkout")
    def test_creates_mercado_pago_pix_checkout(
        self,
        create_checkout_mock,
    ):
        self.configure_provider(PROVIDER_MERCADO_PAGO)
        create_checkout_mock.return_value = {
            "id": "mp-order-123",
            "url": "https://mercadopago.example/checkout/123",
        }

        response = self.client.post(self.checkout_url())

        subscription = Subscription.objects.get(
            professional=self.profile,
        )

        self.assertRedirects(
            response,
            "https://mercadopago.example/checkout/123",
            fetch_redirect_response=False,
        )
        self.assertEqual(
            subscription.provider,
            PROVIDER_MERCADO_PAGO,
        )
        self.assertEqual(
            subscription.provider_checkout_id,
            "mp-order-123",
        )
        self.assertEqual(
            subscription.provider_checkout_url,
            "https://mercadopago.example/checkout/123",
        )
        create_checkout_mock.assert_called_once_with(
            subscription=subscription,
            plan=self.pix_plan,
            callback_url="http://testserver/",
            payer_email=self.user.email,
        )

    @patch("billing.views.create_mercado_pago_checkout")
    def test_creates_mercado_pago_monthly_checkout(
        self,
        create_checkout_mock,
    ):
        self.configure_provider(PROVIDER_MERCADO_PAGO)
        create_checkout_mock.return_value = {
            "id": "mp-subscription-123",
            "subscription_id": "mp-subscription-123",
            "url": "https://mercadopago.example/subscription/123",
        }

        response = self.client.post(
            self.checkout_url(self.monthly_plan),
        )

        subscription = Subscription.objects.get(
            professional=self.profile,
        )

        self.assertRedirects(
            response,
            "https://mercadopago.example/subscription/123",
            fetch_redirect_response=False,
        )
        self.assertEqual(
            subscription.provider_subscription_id,
            "mp-subscription-123",
        )
        self.assertEqual(
            subscription.provider_checkout_id,
            "mp-subscription-123",
        )
        create_checkout_mock.assert_called_once()

    @patch("billing.views.create_asaas_checkout")
    def test_reuses_existing_checkout(self, create_checkout_mock):
        self.create_subscription(
            checkout_id="existing-checkout",
            checkout_url="https://asaas.example/existing",
        )

        response = self.client.post(self.checkout_url())

        self.assertRedirects(
            response,
            "https://asaas.example/existing",
            fetch_redirect_response=False,
        )
        create_checkout_mock.assert_not_called()

    @patch("billing.views.create_mercado_pago_checkout")
    def test_pending_subscription_keeps_its_original_provider(
        self,
        create_checkout_mock,
    ):
        self.configure_provider(PROVIDER_MERCADO_PAGO)
        subscription = self.create_subscription(
            provider=PROVIDER_ASAAS,
        )

        with patch(
            "billing.views.create_asaas_checkout",
            return_value={
                "id": "asaas-checkout-456",
                "url": "https://asaas.example/checkout/456",
            },
        ) as create_asaas_checkout_mock:
            response = self.client.post(self.checkout_url())

        self.assertRedirects(
            response,
            "https://asaas.example/checkout/456",
            fetch_redirect_response=False,
        )
        create_asaas_checkout_mock.assert_called_once()
        create_checkout_mock.assert_not_called()

        subscription.refresh_from_db()
        self.assertEqual(subscription.provider, PROVIDER_ASAAS)

    @patch("billing.views.create_asaas_checkout")
    def test_checkout_failure_keeps_subscription_pending(
        self,
        create_checkout_mock,
    ):
        self.configure_provider(PROVIDER_ASAAS)
        create_checkout_mock.side_effect = AsaasError("API unavailable")

        response = self.client.post(self.checkout_url())

        subscription = Subscription.objects.get(
            professional=self.profile,
        )

        self.assertRedirects(
            response,
            reverse("home"),
            fetch_redirect_response=False,
        )
        self.assertEqual(
            subscription.status,
            Subscription.STATUS_PENDING,
        )
        self.assertFalse(subscription.provider_checkout_url)

    @patch("billing.views.create_mercado_pago_checkout")
    def test_mercado_pago_failure_keeps_subscription_pending(
        self,
        create_checkout_mock,
    ):
        self.configure_provider(PROVIDER_MERCADO_PAGO)
        create_checkout_mock.side_effect = MercadoPagoError(
            "API unavailable",
        )

        response = self.client.post(self.checkout_url())

        subscription = Subscription.objects.get(
            professional=self.profile,
        )

        self.assertRedirects(
            response,
            reverse("home"),
            fetch_redirect_response=False,
        )
        self.assertEqual(
            subscription.status,
            Subscription.STATUS_PENDING,
        )
        self.assertFalse(subscription.provider_checkout_url)

    def test_active_subscription_cannot_start_another_checkout(self):
        self.create_subscription(status=Subscription.STATUS_ACTIVE)

        response = self.client.post(self.checkout_url())

        self.assertRedirects(
            response,
            reverse("home"),
            fetch_redirect_response=False,
        )
        self.assertEqual(
            Subscription.objects.filter(
                professional=self.profile,
            ).count(),
            1,
        )

    def test_pending_subscription_cannot_change_plan(self):
        self.create_subscription()

        response = self.client.post(
            self.checkout_url(self.monthly_plan),
        )

        self.assertRedirects(
            response,
            reverse("home"),
            fetch_redirect_response=False,
        )
        self.assertEqual(
            Subscription.objects.filter(
                professional=self.profile,
            ).count(),
            1,
        )

    def test_get_renders_checkout_confirmation(self):
        response = self.client.get(self.checkout_url())

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "billing/checkout_confirm.html",
        )


@override_settings(MERCADO_PAGO_ACCESS_TOKEN="test-access-token")
class MercadoPagoServiceTests(SimpleTestCase):
    def setUp(self):
        self.subscription = SimpleNamespace(
            id="subscription-test-123",
            amount=Decimal("49.90"),
        )
        self.pix_plan = SimpleNamespace(
            name="Plano Pix",
            description="Acesso por 30 dias",
            billing_type="ONE_TIME",
        )
        self.monthly_plan = SimpleNamespace(
            name="Plano Mensal",
            description="",
            billing_type="MONTHLY",
        )
        self.callback_url = "https://avisanozap.example/checkout/"
        self.payer_email = "professional@example.com"

    def mock_api_response(self, data, status_code=201):
        response = Mock()
        response.status_code = status_code
        response.json.return_value = data
        response.raise_for_status.return_value = None
        return response

    @patch("billing.services.mercado_pago.requests.request")
    def test_creates_pix_checkout(self, request_mock):
        request_mock.return_value = self.mock_api_response({
            "id": "order-123",
            "checkout_url": "https://mp.example/checkout/123",
        })

        result = create_pix_checkout(
            self.subscription,
            self.pix_plan,
            self.callback_url,
            self.payer_email,
        )

        self.assertEqual(
            result,
            {
                "id": "order-123",
                "url": "https://mp.example/checkout/123",
            },
        )

        request_mock.assert_called_once()
        args = request_mock.call_args

        self.assertEqual(
            args.args,
            ("POST", "https://api.mercadopago.com/v1/orders"),
        )
        self.assertEqual(
            args.kwargs["headers"]["Authorization"],
            "Bearer test-access-token",
        )
        self.assertEqual(
            args.kwargs["headers"]["X-Idempotency-Key"],
            str(self.subscription.id),
        )

        payload = args.kwargs["json"]
        self.assertEqual(payload["total_amount"], "49.90")
        self.assertEqual(
            payload["external_reference"],
            str(self.subscription.id),
        )
        self.assertEqual(payload["payer"]["email"], self.payer_email)
        self.assertEqual(payload["items"][0]["unit_price"], "49.90")

    @patch("billing.services.mercado_pago.requests.request")
    def test_creates_monthly_checkout(self, request_mock):
        request_mock.return_value = self.mock_api_response({
            "id": "preapproval-123",
            "init_point": "https://mp.example/subscription/123",
        })

        result = create_monthly_checkout(
            self.subscription,
            self.monthly_plan,
            self.callback_url,
            self.payer_email,
        )

        self.assertEqual(
            result,
            {
                "id": "preapproval-123",
                "url": "https://mp.example/subscription/123",
                "subscription_id": "preapproval-123",
            },
        )

        args = request_mock.call_args
        self.assertEqual(
            args.args,
            ("POST", "https://api.mercadopago.com/preapproval"),
        )
        payload = args.kwargs["json"]
        self.assertEqual(payload["payer_email"], self.payer_email)
        self.assertEqual(
            payload["auto_recurring"]["transaction_amount"],
            49.9,
        )
        self.assertEqual(
            payload["auto_recurring"]["frequency_type"],
            "months",
        )

    @patch("billing.services.mercado_pago.requests.request")
    def test_create_checkout_selects_pix(self, request_mock):
        request_mock.return_value = self.mock_api_response({
            "id": "order-123",
            "checkout_url": "https://mp.example/checkout/123",
        })

        result = create_checkout(
            self.subscription,
            self.pix_plan,
            self.callback_url,
            self.payer_email,
        )

        self.assertEqual(result["id"], "order-123")
        self.assertEqual(
            request_mock.call_args.args[1],
            "https://api.mercadopago.com/v1/orders",
        )

    @patch("billing.services.mercado_pago.requests.request")
    def test_create_checkout_selects_monthly(self, request_mock):
        request_mock.return_value = self.mock_api_response({
            "id": "preapproval-123",
            "init_point": "https://mp.example/subscription/123",
        })

        result = create_checkout(
            self.subscription,
            self.monthly_plan,
            self.callback_url,
            self.payer_email,
        )

        self.assertEqual(result["subscription_id"], "preapproval-123")
        self.assertEqual(
            request_mock.call_args.args[1],
            "https://api.mercadopago.com/preapproval",
        )

    def test_rejects_missing_payer_email(self):
        with self.assertRaisesMessage(
            MercadoPagoError,
            "The customer must have an email address",
        ):
            create_checkout(
                self.subscription,
                self.pix_plan,
                self.callback_url,
                "",
            )

    @override_settings(MERCADO_PAGO_ACCESS_TOKEN="")
    def test_rejects_missing_access_token(self):
        with self.assertRaisesMessage(
            MercadoPagoError,
            "MERCADO_PAGO_ACCESS_TOKEN is not configured",
        ):
            create_pix_checkout(
                self.subscription,
                self.pix_plan,
                self.callback_url,
                self.payer_email,
            )

    @patch("billing.services.mercado_pago.requests.request")
    def test_rejects_pix_response_without_checkout_url(
        self,
        request_mock,
    ):
        request_mock.return_value = self.mock_api_response({
            "id": "order-123",
        })

        with self.assertRaisesMessage(
            MercadoPagoError,
            "did not return an order ID and checkout URL",
        ):
            create_pix_checkout(
                self.subscription,
                self.pix_plan,
                self.callback_url,
                self.payer_email,
            )

    @patch("billing.services.mercado_pago.requests.request")
    def test_wraps_api_errors(self, request_mock):
        request_mock.side_effect = requests.ConnectionError(
            "Connection failed",
        )

        with self.assertRaisesMessage(
            MercadoPagoError,
            "Mercado Pago API request failed",
        ):
            create_pix_checkout(
                self.subscription,
                self.pix_plan,
                self.callback_url,
                self.payer_email,
            )


class MercadoPagoWebhookTests(TestCase):
    SECRET = "test-webhook-secret"
    REQUEST_ID = "request-123"
    DATA_ID = "order-456"
    EVENT_ID = "event-789"

    def setUp(self):
        self.url = reverse("billing:mercado_pago_webhook")
        self.payload = {
            "id": self.EVENT_ID,
            "type": "order",
            "action": "order.updated",
            "data": {"id": self.DATA_ID},
        }

    def make_signature(self, data_id=None, request_id=None):
        data_id = data_id or self.DATA_ID
        request_id = (
            self.REQUEST_ID if request_id is None else request_id
        )
        timestamp = "1729000000"

        manifest = f"id:{data_id.lower()};"
        if request_id:
            manifest += f"request-id:{request_id};"
        manifest += f"ts:{timestamp};"

        signature = hmac.new(
            self.SECRET.encode("utf-8"),
            manifest.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return f"ts={timestamp},v1={signature}"

    def post_webhook(self, signature=None, payload=None):
        signature = signature or self.make_signature()
        payload = self.payload if payload is None else payload

        return self.client.post(
            f"{self.url}?data.id={self.DATA_ID}",
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_SIGNATURE=signature,
            HTTP_X_REQUEST_ID=self.REQUEST_ID,
        )

    @override_settings(MERCADO_PAGO_WEBHOOK_SECRET=SECRET)
    @patch("billing.views.process_mercado_pago_order")
    def test_valid_signature_stores_event(self, mock_process):
        mock_process.return_value = True

        response = self.post_webhook()

        self.assertEqual(response.status_code, 200)
        mock_process.assert_called_once_with(self.DATA_ID)

        self.assertTrue(
            MercadoPagoWebhookEvent.objects.filter(
                event_id=self.EVENT_ID,
                event_type="order.updated",
                status=MercadoPagoWebhookEvent.STATUS_PROCESSED,
            ).exists()
        )

    @override_settings(MERCADO_PAGO_WEBHOOK_SECRET=SECRET)
    def test_invalid_signature_is_rejected(self):
        response = self.post_webhook(
            signature="ts=1729000000,v1=invalid",
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            MercadoPagoWebhookEvent.objects.count(),
            0,
        )

    @override_settings(MERCADO_PAGO_WEBHOOK_SECRET=SECRET)
    @patch("billing.views.process_mercado_pago_order")
    def test_duplicate_event_is_stored_once(self, mock_process):
        first_response = self.post_webhook()
        second_response = self.post_webhook()

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)

        self.assertEqual(
            MercadoPagoWebhookEvent.objects.filter(
                event_id=self.EVENT_ID,
            ).count(),
            1,
        )
        mock_process.assert_called_once_with(self.DATA_ID)

    @override_settings(MERCADO_PAGO_WEBHOOK_SECRET="")
    def test_missing_secret_returns_service_unavailable(self):
        response = self.post_webhook()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            MercadoPagoWebhookEvent.objects.count(),
            0,
        )

    @override_settings(MERCADO_PAGO_WEBHOOK_SECRET=SECRET)
    def test_invalid_json_is_rejected(self):
        response = self.client.post(
            f"{self.url}?data.id={self.DATA_ID}",
            data="{invalid-json",
            content_type="application/json",
            HTTP_X_SIGNATURE=self.make_signature(),
            HTTP_X_REQUEST_ID=self.REQUEST_ID,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            MercadoPagoWebhookEvent.objects.count(),
            0,
        )

    @override_settings(MERCADO_PAGO_WEBHOOK_SECRET=SECRET)
    def test_missing_event_id_is_rejected(self):
        response = self.post_webhook(payload={"type": "order"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            MercadoPagoWebhookEvent.objects.count(),
            0,
        )

    @override_settings(MERCADO_PAGO_WEBHOOK_SECRET=SECRET)
    def test_non_post_request_is_rejected(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 405)

    @patch("billing.services.mercado_pago._request")
    def test_get_order(self, mock_request):
        mock_request.return_value = {"id": "order-123"}

        result = get_order("order-123")

        self.assertEqual(result, {"id": "order-123"})
        mock_request.assert_called_once_with(
            "GET",
            "/v1/orders/order-123",
        )

    @patch("billing.services.mercado_pago._request")
    def test_get_payment(self, mock_request):
        mock_request.return_value = {
            "id": "payment-123",
            "status": "approved",
        }

        result = get_payment("payment-123")

        self.assertEqual(result["status"], "approved")
        mock_request.assert_called_once_with(
            "GET",
            "/v1/payments/payment-123",
        )

    @patch("billing.services.mercado_pago._request")
    def test_get_preapproval(self, mock_request):
        mock_request.return_value = {
            "id": "preapproval-123",
            "status": "authorized",
        }

        result = get_preapproval("preapproval-123")

        self.assertEqual(result["status"], "authorized")
        mock_request.assert_called_once_with(
            "GET",
            "/preapproval/preapproval-123",
        )

    def test_get_order_requires_id(self):
        with self.assertRaises(MercadoPagoError):
            get_order("")

    def test_get_payment_requires_id(self):
        with self.assertRaises(MercadoPagoError):
            get_payment("")

    def test_get_preapproval_requires_id(self):
        with self.assertRaises(MercadoPagoError):
            get_preapproval("")


class MercadoPagoOrderProcessingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="mp-professional",
            email="mp-professional@example.com",
            password="test-password",
        )
        self.profile = ProfessionalProfile.objects.create(
            user=self.user,
            whatsapp_number="5511999999999",
            slug="mp-professional",
        )
        self.plan = BillingPlan.objects.create(
            code="mp-pix-plan",
            name="Plano Pix",
            amount=Decimal("49.90"),
            billing_type=BillingPlan.TYPE_ONE_TIME,
            payment_method=BillingPlan.PAYMENT_PIX,
            access_days=30,
        )
        self.subscription = Subscription.objects.create(
            professional=self.profile,
            plan=Subscription.PLAN_PIX,
            billing_plan=self.plan,
            amount=Decimal("49.90"),
            provider=PROVIDER_MERCADO_PAGO,
            status=Subscription.STATUS_PENDING,
            provider_checkout_id="order-456",
        )
        self.order = {
            "id": "order-456",
            "external_reference": str(self.subscription.id),
            "status": "processed",
            "status_detail": "accredited",
            "total_amount": "49.90",
            "transactions": {
                "payments": [
                    {
                        "id": "payment-123",
                        "amount": "49.90",
                        "paid_amount": "49.90",
                        "status": "processed",
                        "status_detail": "accredited",
                    }
                ]
            },
        }

    @patch("billing.services.mercado_pago_webhooks.get_order")
    def test_credited_order_activates_subscription(self, mock_get_order):
        mock_get_order.return_value = self.order

        process_mercado_pago_order("order-456")

        self.subscription.refresh_from_db()
        payment = Payment.objects.get(
            provider=PROVIDER_MERCADO_PAGO,
            provider_payment_id="payment-123",
        )

        self.assertEqual(
            self.subscription.status,
            Subscription.STATUS_ACTIVE,
        )
        self.assertIsNotNone(self.subscription.started_at)
        self.assertIsNotNone(self.subscription.expires_at)
        self.assertEqual(
            self.subscription.expires_at - self.subscription.started_at,
            timedelta(days=30),
        )
        self.assertEqual(payment.status, Payment.STATUS_CONFIRMED)
        self.assertEqual(payment.amount, Decimal("49.90"))

        mock_get_order.assert_called_once_with("order-456")

    @patch("billing.services.mercado_pago_webhooks.get_order")
    def test_pending_order_does_not_activate_subscription(
        self,
        mock_get_order,
    ):
        self.order["status"] = "pending"
        self.order["status_detail"] = "pending"
        mock_get_order.return_value = self.order

        result = process_mercado_pago_order("order-456")

        self.subscription.refresh_from_db()

        self.assertFalse(result)
        self.assertEqual(
            self.subscription.status,
            Subscription.STATUS_PENDING,
        )
        self.assertEqual(Payment.objects.count(), 0)

    @patch("billing.services.mercado_pago_webhooks.get_order")
    def test_amount_mismatch_does_not_activate_subscription(
        self,
        mock_get_order,
    ):
        self.order["total_amount"] = "39.90"
        mock_get_order.return_value = self.order

        with self.assertRaises(MercadoPagoWebhookProcessingError):
            process_mercado_pago_order("order-456")

        self.subscription.refresh_from_db()

        self.assertEqual(
            self.subscription.status,
            Subscription.STATUS_PENDING,
        )
        self.assertEqual(Payment.objects.count(), 0)

    @patch("billing.services.mercado_pago_webhooks.get_order")
    def test_duplicate_processing_does_not_extend_access(
        self,
        mock_get_order,
    ):
        mock_get_order.return_value = self.order

        process_mercado_pago_order("order-456")

        self.subscription.refresh_from_db()
        original_started_at = self.subscription.started_at
        original_expires_at = self.subscription.expires_at

        process_mercado_pago_order("order-456")

        self.subscription.refresh_from_db()

        self.assertEqual(
            self.subscription.started_at,
            original_started_at,
        )
        self.assertEqual(
            self.subscription.expires_at,
            original_expires_at,
        )
        self.assertEqual(Payment.objects.count(), 1)
