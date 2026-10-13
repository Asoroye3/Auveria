from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Account
from apps.accounts.services import open_account
from apps.kyc.services import OnboardingError, register_customer, set_pin
from apps.ledger.services import AccountNotActive, InsufficientFunds, LimitExceeded, deposit, transfer

PASSWORD = "Demo-Passw0rd!"
PIN = "2580"
# (BVN, NIN, phone). The mock identity provider treats a BVN and NIN that share
# their first four digits as the same person.
PEOPLE = [
    ("22211111111", "22219999999", "08030000001"),
    ("33321111111", "33329999999", "08030000002"),
]


class Command(BaseCommand):
    help = "Create two demo customers with some money and history (development only)."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo is for development only (DEBUG is off).")

        User = get_user_model()
        accounts = []
        for bvn, nin, phone in PEOPLE:
            if not User.objects.filter(username=phone).exists():
                try:
                    customer = register_customer(bvn=bvn, nin=nin, phone=phone, password=PASSWORD)
                except OnboardingError as exc:
                    raise CommandError(f"Could not create {phone}: {exc}")
                open_account(customer)
                set_pin(customer, PIN)
                self.stdout.write(f"Created customer {customer.full_name} ({phone})")
            account = Account.objects.filter(customer__user__username=phone).first()
            if account is None:
                raise CommandError(f"{phone} exists but has no account")
            accounts.append(account)

        first, second = accounts
        # Fixed idempotency keys make this safe to run again: nothing is duplicated.
        deposit(account_id=first.id, amount_kobo=15_000_000, idempotency_key="seed-deposit-1")
        for i, kobo in enumerate((2_500_000, 750_000, 120_000), start=1):
            try:
                transfer(
                    from_account_id=first.id, to_account_id=second.id, amount_kobo=kobo,
                    idempotency_key=f"seed-transfer-{i}",
                )
            except (InsufficientFunds, LimitExceeded, AccountNotActive) as exc:
                self.stdout.write(f"Skipped demo transfer {i}: {exc}")

        self.stdout.write(self.style.SUCCESS("Demo data ready."))
        self.stdout.write(f"Demo logins (phone / password / PIN): {PEOPLE[0][2]} and {PEOPLE[1][2]} / {PASSWORD} / {PIN}")
        self.stdout.write("Customers that already existed keep their own passwords and PINs.")
        self.stdout.write("For the teller desk, create a staff login: python manage.py createsuperuser")
