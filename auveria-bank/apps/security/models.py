from django.db import models


class OneTimeCode(models.Model):
    """A short-lived code sent by SMS. Only a keyed hash of the code is stored."""

    class Purpose(models.TextChoices):
        TRANSFER = "TRANSFER"
        PIN_CHANGE = "PIN_CHANGE"

    customer = models.ForeignKey("kyc.Customer", on_delete=models.CASCADE, related_name="one_time_codes")
    purpose = models.CharField(max_length=16, choices=Purpose.choices)
    # For transfers: a hash of (from, to, amount), so a code only works for the
    # exact transfer it was sent for ("dynamic linking").
    context_hash = models.CharField(max_length=64, blank=True)
    code_hash = models.CharField(max_length=64)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["customer", "purpose", "consumed_at"])]
