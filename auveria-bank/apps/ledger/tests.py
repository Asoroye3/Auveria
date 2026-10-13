from django.test import TestCase

from apps.accounts import nuban
from apps.accounts.models import Account
from apps.ledger.models import LedgerEntry
from apps.ledger.services import InsufficientFunds, transfer


class AccountTests(TestCase):
    def test_new_account_gets_valid_nuban(self):
        acct = Account.objects.create(owner_name="Ada")
        self.assertEqual(len(acct.account_number), 10)
        self.assertTrue(nuban.is_valid("777", acct.account_number))


class TransferTests(TestCase):
    def setUp(self):
        self.a = Account.objects.create(owner_name="Ada", balance_kobo=100_000)
        self.b = Account.objects.create(owner_name="Bola")

    def test_transfer_moves_money_and_balances_entries(self):
        tx = transfer(from_account_id=self.a.id, to_account_id=self.b.id,
                      amount_kobo=40_000, idempotency_key="k1")
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.assertEqual(self.a.balance_kobo, 60_000)
        self.assertEqual(self.b.balance_kobo, 40_000)
        entries = LedgerEntry.objects.filter(transaction=tx)
        debits = sum(e.amount_kobo for e in entries if e.direction == "DEBIT")
        credits = sum(e.amount_kobo for e in entries if e.direction == "CREDIT")
        self.assertEqual(debits, credits)

    def test_same_idempotency_key_does_not_double_spend(self):
        t1 = transfer(from_account_id=self.a.id, to_account_id=self.b.id,
                      amount_kobo=10_000, idempotency_key="dup")
        t2 = transfer(from_account_id=self.a.id, to_account_id=self.b.id,
                      amount_kobo=10_000, idempotency_key="dup")
        self.assertEqual(t1.id, t2.id)
        self.a.refresh_from_db()
        self.assertEqual(self.a.balance_kobo, 90_000)

    def test_insufficient_funds(self):
        with self.assertRaises(InsufficientFunds):
            transfer(from_account_id=self.a.id, to_account_id=self.b.id,
                     amount_kobo=999_999, idempotency_key="big")

    def test_cannot_transfer_to_self(self):
        with self.assertRaises(ValueError):
            transfer(from_account_id=self.a.id, to_account_id=self.a.id,
                     amount_kobo=1, idempotency_key="self")

    def test_ledger_entries_are_immutable(self):
        tx = transfer(from_account_id=self.a.id, to_account_id=self.b.id,
                      amount_kobo=5_000, idempotency_key="imm")
        entry = tx.entries.first()
        with self.assertRaises(RuntimeError):
            entry.save()
        with self.assertRaises(RuntimeError):
            entry.delete()


class RulesTests(TestCase):
    """Tier limits and account status checks."""

    def _customer(self, tier_code, suffix):
        from datetime import date

        from apps.kyc.models import Customer
        from apps.kyc.services import get_tier

        return Customer.objects.create(
            full_name=f"Customer {suffix}", date_of_birth=date(1990, 1, 1), phone="0803",
            identity_hash=f"hash-{suffix}", tier=get_tier(tier_code),
        )

    def test_tier1_daily_limit_blocks_second_transfer(self):
        from apps.ledger.services import LimitExceeded

        src = Account.objects.create(owner_name="S", customer=self._customer(1, "s"), balance_kobo=10_000_000)
        dst = Account.objects.create(owner_name="D")
        transfer(from_account_id=src.id, to_account_id=dst.id, amount_kobo=4_000_000, idempotency_key="d1")
        with self.assertRaises(LimitExceeded):
            transfer(from_account_id=src.id, to_account_id=dst.id, amount_kobo=2_000_000, idempotency_key="d2")

    def test_tier1_max_balance_blocks_deposit_into_account(self):
        from apps.ledger.services import LimitExceeded

        src = Account.objects.create(owner_name="S", balance_kobo=5_000_000)
        dst = Account.objects.create(owner_name="D", customer=self._customer(1, "d"), balance_kobo=29_000_000)
        with self.assertRaises(LimitExceeded):
            transfer(from_account_id=src.id, to_account_id=dst.id, amount_kobo=2_000_000, idempotency_key="m1")

    def test_frozen_account_cannot_send(self):
        from apps.ledger.services import AccountNotActive

        src = Account.objects.create(owner_name="S", balance_kobo=1_000, status=Account.Status.FROZEN)
        dst = Account.objects.create(owner_name="D")
        with self.assertRaises(AccountNotActive):
            transfer(from_account_id=src.id, to_account_id=dst.id, amount_kobo=100, idempotency_key="f1")


class CashTests(TestCase):
    """Deposits, withdrawals and reconciliation."""

    def setUp(self):
        self.acct = Account.objects.create(owner_name="Ada")

    def test_deposit_credits_customer_and_debits_vault(self):
        from apps.accounts.services import get_cash_account
        from apps.ledger.services import deposit

        deposit(account_id=self.acct.id, amount_kobo=50_000, idempotency_key="dep1")
        self.acct.refresh_from_db()
        vault = get_cash_account()
        vault.refresh_from_db()
        self.assertEqual(self.acct.balance_kobo, 50_000)
        self.assertEqual(vault.balance_kobo, -50_000)

    def test_withdraw_reduces_balance_and_blocks_overdraft(self):
        from apps.ledger.services import deposit, withdraw

        deposit(account_id=self.acct.id, amount_kobo=50_000, idempotency_key="dep2")
        withdraw(account_id=self.acct.id, amount_kobo=20_000, idempotency_key="wd1")
        self.acct.refresh_from_db()
        self.assertEqual(self.acct.balance_kobo, 30_000)
        with self.assertRaises(InsufficientFunds):
            withdraw(account_id=self.acct.id, amount_kobo=999_999, idempotency_key="wd2")

    def test_deposit_is_idempotent(self):
        from apps.ledger.services import deposit

        t1 = deposit(account_id=self.acct.id, amount_kobo=10_000, idempotency_key="same")
        t2 = deposit(account_id=self.acct.id, amount_kobo=10_000, idempotency_key="same")
        self.assertEqual(t1.id, t2.id)
        self.acct.refresh_from_db()
        self.assertEqual(self.acct.balance_kobo, 10_000)

    def test_normal_transfer_cannot_touch_vault(self):
        from apps.accounts.services import get_cash_account

        vault = get_cash_account()
        with self.assertRaises(ValueError):
            transfer(from_account_id=vault.id, to_account_id=self.acct.id,
                     amount_kobo=100, idempotency_key="sneaky")

    def test_deposit_respects_tier1_max_balance(self):
        from datetime import date

        from apps.kyc.models import Customer
        from apps.kyc.services import get_tier
        from apps.ledger.services import LimitExceeded, deposit

        cust = Customer.objects.create(
            full_name="T1", date_of_birth=date(1990, 1, 1), phone="0803",
            identity_hash="hash-t1", tier=get_tier(1),
        )
        acct = Account.objects.create(owner_name="T1", customer=cust)
        with self.assertRaises(LimitExceeded):
            deposit(account_id=acct.id, amount_kobo=31_000_000, idempotency_key="big-dep")

    def test_reconciliation_clean_after_normal_activity(self):
        from apps.ledger.reconciliation import run_reconciliation
        from apps.ledger.services import deposit, withdraw

        other = Account.objects.create(owner_name="Bola")
        deposit(account_id=self.acct.id, amount_kobo=80_000, idempotency_key="r1")
        transfer(from_account_id=self.acct.id, to_account_id=other.id,
                 amount_kobo=30_000, idempotency_key="r2")
        withdraw(account_id=other.id, amount_kobo=10_000, idempotency_key="r3")
        report = run_reconciliation()
        self.assertTrue(report.ok, report)

    def test_reconciliation_detects_tampered_balance(self):
        from io import StringIO

        from django.core.management import call_command
        from django.core.management.base import CommandError

        from apps.ledger.reconciliation import run_reconciliation
        from apps.ledger.services import deposit

        deposit(account_id=self.acct.id, amount_kobo=10_000, idempotency_key="t1")
        Account.objects.filter(pk=self.acct.pk).update(balance_kobo=999_999)  # sneaky edit
        report = run_reconciliation()
        self.assertFalse(report.ok)
        self.assertEqual(len(report.balance_mismatches), 1)
        with self.assertRaises(CommandError):
            call_command("reconcile", stdout=StringIO())


class SeedDemoTests(TestCase):
    def test_seed_demo_is_repeatable_and_keeps_the_books_balanced(self):
        from io import StringIO

        from django.core.management import call_command
        from django.test import override_settings

        from apps.ledger.reconciliation import run_reconciliation

        with override_settings(DEBUG=True):
            call_command("seed_demo", stdout=StringIO())
            call_command("seed_demo", stdout=StringIO())  # second run must change nothing
        self.assertEqual(Account.objects.filter(is_system=False).count(), 2)
        self.assertTrue(run_reconciliation().ok)
        first = Account.objects.filter(is_system=False).order_by("id").first()
        self.assertEqual(first.balance_kobo, 15_000_000 - 2_500_000 - 750_000 - 120_000)
