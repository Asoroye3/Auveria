from django.test import TestCase

from apps.kyc.models import Customer
from apps.kyc.services import OnboardingError, onboard_customer


class OnboardingTests(TestCase):
    def test_successful_onboarding_creates_tier2_customer(self):
        c = onboard_customer(bvn="22211111111", nin="22219999999", phone="08030000000")
        self.assertEqual(c.tier.code, 2)
        self.assertEqual(c.bvn_last4, "1111")
        self.assertEqual(c.nin_last4, "9999")
        self.assertIsNotNone(c.verified_at)

    def test_full_numbers_are_never_stored(self):
        c = onboard_customer(bvn="22211111111", nin="22219999999", phone="08030000000")
        stored = " ".join(str(v) for v in Customer.objects.filter(pk=c.pk).values().first().values())
        self.assertNotIn("22211111111", stored)
        self.assertNotIn("22219999999", stored)

    def test_rejects_malformed_numbers(self):
        with self.assertRaises(OnboardingError):
            onboard_customer(bvn="123", nin="22219999999", phone="0803")

    def test_rejects_unknown_bvn(self):
        with self.assertRaises(OnboardingError):
            onboard_customer(bvn="22210000000", nin="22219999999", phone="0803")

    def test_rejects_mismatched_identities(self):
        with self.assertRaises(OnboardingError):
            onboard_customer(bvn="22211111111", nin="22229999999", phone="0803")

    def test_rejects_duplicate_identity(self):
        onboard_customer(bvn="22211111111", nin="22219999999", phone="0803")
        with self.assertRaises(OnboardingError):
            onboard_customer(bvn="22211111111", nin="22219999999", phone="0804")
