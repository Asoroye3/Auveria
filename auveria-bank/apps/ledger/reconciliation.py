from dataclasses import dataclass, field

from django.db.models import Q, Sum

from apps.accounts.models import Account
from .models import LedgerEntry


@dataclass
class Report:
    unbalanced_transactions: list = field(default_factory=list)  # (transaction_id, debits, credits)
    balance_mismatches: list = field(default_factory=list)  # (account_number, cached, derived)
    total_balance_kobo: int = 0

    @property
    def ok(self) -> bool:
        return (
            not self.unbalanced_transactions
            and not self.balance_mismatches
            and self.total_balance_kobo == 0
        )


def run_reconciliation() -> Report:
    credits = Sum("amount_kobo", filter=Q(direction=LedgerEntry.Direction.CREDIT))
    debits = Sum("amount_kobo", filter=Q(direction=LedgerEntry.Direction.DEBIT))
    report = Report()

    # 1. Every transaction must balance: debits == credits.
    for row in LedgerEntry.objects.values("transaction_id").annotate(c=credits, d=debits):
        c, d = row["c"] or 0, row["d"] or 0
        if c != d:
            report.unbalanced_transactions.append((row["transaction_id"], d, c))

    # 2. Every cached balance must equal credits - debits from the ledger.
    derived = {
        row["account_id"]: (row["c"] or 0) - (row["d"] or 0)
        for row in LedgerEntry.objects.values("account_id").annotate(c=credits, d=debits)
    }
    for acct in Account.objects.all():
        expected = derived.get(acct.id, 0)
        if acct.balance_kobo != expected:
            report.balance_mismatches.append((acct.account_number, acct.balance_kobo, expected))

    # 3. Money is only moved, never created: all balances must sum to zero.
    report.total_balance_kobo = Account.objects.aggregate(t=Sum("balance_kobo"))["t"] or 0
    return report
