from django.db import models


class Transaction(models.Model):
    class Status(models.TextChoices):
        POSTED = "POSTED"
        REVERSED = "REVERSED"

    reference = models.CharField(max_length=64, unique=True)
    idempotency_key = models.CharField(max_length=128, unique=True)
    type = models.CharField(max_length=32)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.POSTED)
    reverses = models.OneToOneField("self", null=True, blank=True, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class LedgerEntry(models.Model):
    """Immutable. Amounts are integer kobo. Entries per transaction sum to zero."""

    class Direction(models.TextChoices):
        DEBIT = "DEBIT"
        CREDIT = "CREDIT"

    transaction = models.ForeignKey(Transaction, related_name="entries", on_delete=models.PROTECT)
    account = models.ForeignKey("accounts.Account", on_delete=models.PROTECT)
    direction = models.CharField(max_length=6, choices=Direction.choices)
    amount_kobo = models.PositiveBigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.CheckConstraint(check=models.Q(amount_kobo__gt=0), name="entry_amount_positive")]

    def save(self, *args, **kwargs):
        if self.pk:
            raise RuntimeError("Ledger entries are immutable; post a reversal instead.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("Ledger entries cannot be deleted.")
