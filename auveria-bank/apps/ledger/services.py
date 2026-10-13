import uuid
from datetime import datetime, time

from django.db import transaction as db_tx
from django.db.models import Sum
from django.utils import timezone

from apps.accounts.models import Account
from apps.accounts.services import get_cash_account
from .models import LedgerEntry, Transaction


class InsufficientFunds(Exception):
    pass


class AccountNotActive(Exception):
    pass


class LimitExceeded(Exception):
    pass


def _spent_today(account) -> int:
    start = timezone.make_aware(datetime.combine(timezone.localdate(), time.min))
    total = LedgerEntry.objects.filter(
        account=account,
        direction=LedgerEntry.Direction.DEBIT,
        created_at__gte=start,
        transaction__status=Transaction.Status.POSTED,
    ).aggregate(total=Sum("amount_kobo"))["total"]
    return total or 0


def _enforce_rules(src, dst, amount_kobo):
    for acct in (src, dst):
        if acct.status != Account.Status.ACTIVE:
            raise AccountNotActive(f"Account {acct.account_number} is {acct.status}")

    if src.customer_id:
        cap = src.customer.tier.daily_limit_kobo
        if cap is not None and _spent_today(src) + amount_kobo > cap:
            raise LimitExceeded("daily transfer limit exceeded")

    if dst.customer_id:
        cap = dst.customer.tier.max_balance_kobo
        if cap is not None and dst.balance_kobo + amount_kobo > cap:
            raise LimitExceeded("recipient's maximum balance would be exceeded")


@db_tx.atomic
def transfer(*, from_account_id, to_account_id, amount_kobo, idempotency_key, type="TRANSFER"):
    """Move money between two accounts atomically and idempotently."""
    if amount_kobo <= 0:
        raise ValueError("amount must be positive")
    if from_account_id == to_account_id:
        raise ValueError("cannot transfer to the same account")

    # Lock both rows in a stable order to avoid deadlocks. `of=("self",)` locks
    # only the account rows: PostgreSQL refuses FOR UPDATE on the nullable side
    # of the customer join (SQLite ignores select_for_update entirely).
    accounts = {
        a.id: a
        for a in Account.objects.select_for_update(of=("self",))
        .select_related("customer__tier")
        .filter(id__in=[from_account_id, to_account_id])
        .order_by("id")
    }
    src, dst = accounts[from_account_id], accounts[to_account_id]

    # Idempotency check AFTER locking: two simultaneous requests with the same
    # key queue up on the account lock, and the second one then sees the first
    # one's committed transaction instead of crashing on the unique key.
    existing = Transaction.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        return existing  # retry of a request we already processed

    if type == "TRANSFER" and (src.is_system or dst.is_system):
        raise ValueError("system accounts can only be used by deposits and withdrawals")

    _enforce_rules(src, dst, amount_kobo)
    # System accounts (the cash vault) are allowed to run negative.
    if not src.is_system and src.balance_kobo < amount_kobo:
        raise InsufficientFunds()

    tx = Transaction.objects.create(
        reference=uuid.uuid4().hex, idempotency_key=idempotency_key, type=type
    )
    LedgerEntry.objects.create(transaction=tx, account=src, direction="DEBIT", amount_kobo=amount_kobo)
    LedgerEntry.objects.create(transaction=tx, account=dst, direction="CREDIT", amount_kobo=amount_kobo)

    src.balance_kobo -= amount_kobo
    dst.balance_kobo += amount_kobo
    src.save(update_fields=["balance_kobo"])
    dst.save(update_fields=["balance_kobo"])
    return tx


def deposit(*, account_id, amount_kobo, idempotency_key):
    """Cash in: the vault is debited and the customer's account credited."""
    vault = get_cash_account()
    return transfer(
        from_account_id=vault.id, to_account_id=account_id, amount_kobo=amount_kobo,
        idempotency_key=idempotency_key, type="DEPOSIT",
    )


def withdraw(*, account_id, amount_kobo, idempotency_key):
    """Cash out: the customer's account is debited and the vault credited."""
    vault = get_cash_account()
    return transfer(
        from_account_id=account_id, to_account_id=vault.id, amount_kobo=amount_kobo,
        idempotency_key=idempotency_key, type="WITHDRAWAL",
    )
