from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from appointments.models import ProfessionalProfile
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
