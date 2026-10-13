import re
from datetime import date, timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.kyc.models import Customer
from apps.kyc.services import get_tier

from .models import OneTimeCode
from .providers import LocMemSMSProvider
from .services import OtpInvalid, OtpRateLimited, issue_otp, transfer_context, verify_otp

TRANSFER = OneTimeCode.Purpose.TRANSFER
PIN_CHANGE = OneTimeCode.Purpose.PIN_CHANGE


def sms_code():
    return re.search(r"Code: (\d{6})", LocMemSMSProvider.outbox[-1][1]).group(1)


def a_wrong_code(real):
    return "000000" if real != "000000" else "111111"


@override_settings(SMS_PROVIDER="apps.security.providers.LocMemSMSProvider", OTP_RESEND_COOLDOWN_SECONDS=0)
class OtpServiceTests(TestCase):
    def setUp(self):
        LocMemSMSProvider.outbox.clear()
        self.customer = Customer.objects.create(
            full_name="Ada", date_of_birth=date(1990, 1, 1), phone="08030000001",
            identity_hash="otp-test", tier=get_tier(2),
        )

    def test_code_works_once(self):
        issue_otp(self.customer, TRANSFER, description="confirm test")
        code = sms_code()
        verify_otp(self.customer, TRANSFER, code)
        with self.assertRaises(OtpInvalid):
            verify_otp(self.customer, TRANSFER, code)

    def test_code_is_stored_hashed_and_texted_to_the_customer(self):
        issue_otp(self.customer, TRANSFER, description="confirm test")
        code = sms_code()
        otp = OneTimeCode.objects.get()
        self.assertEqual(len(otp.code_hash), 64)
        self.assertNotIn(code, otp.code_hash)
        self.assertEqual(LocMemSMSProvider.outbox[-1][0], "08030000001")

    def test_wrong_guesses_are_counted_and_five_burn_the_code(self):
        issue_otp(self.customer, TRANSFER, description="confirm test")
        code = sms_code()
        bad = a_wrong_code(code)
        for expected_left in (4, 3, 2, 1, 0):
            with self.assertRaises(OtpInvalid) as ctx:
                verify_otp(self.customer, TRANSFER, bad)
            self.assertEqual(ctx.exception.attempts_remaining, expected_left)
        with self.assertRaises(OtpInvalid):  # burned: even the right code fails now
            verify_otp(self.customer, TRANSFER, code)

    def test_expired_code_rejected(self):
        issue_otp(self.customer, TRANSFER, description="confirm test")
        code = sms_code()
        OneTimeCode.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        with self.assertRaises(OtpInvalid):
            verify_otp(self.customer, TRANSFER, code)

    def test_code_is_tied_to_its_purpose(self):
        issue_otp(self.customer, TRANSFER, description="confirm test")
        with self.assertRaises(OtpInvalid):
            verify_otp(self.customer, PIN_CHANGE, sms_code())

    def test_code_is_tied_to_the_exact_transfer(self):
        ctx = transfer_context("0000000001", "0000000002", 3_000_000)
        other = transfer_context("0000000001", "0000000002", 3_500_000)
        issue_otp(self.customer, TRANSFER, context=ctx, description="confirm test")
        code = sms_code()
        with self.assertRaises(OtpInvalid):
            verify_otp(self.customer, TRANSFER, code, context=other)
        verify_otp(self.customer, TRANSFER, code, context=ctx)  # still usable for the right transfer

    def test_new_code_invalidates_the_old_one(self):
        issue_otp(self.customer, TRANSFER, description="confirm test")
        first = sms_code()
        issue_otp(self.customer, TRANSFER, description="confirm test")
        second = sms_code()
        if first != second:  # (a 1-in-a-million collision would make this meaningless)
            with self.assertRaises(OtpInvalid):
                verify_otp(self.customer, TRANSFER, first)
        verify_otp(self.customer, TRANSFER, second)

    @override_settings(OTP_RESEND_COOLDOWN_SECONDS=30)
    def test_resend_cooldown(self):
        issue_otp(self.customer, TRANSFER, description="confirm test")
        with self.assertRaises(OtpRateLimited):
            issue_otp(self.customer, TRANSFER, description="confirm test")
