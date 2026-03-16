import unittest
from unittest.mock import Mock, patch

from src.checkout import ChargeResult, CheckoutService
from src.models import CartItem, Order
from src.pricing import PricingError, PricingService


class TestCheckoutService(unittest.TestCase):
    def setUp(self):
        self.payments = Mock()
        self.email = Mock()
        self.fraud = Mock()
        self.repo = Mock()
        self.pricing = Mock()
        self.service = CheckoutService(
            payments=self.payments,
            email=self.email,
            fraud=self.fraud,
            repo=self.repo,
            pricing=self.pricing,
        )

    def test_checkout_rejects_blank_users_without_touching_dependencies(self):
        result = self.service.checkout("   ", [], "tok_test", "CL")

        self.assertEqual(result, "INVALID_USER")
        self.pricing.total_cents.assert_not_called()
        self.fraud.score.assert_not_called()
        self.payments.charge.assert_not_called()
        self.repo.save.assert_not_called()
        self.email.send_receipt.assert_not_called()

    def test_checkout_returns_invalid_cart_when_pricing_fails(self):
        self.pricing.total_cents.side_effect = PricingError("invalid coupon")

        result = self.service.checkout("user-1", [], "tok_test", "CL", coupon_code="BAD")

        self.assertEqual(result, "INVALID_CART:invalid coupon")
        self.fraud.score.assert_not_called()
        self.payments.charge.assert_not_called()
        self.repo.save.assert_not_called()
        self.email.send_receipt.assert_not_called()

    def test_checkout_rejects_orders_flagged_as_fraud(self):
        self.pricing.total_cents.return_value = 15000
        self.fraud.score.return_value = 80

        result = self.service.checkout("user-1", [], "tok_test", "CL")

        self.assertEqual(result, "REJECTED_FRAUD")
        self.fraud.score.assert_called_once_with("user-1", 15000)
        self.payments.charge.assert_not_called()
        self.repo.save.assert_not_called()
        self.email.send_receipt.assert_not_called()

    def test_checkout_returns_payment_failed_when_gateway_declines(self):
        self.pricing.total_cents.return_value = 12345
        self.fraud.score.return_value = 10
        self.payments.charge.return_value = ChargeResult(False, reason="DECLINED")

        result = self.service.checkout("user-1", [], "tok_test", "CL")

        self.assertEqual(result, "PAYMENT_FAILED:DECLINED")
        self.payments.charge.assert_called_once_with(
            user_id="user-1",
            amount_cents=12345,
            payment_token="tok_test",
        )
        self.repo.save.assert_not_called()
        self.email.send_receipt.assert_not_called()

    def test_checkout_saves_order_and_sends_receipt_on_success(self):
        self.pricing.total_cents.return_value = 9900
        self.fraud.score.return_value = 15
        self.payments.charge.return_value = ChargeResult(True, charge_id="ch_123")

        with patch("src.checkout.uuid.uuid4", return_value="order-123"):
            result = self.service.checkout("user-1", [], "tok_test", " cl ", coupon_code="SAVE10")

        self.assertEqual(result, "OK:order-123")
        saved_order = self.repo.save.call_args.args[0]
        self.assertIsInstance(saved_order, Order)
        self.assertEqual(saved_order.order_id, "order-123")
        self.assertEqual(saved_order.user_id, "user-1")
        self.assertEqual(saved_order.total_cents, 9900)
        self.assertEqual(saved_order.payment_charge_id, "ch_123")
        self.assertEqual(saved_order.coupon_code, "SAVE10")
        self.assertEqual(saved_order.country, "CL")
        self.email.send_receipt.assert_called_once_with("user-1", "order-123", 9900)

    def test_checkout_uses_default_pricing_service_and_unknown_charge_id_fallback(self):
        payments = Mock()
        email = Mock()
        fraud = Mock()
        repo = Mock()
        service = CheckoutService(payments=payments, email=email, fraud=fraud, repo=repo)

        self.assertIsInstance(service.pricing, PricingService)

        fraud.score.return_value = 5
        payments.charge.return_value = ChargeResult(True, charge_id=None)
        items = [CartItem("SKU-1", 1000, 2)]

        with patch("src.checkout.uuid.uuid4", return_value="order-456"):
            result = service.checkout("user-2", items, "tok_live", " us ")

        self.assertEqual(result, "OK:order-456")
        saved_order = repo.save.call_args.args[0]
        self.assertEqual(saved_order.total_cents, 7000)
        self.assertEqual(saved_order.payment_charge_id, "UNKNOWN")
        self.assertEqual(saved_order.country, "US")
        payments.charge.assert_called_once_with(
            user_id="user-2",
            amount_cents=7000,
            payment_token="tok_live",
        )
        email.send_receipt.assert_called_once_with("user-2", "order-456", 7000)
