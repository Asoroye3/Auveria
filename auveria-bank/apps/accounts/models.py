from django.conf import settings
from django.db import models, transaction

from . import nuban


class Account(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE"
        FROZEN = "FROZEN"
        CLOSED = "CLOSED"

    # Null until assigned, so several rows can exist before numbers are generated.
    account_number = models.CharField(max_length=10, unique=True, null=True, blank=True, editable=False)
    owner_name = models.CharField(max_length=200)
    customer = models.ForeignKey(
        "kyc.Customer", null=True, blank=True, on_delete=models.PROTECT, related_name="accounts"
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    # Bank-owned accounts (e.g. the cash vault). They may run negative.
    is_system = models.BooleanField(default=False)
    # Cached balance in kobo. The ledger is the source of truth.
    balance_kobo = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        creating = self.pk is None
        with transaction.atomic():
            super().save(*args, **kwargs)
            if creating and not self.account_number:
                serial = 100_000_000 + self.pk  # 9-digit serial
                self.account_number = nuban.generate(settings.AUVERIA_BANK_CODE, serial)
                super().save(update_fields=["account_number"])

    def __str__(self):
        return f"{self.account_number} - {self.owner_name}"
