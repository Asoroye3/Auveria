"""Concurrency tests. They need PostgreSQL: SQLite ignores row locks.

Run with the DB_* environment variables set (see README).
"""
import threading
import unittest
from datetime import date

from django.db import connection, connections
from django.test import TransactionTestCase

from apps.accounts.models import Account
from apps.kyc.models import Customer
from apps.kyc.services import get_tier

from .reconciliation import run_reconciliation
from .services import InsufficientFunds, LimitExceeded, deposit, transfer


def run_parallel(n, fn):
    """Run fn(i) in n threads released at the same instant: [(status, value), ...]."""
    results = []
    barrier = threading.Barrier(n)

    def worker(i):
        try:
            barrier.wait()
            results.append(("ok", fn(i)))
        except Exception as exc:  # collected and asserted on by the tests
            results.append(("error", exc))
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


@unittest.skipUnless(connection.vendor == "postgresql", "needs PostgreSQL row locks")
class ConcurrencyTests(TransactionTestCase):
    def test_parallel_spends_never_overdraw(self):
        src = Account.objects.create(owner_name="Src")
        dst = Account.objects.create(owner_name="Dst")
        deposit(account_id=src.id, amount_kobo=100_000, idempotency_key="seed")

        results = run_parallel(20, lambda i: transfer(
            from_account_id=src.id, to_account_id=dst.id,
            amount_kobo=10_000, idempotency_key=f"spend-{i}"))

        errors = [r[1] for r in results if r[0] == "error"]
        self.assertEqual(len([r for r in results if r[0] == "ok"]), 10)
        self.assertTrue(all(isinstance(e, InsufficientFunds) for e in errors), errors)
        src.refresh_from_db()
        dst.refresh_from_db()
        self.assertEqual((src.balance_kobo, dst.balance_kobo), (0, 100_000))
        self.assertTrue(run_reconciliation().ok)

    def test_same_idempotency_key_in_parallel_charges_once(self):
        src = Account.objects.create(owner_name="Src")
        dst = Account.objects.create(owner_name="Dst")
        deposit(account_id=src.id, amount_kobo=100_000, idempotency_key="seed")

        results = run_parallel(10, lambda i: transfer(
            from_account_id=src.id, to_account_id=dst.id,
            amount_kobo=10_000, idempotency_key="one-and-only"))

        self.assertEqual([r for r in results if r[0] == "error"], [])
        self.assertEqual(len({r[1].id for r in results}), 1)
        src.refresh_from_db()
        self.assertEqual(src.balance_kobo, 90_000)
        self.assertTrue(run_reconciliation().ok)

    def test_opposite_direction_transfers_do_not_deadlock(self):
        a = Account.objects.create(owner_name="A")
        b = Account.objects.create(owner_name="B")
        deposit(account_id=a.id, amount_kobo=1_000_000, idempotency_key="seed-a")
        deposit(account_id=b.id, amount_kobo=1_000_000, idempotency_key="seed-b")

        def move(i):
            src, dst = (a, b) if i % 2 == 0 else (b, a)
            return transfer(from_account_id=src.id, to_account_id=dst.id,
                            amount_kobo=1_000, idempotency_key=f"cross-{i}")

        results = run_parallel(40, move)
        self.assertEqual([r for r in results if r[0] == "error"], [])
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(a.balance_kobo + b.balance_kobo, 2_000_000)
        self.assertTrue(run_reconciliation().ok)

    def test_parallel_deposits_keep_the_vault_consistent(self):
        accounts = [Account.objects.create(owner_name=f"C{i}") for i in range(20)]
        results = run_parallel(20, lambda i: deposit(
            account_id=accounts[i].id, amount_kobo=1_000, idempotency_key=f"dep-{i}"))
        self.assertEqual([r for r in results if r[0] == "error"], [])
        self.assertTrue(run_reconciliation().ok)

    def test_daily_limit_holds_under_parallel_requests(self):
        cust = Customer.objects.create(
            full_name="T1", date_of_birth=date(1990, 1, 1), phone="0803",
            identity_hash="conc-t1", tier=get_tier(1))
        src = Account.objects.create(owner_name="T1", customer=cust)
        dst = Account.objects.create(owner_name="Dst")
        deposit(account_id=src.id, amount_kobo=10_000_000, idempotency_key="seed-t1")

        results = run_parallel(10, lambda i: transfer(
            from_account_id=src.id, to_account_id=dst.id,
            amount_kobo=1_000_000, idempotency_key=f"lim-{i}"))

        errors = [r[1] for r in results if r[0] == "error"]
        # Tier 1 daily cap is 5,000,000 kobo, so exactly 5 transfers fit.
        self.assertEqual(len([r for r in results if r[0] == "ok"]), 5)
        self.assertTrue(all(isinstance(e, LimitExceeded) for e in errors), errors)
        self.assertTrue(run_reconciliation().ok)
