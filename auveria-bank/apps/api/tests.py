import re

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.security.models import OneTimeCode
from apps.security.providers import LocMemSMSProvider

PASSWORD = "Str0ng-Passw0rd!"
# Mock provider: BVN and NIN sharing their first 4 digits are the same person.
PEOPLE = {
    "ada": ("22211111111", "22219999999", "08030000001"),
    "bola": ("33321111111", "33329999999", "08030000002"),
}
PIN = "2580"


@override_settings(SMS_PROVIDER="apps.security.providers.LocMemSMSProvider", OTP_RESEND_COOLDOWN_SECONDS=0)
class ApiBase(TestCase):
    def setUp(self):
        cache.clear()  # reset rate-limit counters between tests
        LocMemSMSProvider.outbox.clear()
        self.anon = APIClient()

    def register(self, who):
        bvn, nin, phone = PEOPLE[who]
        r = self.anon.post(
            "/api/v1/auth/register/",
            {"bvn": bvn, "nin": nin, "phone": phone, "password": PASSWORD}, format="json",
        )
        self.assertEqual(r.status_code, 201, r.data)
        return r.data

    def client_for(self, token):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        return c

    def staff(self):
        User = get_user_model()
        user, _ = User.objects.get_or_create(username="teller1", defaults={"is_staff": True})
        token, _ = Token.objects.get_or_create(user=user)
        return self.client_for(token.key)

    def fund(self, account_number, kobo, key):
        r = self.staff().post(
            "/api/v1/staff/deposits/", {"account_number": account_number, "amount_kobo": kobo},
            format="json", HTTP_IDEMPOTENCY_KEY=key,
        )
        self.assertEqual(r.status_code, 201, r.data)

    def customer_with_pin(self, who):
        data = self.register(who)
        client = self.client_for(data["token"])
        r = client.post("/api/v1/pin/", {"pin": PIN}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        return client, data["account_number"]

    def send(self, client, src, dst, kobo, pin=PIN, key="k1"):
        return client.post(
            "/api/v1/transfers/",
            {"from_account": src, "to_account": dst, "amount_kobo": kobo, "pin": pin},
            format="json", HTTP_IDEMPOTENCY_KEY=key,
        )


class AuthTests(ApiBase):
    def test_register_returns_token_and_nuban_account(self):
        data = self.register("ada")
        self.assertTrue(data["token"])
        self.assertEqual(len(data["account_number"]), 10)
        self.assertEqual(data["customer"]["tier"], 2)

    def test_register_rejects_unknown_bvn(self):
        r = self.anon.post(
            "/api/v1/auth/register/",
            {"bvn": "22210000000", "nin": "22219999999", "phone": "0803", "password": PASSWORD},
            format="json",
        )
        self.assertEqual(r.status_code, 400)

    def test_login_works_and_wrong_password_fails(self):
        self.register("ada")
        ok = self.anon.post("/api/v1/auth/login/", {"phone": PEOPLE["ada"][2], "password": PASSWORD}, format="json")
        self.assertEqual(ok.status_code, 200)
        self.assertIn("token", ok.data)
        bad = self.anon.post("/api/v1/auth/login/", {"phone": PEOPLE["ada"][2], "password": "nope-nope-1"}, format="json")
        self.assertEqual(bad.status_code, 400)

    def test_endpoints_require_authentication(self):
        self.assertEqual(self.anon.get("/api/v1/accounts/").status_code, 401)


class PinTests(ApiBase):
    def test_transfer_requires_a_pin_to_be_set(self):
        a = self.register("ada")
        b = self.register("bola")
        self.fund(a["account_number"], 100_000, "f1")
        r = self.send(self.client_for(a["token"]), a["account_number"], b["account_number"], 1_000)
        self.assertEqual(r.status_code, 400)

    def test_pin_locks_after_five_wrong_attempts(self):
        ada, ada_acct = self.customer_with_pin("ada")
        _, bola_acct = self.customer_with_pin("bola")
        self.fund(ada_acct, 100_000, "f1")
        for expected_left in (4, 3, 2, 1):
            r = self.send(ada, ada_acct, bola_acct, 1_000, pin="1111", key=f"w{expected_left}")
            self.assertEqual(r.status_code, 403)
            self.assertEqual(r.data["attempts_remaining"], expected_left)
        self.assertEqual(self.send(ada, ada_acct, bola_acct, 1_000, pin="1111", key="w0").status_code, 423)
        # Even the correct PIN is refused while locked.
        self.assertEqual(self.send(ada, ada_acct, bola_acct, 1_000, key="right").status_code, 423)

    def test_weak_pin_rejected(self):
        data = self.register("ada")
        r = self.client_for(data["token"]).post("/api/v1/pin/", {"pin": "1111"}, format="json")
        self.assertEqual(r.status_code, 400)


class TransferApiTests(ApiBase):
    def setUp(self):
        super().setUp()
        self.ada, self.ada_acct = self.customer_with_pin("ada")
        self.bola, self.bola_acct = self.customer_with_pin("bola")
        self.fund(self.ada_acct, 100_000, "seed")

    def test_transfer_moves_money(self):
        r = self.send(self.ada, self.ada_acct, self.bola_acct, 30_000)
        self.assertEqual(r.status_code, 201, r.data)
        balances = {a["account_number"]: a["balance_kobo"] for a in self.ada.get("/api/v1/accounts/").data}
        self.assertEqual(balances[self.ada_acct], 70_000)
        bola_balances = self.bola.get("/api/v1/accounts/").data
        self.assertEqual(bola_balances[0]["balance_kobo"], 30_000)
        self.assertEqual(bola_balances[0]["balance_display"], "₦300.00")

    def test_replayed_key_does_not_charge_twice(self):
        r1 = self.send(self.ada, self.ada_acct, self.bola_acct, 10_000, key="same")
        r2 = self.send(self.ada, self.ada_acct, self.bola_acct, 10_000, key="same")
        self.assertEqual(r1.data["reference"], r2.data["reference"])
        self.assertEqual(self.ada.get("/api/v1/accounts/").data[0]["balance_kobo"], 90_000)

    def test_missing_idempotency_key_rejected(self):
        r = self.ada.post(
            "/api/v1/transfers/",
            {"from_account": self.ada_acct, "to_account": self.bola_acct, "amount_kobo": 100, "pin": PIN},
            format="json",
        )
        self.assertEqual(r.status_code, 400)

    def test_cannot_send_from_someone_elses_account(self):
        r = self.send(self.bola, self.ada_acct, self.bola_acct, 1_000)
        self.assertEqual(r.status_code, 404)

    def test_insufficient_funds_returns_422(self):
        r = self.send(self.ada, self.ada_acct, self.bola_acct, 999_999_999)
        self.assertEqual(r.status_code, 422)

    def test_name_enquiry(self):
        r = self.ada.get(f"/api/v1/accounts/lookup/{self.bola_acct}/")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["account_name"])
        self.assertEqual(self.ada.get("/api/v1/accounts/lookup/0000000000/").status_code, 404)

    def test_statement_lists_entries_and_is_private(self):
        self.send(self.ada, self.ada_acct, self.bola_acct, 5_000)
        r = self.ada.get(f"/api/v1/accounts/{self.ada_acct}/transactions/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["count"], 2)  # the deposit and the transfer
        self.assertEqual(r.data["results"][0]["direction"], "DEBIT")
        self.assertEqual(self.bola.get(f"/api/v1/accounts/{self.ada_acct}/transactions/").status_code, 404)


class StaffTests(ApiBase):
    def test_customers_cannot_use_staff_endpoints(self):
        data = self.register("ada")
        r = self.client_for(data["token"]).post(
            "/api/v1/staff/deposits/", {"account_number": data["account_number"], "amount_kobo": 1_000},
            format="json", HTTP_IDEMPOTENCY_KEY="x",
        )
        self.assertEqual(r.status_code, 403)

    def test_staff_withdrawal_reduces_balance(self):
        data = self.register("ada")
        self.fund(data["account_number"], 50_000, "d1")
        r = self.staff().post(
            "/api/v1/staff/withdrawals/", {"account_number": data["account_number"], "amount_kobo": 20_000},
            format="json", HTTP_IDEMPOTENCY_KEY="w1",
        )
        self.assertEqual(r.status_code, 201, r.data)
        accounts = self.client_for(data["token"]).get("/api/v1/accounts/").data
        self.assertEqual(accounts[0]["balance_kobo"], 30_000)


def latest_code():
    return re.search(r"Code: (\d{6})", LocMemSMSProvider.outbox[-1][1]).group(1)


class OtpApiTests(ApiBase):
    def setUp(self):
        super().setUp()
        self.ada, self.ada_acct = self.customer_with_pin("ada")
        self.bola, self.bola_acct = self.customer_with_pin("bola")
        self.fund(self.ada_acct, 10_000_000, "seed")  # NGN 100,000

    def request_transfer_code(self, amount):
        return self.ada.post(
            "/api/v1/otp/request/",
            {"purpose": "TRANSFER", "from_account": self.ada_acct, "to_account": self.bola_acct,
             "amount_kobo": amount},
            format="json",
        )

    def send_with_otp(self, amount, otp, key):
        return self.ada.post(
            "/api/v1/transfers/",
            {"from_account": self.ada_acct, "to_account": self.bola_acct, "amount_kobo": amount,
             "pin": PIN, "otp": otp},
            format="json", HTTP_IDEMPOTENCY_KEY=key,
        )

    def ada_balance(self):
        return self.ada.get("/api/v1/accounts/").data[0]["balance_kobo"]

    def test_small_transfers_do_not_need_an_otp(self):
        self.assertEqual(self.send(self.ada, self.ada_acct, self.bola_acct, 1_000).status_code, 201)

    def test_large_transfer_requires_an_otp(self):
        r = self.send(self.ada, self.ada_acct, self.bola_acct, 3_000_000)
        self.assertEqual(r.status_code, 400)
        self.assertTrue(r.data["otp_required"])
        self.assertEqual(self.ada_balance(), 10_000_000)

    def test_large_transfer_succeeds_with_the_texted_code(self):
        r = self.request_transfer_code(3_000_000)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertNotIn(latest_code(), str(r.data))  # the code only goes by SMS
        phone, message = LocMemSMSProvider.outbox[-1]
        self.assertEqual(phone, PEOPLE["ada"][2])
        self.assertIn("NGN 30,000.00", message)
        self.assertIn(self.bola_acct, message)
        ok = self.send_with_otp(3_000_000, latest_code(), "big1")
        self.assertEqual(ok.status_code, 201, ok.data)
        self.assertEqual(self.ada_balance(), 7_000_000)

    def test_code_only_works_for_the_exact_transfer_it_was_sent_for(self):
        self.request_transfer_code(3_000_000)
        code = latest_code()
        self.assertEqual(self.send_with_otp(3_500_000, code, "x1").status_code, 403)
        self.assertEqual(self.send_with_otp(3_000_000, code, "x2").status_code, 201)

    def test_wrong_code_is_rejected_with_attempts_remaining(self):
        self.request_transfer_code(3_000_000)
        real = latest_code()
        wrong = "000000" if real != "000000" else "111111"
        r = self.send_with_otp(3_000_000, wrong, "w1")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data["attempts_remaining"], 4)

    def test_retrying_a_completed_transfer_returns_the_same_result(self):
        self.request_transfer_code(3_000_000)
        first = self.send_with_otp(3_000_000, latest_code(), "retry-me")
        again = self.ada.post(  # network hiccup: same key, no fresh code
            "/api/v1/transfers/",
            {"from_account": self.ada_acct, "to_account": self.bola_acct, "amount_kobo": 3_000_000, "pin": PIN},
            format="json", HTTP_IDEMPOTENCY_KEY="retry-me",
        )
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.data["reference"], first.data["reference"])
        self.assertEqual(self.ada_balance(), 7_000_000)  # charged once

    def test_cannot_request_a_code_for_someone_elses_account(self):
        r = self.bola.post(
            "/api/v1/otp/request/",
            {"purpose": "TRANSFER", "from_account": self.ada_acct, "to_account": self.bola_acct,
             "amount_kobo": 3_000_000},
            format="json",
        )
        self.assertEqual(r.status_code, 404)

    def test_changing_the_pin_needs_an_otp_and_the_current_pin(self):
        no_otp = self.ada.post("/api/v1/pin/", {"pin": "1357", "current_pin": PIN}, format="json")
        self.assertEqual(no_otp.status_code, 400)
        self.ada.post("/api/v1/otp/request/", {"purpose": "PIN_CHANGE"}, format="json")
        code = latest_code()
        no_current = self.ada.post("/api/v1/pin/", {"pin": "1357", "otp": code}, format="json")
        self.assertEqual(no_current.status_code, 400)
        self.ada.post("/api/v1/otp/request/", {"purpose": "PIN_CHANGE"}, format="json")
        ok = self.ada.post(
            "/api/v1/pin/", {"pin": "1357", "current_pin": PIN, "otp": latest_code()}, format="json"
        )
        self.assertEqual(ok.status_code, 200, ok.data)
        self.assertEqual(self.send(self.ada, self.ada_acct, self.bola_acct, 1_000, pin="1357", key="np").status_code, 201)

    def test_large_overdraft_is_refused_without_using_up_the_code(self):
        self.request_transfer_code(20_000_000)  # more than Ada's N100,000
        r = self.send_with_otp(20_000_000, latest_code(), "too-much")
        self.assertEqual(r.status_code, 422)
        self.assertEqual(OneTimeCode.objects.filter(consumed_at__isnull=True).count(), 1)


class MeTests(ApiBase):
    def test_me_reports_tier_limits_and_pin_status(self):
        data = self.register("ada")
        client = self.client_for(data["token"])
        r = client.get("/api/v1/me/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["tier"], 2)
        self.assertFalse(r.data["pin_set"])
        self.assertEqual(r.data["otp_threshold_kobo"], 2_000_000)
        self.assertNotIn(PEOPLE["ada"][2], str(r.data))  # the phone number comes back masked
        client.post("/api/v1/pin/", {"pin": PIN}, format="json")
        self.assertTrue(client.get("/api/v1/me/").data["pin_set"])

    def test_me_requires_authentication(self):
        self.assertEqual(self.anon.get("/api/v1/me/").status_code, 401)


class StaffViewTests(ApiBase):
    def test_whoami_tells_staff_from_customers(self):
        data = self.register("ada")
        self.assertEqual(self.client_for(data["token"]).get("/api/v1/whoami/").data["role"], "customer")
        self.assertEqual(self.staff().get("/api/v1/whoami/").data["role"], "staff")
        self.assertEqual(self.anon.get("/api/v1/whoami/").status_code, 401)

    def test_staff_can_look_up_an_account_and_see_its_balance(self):
        data = self.register("ada")
        self.fund(data["account_number"], 50_000, "f1")
        r = self.staff().get(f"/api/v1/staff/accounts/{data['account_number']}/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["balance_kobo"], 50_000)
        self.assertEqual(r.data["tier"], 2)
        self.assertEqual(len(r.data["recent"]), 1)
        self.assertEqual(self.staff().get("/api/v1/staff/accounts/0000000000/").status_code, 404)

    def test_customers_cannot_use_the_staff_lookup_or_journal(self):
        data = self.register("ada")
        customer = self.client_for(data["token"])
        self.assertEqual(customer.get(f"/api/v1/staff/accounts/{data['account_number']}/").status_code, 403)
        self.assertEqual(customer.get("/api/v1/staff/cash-journal/").status_code, 403)

    def test_cash_journal_tracks_net_cash_and_lists_movements(self):
        data = self.register("ada")
        self.fund(data["account_number"], 50_000, "j1")
        self.staff().post(
            "/api/v1/staff/withdrawals/", {"account_number": data["account_number"], "amount_kobo": 20_000},
            format="json", HTTP_IDEMPOTENCY_KEY="j2",
        )
        r = self.staff().get("/api/v1/staff/cash-journal/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["net_cash_kobo"], 30_000)
        self.assertEqual(len(r.data["entries"]), 2)
        self.assertEqual({e["type"] for e in r.data["entries"]}, {"DEPOSIT", "WITHDRAWAL"})
        self.assertEqual(r.data["entries"][0]["account_number"], data["account_number"])
