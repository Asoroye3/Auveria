from django.conf import settings
from django.db import models


class Tier(models.Model):
    """KYC tier with limits (kobo). None means no cap."""

    code = models.PositiveSmallIntegerField(unique=True)
    name = models.CharField(max_length=50)
    daily_limit_kobo = models.BigIntegerField(null=True, blank=True)
    max_balance_kobo = models.BigIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"Tier {self.code} - {self.name}"


class Customer(models.Model):
    full_name = models.CharField(max_length=200)
    date_of_birth = models.DateField()
    phone = models.CharField(max_length=20)
    # We never store full BVN/NIN: only the last 4 digits for display, plus a
    # keyed hash so the same person can't onboard twice.
    bvn_last4 = models.CharField(max_length=4, blank=True)
    nin_last4 = models.CharField(max_length=4, blank=True)
    identity_hash = models.CharField(max_length=64, unique=True)
    tier = models.ForeignKey(Tier, on_delete=models.PROTECT, related_name="customers")
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Login identity and transaction PIN (the PIN is stored hashed, never raw).
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="customer"
    )
    pin_hash = models.CharField(max_length=128, blank=True)
    pin_failed_attempts = models.PositiveSmallIntegerField(default=0)
    pin_locked_until = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.full_name
