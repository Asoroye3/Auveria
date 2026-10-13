from django.core.management.base import BaseCommand, CommandError

from apps.ledger.reconciliation import run_reconciliation


class Command(BaseCommand):
    help = "Check that the ledger balances and cached account balances match it."

    def handle(self, *args, **options):
        report = run_reconciliation()

        for tx_id, d, c in report.unbalanced_transactions:
            self.stdout.write(self.style.ERROR(f"Transaction {tx_id}: debits {d} != credits {c} (kobo)"))
        for number, cached, expected in report.balance_mismatches:
            self.stdout.write(
                self.style.ERROR(f"Account {number}: cached {cached} != ledger {expected} (kobo)")
            )
        if report.total_balance_kobo != 0:
            self.stdout.write(
                self.style.ERROR(f"All balances sum to {report.total_balance_kobo} kobo, expected 0")
            )

        if not report.ok:
            raise CommandError("Reconciliation FAILED")
        self.stdout.write(self.style.SUCCESS("Reconciliation OK: ledger balanced, all balances match."))
