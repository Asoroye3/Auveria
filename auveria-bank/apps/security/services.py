import hashlib
import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.module_loading import import_string

from .models import OneTimeCode


class OtpError(Exception):
    pass


class OtpInvalid(OtpError):
    def __init__(self, attempts_remaining: int = 0):
        super().__init__("Invalid or expired code")
        self.attempts_remaining = attempts_remaining


class OtpRateLimited(OtpError):
    pass


def get_sms_provider():
    return import_string(settings.SMS_PROVIDER)()


def transfer_context(from_account: str, to_account: str, amount_kobo: int) -> str:
    """Ties a code to one exact transfer."""
    return hashlib.sha256(f"transfer:{from_account}:{to_account}:{amount_kobo}".encode()).hexdigest()


def _hash_code(code: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), code.encode(), hashlib.sha256).hexdigest()


@transaction.atomic
def issue_otp(customer, purpose: str, *, context: str = "", description: str = "") -> None:
    """Create a fresh code (invalidating older ones) and text it to the customer."""
    now = timezone.now()
    active = OneTimeCode.objects.filter(customer=customer, purpose=purpose, consumed_at__isnull=True)

    cooldown = settings.OTP_RESEND_COOLDOWN_SECONDS
    latest = active.order_by("-created_at").first()
    if cooldown and latest and (now - latest.created_at).total_seconds() < cooldown:
        raise OtpRateLimited("Please wait a moment before requesting another code")
    active.update(consumed_at=now)  # only the newest code is ever valid

    code = f"{secrets.randbelow(10 ** 6):06d}"
    OneTimeCode.objects.create(
        customer=customer, purpose=purpose, context_hash=context, code_hash=_hash_code(code),
        expires_at=now + timedelta(seconds=settings.OTP_TTL_SECONDS),
    )
    minutes = max(settings.OTP_TTL_SECONDS // 60, 1)
    message = f"Auveria Bank: {description}. Code: {code}. Valid for {minutes} min. Never share this code."
    get_sms_provider().send(customer.phone, message)


@transaction.atomic
def _check_otp(customer_id: int, purpose: str, code: str, context: str):
    """Returns ("ok" | "wrong" | "burned" | "none", attempts_remaining)."""
    now = timezone.now()
    otp = (
        OneTimeCode.objects.select_for_update()
        .filter(customer_id=customer_id, purpose=purpose, consumed_at__isnull=True, expires_at__gt=now)
        .order_by("-created_at")
        .first()
    )
    if otp is None:
        return "none", 0
    matches = hmac.compare_digest(otp.code_hash, _hash_code(code)) and otp.context_hash == context
    if matches:
        otp.consumed_at = now
        otp.save(update_fields=["consumed_at"])
        return "ok", 0
    otp.attempts += 1
    if otp.attempts >= settings.OTP_MAX_ATTEMPTS:
        otp.consumed_at = now  # too many guesses: burn the code
        otp.save(update_fields=["attempts", "consumed_at"])
        return "burned", 0
    otp.save(update_fields=["attempts"])
    return "wrong", settings.OTP_MAX_ATTEMPTS - otp.attempts


def verify_otp(customer, purpose: str, code: str, *, context: str = "") -> None:
    """Consume a valid code, or raise OtpInvalid. Wrong guesses are counted even
    though we raise, because the attempt is recorded in its own transaction."""
    status, remaining = _check_otp(customer.pk, purpose, code, context)
    if status != "ok":
        raise OtpInvalid(remaining if status == "wrong" else 0)
