from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from .models import Prospect, ProspectInteraction
from .services import (
    PROSPECT_OFFER_MESSAGE,
    process_prospect_reply,
)


class ProcessProspectReplyTests(TestCase):
    def setUp(self):
        self.phone = "5551993727450"

        self.prospect = Prospect.objects.create(
            business_name="Salão Teste",
            phone_number=self.phone,
            phone_status=Prospect.PhoneStatus.WHATSAPP_CONFIRMED,
            sales_status=Prospect.SalesStatus.FIRST_CONTACT_SENT,
            whatsapp_opt_in_at=timezone.now(),
        )

    @patch("prospects.services.send_whatsapp_message", return_value=True)
    def test_positive_reply_sends_offer(self, send_message):
        result = process_prospect_reply(
            phone=self.phone,
            message="SIM",
            provider_message_id="message-positive-1",
        )

        self.prospect.refresh_from_db()

        self.assertEqual(result, "offer_sent")
        self.assertEqual(
            self.prospect.sales_status,
            Prospect.SalesStatus.OFFER_SENT,
        )

        send_message.assert_called_once_with(
            number=self.phone,
            text=PROSPECT_OFFER_MESSAGE,
        )

        self.assertEqual(
            self.prospect.interactions.count(),
            2,
        )

        self.assertTrue(
            self.prospect.interactions.filter(
                interaction_type=(
                    ProspectInteraction.InteractionType.POSITIVE_REPLY
                ),
                direction=ProspectInteraction.Direction.INBOUND,
            ).exists()
        )

        self.assertTrue(
            self.prospect.interactions.filter(
                interaction_type=(
                    ProspectInteraction.InteractionType.OFFER_SENT
                ),
                direction=ProspectInteraction.Direction.OUTBOUND,
            ).exists()
        )

    @patch("prospects.services.send_whatsapp_message", return_value=True)
    def test_negative_reply_blocks_future_contact(self, send_message):
        result = process_prospect_reply(
            phone=self.phone,
            message="NÃO",
            provider_message_id="message-negative-1",
        )

        self.prospect.refresh_from_db()

        self.assertEqual(result, "declined")
        self.assertEqual(
            self.prospect.sales_status,
            Prospect.SalesStatus.DECLINED,
        )
        self.assertIsNotNone(self.prospect.opt_out_at)
        self.assertFalse(self.prospect.can_receive_whatsapp)

        send_message.assert_not_called()

        self.assertEqual(self.prospect.interactions.count(), 1)

    @patch("prospects.services.send_whatsapp_message")
    def test_ambiguous_reply_does_not_send_offer(self, send_message):
        result = process_prospect_reply(
            phone=self.phone,
            message="Talvez mais tarde",
            provider_message_id="message-other-1",
        )

        self.prospect.refresh_from_db()

        self.assertEqual(result, "unrecognized")
        self.assertEqual(
            self.prospect.sales_status,
            Prospect.SalesStatus.FIRST_CONTACT_SENT,
        )

        send_message.assert_not_called()

        interaction = self.prospect.interactions.get()
        self.assertEqual(
            interaction.interaction_type,
            ProspectInteraction.InteractionType.OTHER,
        )
        self.assertEqual(interaction.message, "Talvez mais tarde")

    @patch("prospects.services.send_whatsapp_message", return_value=True)
    def test_duplicate_reply_does_not_send_offer_twice(self, send_message):
        first_result = process_prospect_reply(
            phone=self.phone,
            message="SIM",
            provider_message_id="message-duplicate-1",
        )

        second_result = process_prospect_reply(
            phone=self.phone,
            message="SIM",
            provider_message_id="message-duplicate-1",
        )

        self.assertEqual(first_result, "offer_sent")
        self.assertEqual(second_result, "not_waiting_for_reply")

        send_message.assert_called_once()

        self.assertEqual(
            self.prospect.interactions.filter(
                interaction_type=(
                    ProspectInteraction.InteractionType.OFFER_SENT
                ),
            ).count(),
            1,
        )

    @patch("prospects.services.send_whatsapp_message", return_value=False)
    def test_failed_offer_keeps_prospect_interested(self, send_message):
        result = process_prospect_reply(
            phone=self.phone,
            message="SIM",
            provider_message_id="message-failed-1",
        )

        self.prospect.refresh_from_db()

        self.assertEqual(result, "offer_failed")
        self.assertEqual(
            self.prospect.sales_status,
            Prospect.SalesStatus.INTERESTED,
        )

        send_message.assert_called_once()

        self.assertFalse(
            self.prospect.interactions.filter(
                interaction_type=(
                    ProspectInteraction.InteractionType.OFFER_SENT
                ),
            ).exists()
        )
