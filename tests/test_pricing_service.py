import unittest

from src.models import CartItem
from src.pricing import PricingError, PricingService


class TestPricingService(unittest.TestCase):
    def setUp(self):
        self.service = PricingService()

    def test_subtotal_cents_sums_all_items(self):
        items = [
            CartItem("SKU-1", 1000, 2),
            CartItem("SKU-2", 250, 4),
        ]

        self.assertEqual(self.service.subtotal_cents(items), 3000)

    def test_subtotal_cents_rejects_non_positive_quantities(self):
        with self.assertRaisesRegex(PricingError, "qty must be > 0"):
            self.service.subtotal_cents([CartItem("SKU-1", 1000, 0)])

    def test_subtotal_cents_rejects_negative_unit_prices(self):
        with self.assertRaisesRegex(PricingError, "unit_price_cents must be >= 0"):
            self.service.subtotal_cents([CartItem("SKU-1", -1, 1)])

    def test_apply_coupon_returns_subtotal_when_coupon_is_missing_or_blank(self):
        self.assertEqual(self.service.apply_coupon(5000, None), 5000)
        self.assertEqual(self.service.apply_coupon(5000, "   "), 5000)

    def test_apply_coupon_save10_is_case_and_whitespace_insensitive(self):
        self.assertEqual(self.service.apply_coupon(10000, " save10 "), 9000)

    def test_apply_coupon_clp2000_reduces_total_but_never_below_zero(self):
        self.assertEqual(self.service.apply_coupon(5000, "CLP2000"), 3000)
        self.assertEqual(self.service.apply_coupon(1500, "CLP2000"), 0)

    def test_apply_coupon_rejects_unknown_codes(self):
        with self.assertRaisesRegex(PricingError, "invalid coupon"):
            self.service.apply_coupon(5000, "NOPE")

    def test_tax_cents_supports_configured_countries(self):
        self.assertEqual(self.service.tax_cents(10000, " cl "), 1900)
        self.assertEqual(self.service.tax_cents(10000, "EU"), 2100)
        self.assertEqual(self.service.tax_cents(10000, "US"), 0)

    def test_tax_cents_rejects_unsupported_countries(self):
        with self.assertRaisesRegex(PricingError, "unsupported country"):
            self.service.tax_cents(10000, "AR")

    def test_shipping_cents_handles_threshold_fixed_rates_and_invalid_country(self):
        self.assertEqual(self.service.shipping_cents(20000, "CL"), 0)
        self.assertEqual(self.service.shipping_cents(19999, "cl"), 2500)
        self.assertEqual(self.service.shipping_cents(5000, "US"), 5000)
        self.assertEqual(self.service.shipping_cents(5000, "EU"), 5000)

        with self.assertRaisesRegex(PricingError, "unsupported country"):
            self.service.shipping_cents(5000, "AR")

    def test_total_cents_combines_subtotal_coupon_tax_and_shipping(self):
        items = [CartItem("SKU-1", 12000, 2)]

        total = self.service.total_cents(items, "SAVE10", "CL")

        self.assertEqual(total, 25704)
