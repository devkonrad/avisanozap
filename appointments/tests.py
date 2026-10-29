from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.models import (
    Appointment,
    ProfessionalProfile,
    ReminderTestConfiguration,
    WhatsAppReminder,
)
from appointments.tasks import (
    process_pending_reminders,
    send_reminder_test_message,
)
from billing.models import Subscription


class SignUpSubscriptionTests(TestCase):
    def setUp(self):
        self.signup_url = reverse("accounts:signup")

    def signup_data(self, email="customer@example.com"):
        return {
            "username": "newcustomer",
            "first_name": "New Customer",
            "email": email,
            "whatsapp_number": "11999999999",
            "slug": "new-customer",
            "password1": "SafeTestPassword123!",
            "password2": "SafeTestPassword123!",
        }

    def create_subscription(
        self,
        *,
        email="customer@example.com",
        status=Subscription.STATUS_ACTIVE,
        professional=None,
    ):
        return Subscription.objects.create(
            customer_email=email,
            plan=Subscription.PLAN_PIX,
            status=status,
            amount=Decimal("29.90"),
            professional=professional,
        )

    def test_active_subscription_is_linked_after_signup(self):
        subscription = self.create_subscription()

        response = self.client.post(
            self.signup_url,
            {
                **self.signup_data(),
                "subscription": str(subscription.pk),
            },
        )

        self.assertRedirects(
            response,
            reverse("appointments_dashboard"),
            fetch_redirect_response=False,
        )

        user = User.objects.get(username="newcustomer")
        profile = ProfessionalProfile.objects.get(user=user)

        subscription.refresh_from_db()

        self.assertEqual(subscription.professional, profile)
        self.assertEqual(profile.user.email, subscription.customer_email)
        self.assertIn("_auth_user_id", self.client.session)

    def test_pending_subscription_does_not_allow_signup(self):
        subscription = self.create_subscription(
            status=Subscription.STATUS_PENDING,
        )

        response = self.client.post(
            self.signup_url,
            {
                **self.signup_data(),
                "subscription": str(subscription.pk),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            User.objects.filter(username="newcustomer").exists()
        )

        subscription.refresh_from_db()
        self.assertIsNone(subscription.professional)

    def test_different_email_does_not_allow_subscription_link(self):
        subscription = self.create_subscription()

        response = self.client.post(
            self.signup_url,
            {
                **self.signup_data(email="other@example.com"),
                "subscription": str(subscription.pk),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            User.objects.filter(username="newcustomer").exists()
        )

        subscription.refresh_from_db()
        self.assertIsNone(subscription.professional)

    def test_already_linked_subscription_cannot_be_reused(self):
        existing_user = User.objects.create_user(
            username="existingcustomer",
            email="existing@example.com",
            password="SafeTestPassword123!",
        )
        existing_profile = ProfessionalProfile.objects.create(
            user=existing_user,
            whatsapp_number="11988888888",
            slug="existing-customer",
        )
        subscription = self.create_subscription(
            professional=existing_profile,
        )

        response = self.client.post(
            self.signup_url,
            {
                **self.signup_data(),
                "subscription": str(subscription.pk),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            User.objects.filter(username="newcustomer").exists()
        )

        subscription.refresh_from_db()
        self.assertEqual(subscription.professional, existing_profile)

    def test_signup_without_subscription_still_works(self):
        response = self.client.post(
            self.signup_url,
            self.signup_data(),
        )

        self.assertRedirects(
            response,
            reverse("appointments_dashboard"),
            fetch_redirect_response=False,
        )

        user = User.objects.get(username="newcustomer")
        self.assertTrue(
            ProfessionalProfile.objects.filter(user=user).exists()
        )
        self.assertIn("_auth_user_id", self.client.session)


class ReminderTestConfigurationTaskTests(TestCase):
    def setUp(self):
        self.configuration = ReminderTestConfiguration.objects.create(
            enabled=True,
            destination_phone="11999999999",
            interval_minutes=15,
        )

    @patch("appointments.tasks.send_whatsapp_message", return_value=True)
    def test_sends_test_message_when_enabled_and_due(self, send_message):
        result = send_reminder_test_message()

        self.configuration.refresh_from_db()

        self.assertEqual(result, "Test message sent successfully.")
        send_message.assert_called_once()
        self.assertEqual(
            send_message.call_args.kwargs["number"],
            "11999999999",
        )
        self.assertIn(
            "Teste de lembretes do AvisanoZap",
            send_message.call_args.kwargs["text"],
        )
        self.assertIsNotNone(self.configuration.last_attempt_at)
        self.assertIsNotNone(self.configuration.last_success_at)
        self.assertEqual(
            self.configuration.last_result,
            "Mensagem de teste enviada com sucesso.",
        )

    @patch("appointments.tasks.send_whatsapp_message")
    def test_does_not_send_when_disabled(self, send_message):
        self.configuration.enabled = False
        self.configuration.save(update_fields=["enabled"])

        result = send_reminder_test_message()

        self.assertEqual(result, "Periodic reminder test is disabled.")
        send_message.assert_not_called()

    @patch("appointments.tasks.send_whatsapp_message")
    def test_waits_until_configured_interval_has_elapsed(self, send_message):
        self.configuration.last_attempt_at = (
            timezone.now() - timedelta(minutes=5)
        )
        self.configuration.save(update_fields=["last_attempt_at"])

        result = send_reminder_test_message()

        self.assertEqual(result, "Periodic reminder test is not due yet.")
        send_message.assert_not_called()

    @patch("appointments.tasks.send_whatsapp_message", return_value=False)
    def test_records_failed_test_message(self, send_message):
        result = send_reminder_test_message()

        self.configuration.refresh_from_db()

        self.assertEqual(result, "Test message failed.")
        send_message.assert_called_once()
        self.assertIsNotNone(self.configuration.last_attempt_at)
        self.assertIsNone(self.configuration.last_success_at)
        self.assertIn("Falha no envio", self.configuration.last_result)

    @patch("appointments.tasks.send_whatsapp_message")
    def test_does_not_send_without_destination(self, send_message):
        self.configuration.destination_phone = ""
        self.configuration.save(update_fields=["destination_phone"])

        result = send_reminder_test_message()

        self.configuration.refresh_from_db()

        self.assertIn("WhatsApp de destino", result)
        self.assertEqual(self.configuration.last_result, result)
        send_message.assert_not_called()


class ProcessPendingRemindersTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(
            username="reminderprofessional",
            email="professional@example.com",
            password="SafeTestPassword123!",
        )
        self.professional = ProfessionalProfile.objects.create(
            user=user,
            whatsapp_number="11988888888",
            slug="reminder-professional",
        )
        now = timezone.now()
        self.appointment = Appointment.objects.create(
            professional=self.professional,
            client_name="Test Client",
            client_whatsapp="11999999999",
            start_datetime=now + timedelta(hours=2),
            end_datetime=now + timedelta(hours=2, minutes=30),
            status=Appointment.STATUS_CONFIRMED,
        )
        self.reminder = WhatsAppReminder.objects.create(
            appointment=self.appointment,
            scheduled_for=now - timedelta(minutes=1),
            reminder_type="2H",
            status="PENDING",
        )

    @patch("appointments.tasks.send_whatsapp_message", return_value=True)
    def test_sends_due_reminder_and_marks_it_sent(self, send_message):
        process_pending_reminders()

        self.reminder.refresh_from_db()

        self.assertEqual(self.reminder.status, "SENT")
        self.assertIsNotNone(self.reminder.sent_at)
        send_message.assert_called_once_with(
            number=self.appointment.client_whatsapp,
            text=send_message.call_args.kwargs["text"],
        )
        self.assertIn(
            "Test Client",
            send_message.call_args.kwargs["text"],
        )

    @patch("appointments.tasks.send_whatsapp_message", return_value=False)
    def test_marks_reminder_failed_when_send_fails(self, send_message):
        process_pending_reminders()

        self.reminder.refresh_from_db()

        self.assertEqual(self.reminder.status, "FAILED")
        self.assertIsNone(self.reminder.sent_at)
        send_message.assert_called_once()

    @patch("appointments.tasks.send_whatsapp_message")
    def test_does_not_send_reminder_before_scheduled_time(self, send_message):
        self.reminder.scheduled_for = timezone.now() + timedelta(minutes=10)
        self.reminder.save(update_fields=["scheduled_for"])

        process_pending_reminders()

        self.reminder.refresh_from_db()

        self.assertEqual(self.reminder.status, "PENDING")
        send_message.assert_not_called()
