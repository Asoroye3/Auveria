import hashlib
import hmac
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone
from django.utils.module_loading import import_string

from .models import Customer, Tier


class OnboardingError(Exception):
    pass


def get_provider():
    return import_string(settings.KYC_PROVIDER)()


def get_tier(code: int) -> Tier:
    """Fetch a tier, creating it from settings.KYC_TIERS on first use."""
    tier, _ = Tier.objects.get_or_create(code=code, defaults=settings.KYC_TIERS[code])
    return tier


def _normalise(name: str) -> list:
    return sorted(name.lower().split())


def _identity_hash(bvn: str, nin: str) -> str:
    msg = f"{bvn}:{nin}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()


@transaction.atomic
def onboard_customer(*, bvn: str, nin: str, phone: str, provider=None) -> Customer:
    """Verify BVN + NIN through the provider and create a Tier 2 customer."""
    for label, value in (("BVN", bvn), ("NIN", nin)):
        if not (value.isdigit() and len(value) == 11):
            raise OnboardingError(f"{label} must be exactly 11 digits")

    provider = provider or get_provider()
    bvn_rec = provider.lookup_bvn(bvn)
    nin_rec = provider.lookup_nin(nin)
    if bvn_rec is None:
        raise OnboardingError("BVN not found")
    if nin_rec is None:
        raise OnboardingError("NIN not found")
    if _normalise(bvn_rec.full_name) != _normalise(nin_rec.full_name) or (
        bvn_rec.date_of_birth != nin_rec.date_of_birth
    ):
        raise OnboardingError("BVN and NIN records do not belong to the same person")

    identity_hash = _identity_hash(bvn, nin)
    if Customer.objects.filter(identity_hash=identity_hash).exists():
        raise OnboardingError("This identity is already registered")

    return Customer.objects.create(
        full_name=bvn_rec.full_name,
        date_of_birth=bvn_rec.date_of_birth,
        phone=phone,
        bvn_last4=bvn[-4:],
        nin_last4=nin[-4:],
        identity_hash=identity_hash,
        tier=get_tier(2),  # BVN + NIN both verified = Tier 2
        verified_at=timezone.now(),
    )


@transaction.atomic
def register_customer(*, bvn: str, nin: str, phone: str, password: str, provider=None) -> Customer:
    """Onboard a customer AND create their login (username = phone number)."""
    User = get_user_model()
    if User.objects.filter(username=phone).exists():
        raise OnboardingError("This phone number is already registered")
    customer = onboard_customer(bvn=bvn, nin=nin, phone=phone, provider=provider)
    customer.user = User.objects.create_user(username=phone, password=password)
    customer.save(update_fields=["user"])
    return customer


# ---------------------------------------------------------------- PIN ----

MAX_PIN_ATTEMPTS = 5
PIN_LOCK_MINUTES = 15


class PinError(Exception):
    pass


class PinNotSet(PinError):
    pass


class PinLocked(PinError):
    pass


class InvalidPin(PinError):
    def __init__(self, attempts_remaining: int):
        super().__init__("Incorrect PIN")
        self.attempts_remaining = attempts_remaining


@transaction.atomic
def _record_pin_attempt(customer_id: int, pin: str):
    """Returns ("ok" | "locked" | "wrong" | "not_set", attempts_remaining)."""
    c = Customer.objects.select_for_update().get(pk=customer_id)
    if not c.pin_hash:
        return "not_set", 0
    now = timezone.now()
    if c.pin_locked_until and c.pin_locked_until > now:
        return "locked", 0
    if check_password(pin, c.pin_hash):
        if c.pin_failed_attempts or c.pin_locked_until:
            c.pin_failed_attempts, c.pin_locked_until = 0, None
            c.save(update_fields=["pin_failed_attempts", "pin_locked_until"])
        return "ok", MAX_PIN_ATTEMPTS
    c.pin_failed_attempts += 1
    if c.pin_failed_attempts >= MAX_PIN_ATTEMPTS:
        c.pin_failed_attempts = 0
        c.pin_locked_until = now + timedelta(minutes=PIN_LOCK_MINUTES)
        c.save(update_fields=["pin_failed_attempts", "pin_locked_until"])
        return "locked", 0
    c.save(update_fields=["pin_failed_attempts"])
    return "wrong", MAX_PIN_ATTEMPTS - c.pin_failed_attempts


def verify_pin(customer: Customer, pin: str) -> None:
    # The attempt is recorded in its own transaction, then we raise outside it,
    # so a wrong guess is counted even though an exception follows.
    status, remaining = _record_pin_attempt(customer.pk, pin)
    if status == "not_set":
        raise PinNotSet("Set a transaction PIN first")
    if status == "locked":
        raise PinLocked(f"PIN locked after too many attempts. Try again in {PIN_LOCK_MINUTES} minutes")
    if status == "wrong":
        raise InvalidPin(remaining)


def set_pin(customer: Customer, new_pin: str, current_pin: str = None) -> None:
    if not (new_pin.isdigit() and len(new_pin) == 4) or len(set(new_pin)) == 1:
        raise ValueError("PIN must be 4 digits and not all the same digit")
    customer.refresh_from_db(fields=["pin_hash"])
    if customer.pin_hash:
        if not current_pin:
            raise ValueError("current_pin is required to change your PIN")
        verify_pin(customer, current_pin)
    customer.pin_hash = make_password(new_pin)
    customer.save(update_fields=["pin_hash"])
