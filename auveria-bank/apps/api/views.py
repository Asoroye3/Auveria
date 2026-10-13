from django.conf import settings
from django.contrib.auth import authenticate
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, BasePermission, IsAdminUser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.models import Account
from apps.accounts.money import naira, ngn
from apps.accounts.services import get_cash_account, open_account
from apps.kyc.models import Customer
from apps.kyc.services import (
    InvalidPin, OnboardingError, PinLocked, PinNotSet, register_customer, set_pin, verify_pin,
)
from apps.ledger.models import LedgerEntry, Transaction
from apps.ledger.services import (
    AccountNotActive, InsufficientFunds, LimitExceeded, deposit, transfer, withdraw,
)

from apps.security.models import OneTimeCode
from apps.security.services import OtpInvalid, OtpRateLimited, issue_otp, transfer_context, verify_otp

from .serializers import (
    AccountSerializer, EntrySerializer, LoginSerializer, OtpRequestSerializer, RegisterSerializer,
    SetPinSerializer, StaffMoneySerializer, TransferSerializer,
)

MAX_KEY_LENGTH = 100


class IsCustomer(BasePermission):
    """Authenticated AND linked to a verified customer profile."""

    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated
            and Customer.objects.filter(user=request.user).exists()
        )


def _error(message, status, **extra):
    return Response({"error": message, **extra}, status=status)


def _idempotency_key(request):
    key = request.headers.get("Idempotency-Key", "").strip()
    if not key:
        return None, _error("Idempotency-Key header is required", 400)
    if len(key) > MAX_KEY_LENGTH:
        return None, _error(f"Idempotency-Key must be at most {MAX_KEY_LENGTH} characters", 400)
    return key, None


def _pin_problem(exc):
    if isinstance(exc, InvalidPin):
        return _error("Incorrect PIN", 403, attempts_remaining=exc.attempts_remaining)
    if isinstance(exc, PinLocked):
        return _error(str(exc), 423)
    if isinstance(exc, PinNotSet):
        return _error(str(exc), 400)
    raise exc


def _otp_check(customer, purpose, code, context=""):
    """Returns an error Response, or None when the code is valid (and now used up)."""
    if not code:
        return _error("A one-time code is required for this action", 400, otp_required=True)
    try:
        verify_otp(customer, purpose, code, context=context)
    except OtpInvalid as exc:
        extra = {"attempts_remaining": exc.attempts_remaining} if exc.attempts_remaining else {}
        return _error("Invalid or expired code", 403, **extra)
    return None


def _mask_phone(phone):
    return f"{phone[:4]}****{phone[-3:]}" if len(phone) >= 8 else "****"


MONEY_ERRORS = (InsufficientFunds, LimitExceeded, AccountNotActive, ValueError)


def _money_problem(exc):
    if isinstance(exc, InsufficientFunds):
        return _error("Insufficient funds", 422)
    if isinstance(exc, LimitExceeded):
        return _error(str(exc), 422)
    if isinstance(exc, AccountNotActive):
        return _error(str(exc), 409)
    return _error(str(exc), 400)


def _tx_payload(tx, amount_kobo):
    return {"reference": tx.reference, "type": tx.type, "status": tx.status, "amount_kobo": amount_kobo}


# ------------------------------------------------------------------ auth ----

class RegisterView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "register"

    def post(self, request):
        s = RegisterSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                customer = register_customer(**s.validated_data)
                account = open_account(customer)
        except OnboardingError as exc:
            return _error(str(exc), 400)
        token, _ = Token.objects.get_or_create(user=customer.user)
        return Response(
            {
                "token": token.key,
                "customer": {"full_name": customer.full_name, "tier": customer.tier.code},
                "account_number": account.account_number,
            },
            status=201,
        )


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        s = LoginSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = authenticate(username=s.validated_data["phone"], password=s.validated_data["password"])
        if user is None:
            return _error("Invalid phone number or password", 400)
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key})


# ------------------------------------------------------------- customer ----

class WhoAmIView(APIView):
    """Lets the app decide which screen to show: customer app or teller desk."""

    def get(self, request):
        user = request.user
        if user.is_staff:
            role = "staff"
        elif Customer.objects.filter(user=user).exists():
            role = "customer"
        else:
            role = "none"
        return Response({"role": role, "name": user.get_full_name() or user.get_username()})


class MeView(APIView):
    """Who am I, what are my limits, and have I set a PIN yet?"""

    permission_classes = [IsCustomer]

    def get(self, request):
        c = Customer.objects.select_related("tier").get(user=request.user)
        return Response(
            {
                "full_name": c.full_name,
                "phone": _mask_phone(c.phone),
                "tier": c.tier.code,
                "tier_name": c.tier.name,
                "daily_limit_kobo": c.tier.daily_limit_kobo,
                "max_balance_kobo": c.tier.max_balance_kobo,
                "pin_set": bool(c.pin_hash),
                "otp_threshold_kobo": settings.OTP_TRANSFER_THRESHOLD_KOBO,
            }
        )


class SetPinView(APIView):
    permission_classes = [IsCustomer]

    def post(self, request):
        s = SetPinSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        customer = Customer.objects.get(user=request.user)
        if customer.pin_hash:  # changing a PIN needs a texted code; setting the first one doesn't
            problem = _otp_check(customer, OneTimeCode.Purpose.PIN_CHANGE, s.validated_data.get("otp"))
            if problem:
                return problem
        try:
            set_pin(customer, s.validated_data["pin"], s.validated_data.get("current_pin") or None)
        except ValueError as exc:
            return _error(str(exc), 400)
        except (InvalidPin, PinLocked, PinNotSet) as exc:
            return _pin_problem(exc)
        return Response({"detail": "PIN saved"})


class OtpRequestView(APIView):
    """Text a one-time code to the customer's phone."""

    permission_classes = [IsCustomer]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "otp"

    def post(self, request):
        s = OtpRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        customer = Customer.objects.get(user=request.user)

        if d["purpose"] == OneTimeCode.Purpose.TRANSFER:
            if not all(k in d for k in ("from_account", "to_account", "amount_kobo")):
                return _error("from_account, to_account and amount_kobo are required for TRANSFER", 400)
            src = Account.objects.filter(account_number=d["from_account"], customer=customer).first()
            if src is None:
                return _error("Source account not found", 404)
            dst = Account.objects.filter(account_number=d["to_account"], is_system=False).first()
            if dst is None:
                return _error("Destination account not found", 404)
            context = transfer_context(src.account_number, dst.account_number, d["amount_kobo"])
            description = f"confirm sending {ngn(d['amount_kobo'])} to {dst.account_number}"
        else:
            context = ""
            description = "confirm your PIN change"

        try:
            issue_otp(customer, d["purpose"], context=context, description=description)
        except OtpRateLimited as exc:
            return _error(str(exc), 429)
        return Response(
            {"detail": "Code sent", "sent_to": _mask_phone(customer.phone),
             "expires_in_seconds": settings.OTP_TTL_SECONDS}
        )


class AccountListView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request):
        customer = Customer.objects.get(user=request.user)
        accounts = Account.objects.filter(customer=customer).order_by("id")
        return Response(AccountSerializer(accounts, many=True).data)


class AccountLookupView(APIView):
    """Name enquiry: confirm who you're paying before you send."""

    permission_classes = [IsCustomer]

    def get(self, request, account_number):
        acct = Account.objects.filter(account_number=account_number, is_system=False).first()
        if acct is None:
            return _error("Account not found", 404)
        return Response({"account_number": acct.account_number, "account_name": acct.owner_name})


class StatementView(generics.ListAPIView):
    permission_classes = [IsCustomer]
    serializer_class = EntrySerializer

    def get_queryset(self):
        customer = Customer.objects.get(user=self.request.user)
        account = get_object_or_404(Account, account_number=self.kwargs["account_number"], customer=customer)
        return (
            LedgerEntry.objects.filter(account=account)
            .select_related("transaction")
            .order_by("-created_at", "-id")
        )


class TransferView(APIView):
    permission_classes = [IsCustomer]

    def post(self, request):
        key, problem = _idempotency_key(request)
        if problem:
            return problem
        s = TransferSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        customer = Customer.objects.get(user=request.user)

        src = Account.objects.filter(account_number=d["from_account"], customer=customer).first()
        if src is None:
            return _error("Source account not found", 404)
        dst = Account.objects.filter(account_number=d["to_account"], is_system=False).first()
        if dst is None:
            return _error("Destination account not found", 404)

        # Keys are namespaced per customer so nobody can replay someone else's key.
        tx_key = f"c{customer.id}:{key}"

        # A retry of a transfer that already went through must return the original
        # result, not demand a fresh PIN/OTP (the old code was already used up).
        existing = Transaction.objects.filter(idempotency_key=tx_key).first()
        if existing:
            debit = existing.entries.filter(direction="DEBIT").first()
            return Response(_tx_payload(existing, debit.amount_kobo), status=200)

        try:
            verify_pin(customer, d["pin"])
        except (InvalidPin, PinLocked, PinNotSet) as exc:
            return _pin_problem(exc)

        # Fail fast on obvious overdrafts, so a large transfer that can't succeed
        # doesn't use up (or demand) a one-time code. transfer() re-checks under lock.
        if src.balance_kobo < d["amount_kobo"]:
            return _error("Insufficient funds", 422)

        if d["amount_kobo"] >= settings.OTP_TRANSFER_THRESHOLD_KOBO:
            context = transfer_context(src.account_number, dst.account_number, d["amount_kobo"])
            problem = _otp_check(customer, OneTimeCode.Purpose.TRANSFER, d.get("otp"), context)
            if problem:
                return problem

        try:
            tx = transfer(
                from_account_id=src.id, to_account_id=dst.id, amount_kobo=d["amount_kobo"],
                idempotency_key=tx_key,
            )
        except MONEY_ERRORS as exc:
            return _money_problem(exc)
        return Response(_tx_payload(tx, d["amount_kobo"]), status=201)


# ---------------------------------------------------------------- staff ----

class _StaffMoneyView(APIView):
    """Cash desk operations: staff only."""

    permission_classes = [IsAdminUser]
    operation = None  # set by subclasses

    def post(self, request):
        key, problem = _idempotency_key(request)
        if problem:
            return problem
        s = StaffMoneySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        acct = Account.objects.filter(account_number=d["account_number"], is_system=False).first()
        if acct is None:
            return _error("Account not found", 404)
        try:
            tx = self.operation(
                account_id=acct.id, amount_kobo=d["amount_kobo"], idempotency_key=f"staff:{key}"
            )
        except MONEY_ERRORS as exc:
            return _money_problem(exc)
        return Response(_tx_payload(tx, d["amount_kobo"]), status=201)


class StaffDepositView(_StaffMoneyView):
    operation = staticmethod(deposit)


class StaffWithdrawalView(_StaffMoneyView):
    operation = staticmethod(withdraw)


class StaffAccountView(APIView):
    """Teller lookup: who owns this account, what's in it, what happened recently."""

    permission_classes = [IsAdminUser]

    def get(self, request, account_number):
        acct = (
            Account.objects.filter(account_number=account_number, is_system=False)
            .select_related("customer__tier")
            .first()
        )
        if acct is None:
            return _error("Account not found", 404)
        recent = (
            LedgerEntry.objects.filter(account=acct)
            .select_related("transaction")
            .order_by("-created_at", "-id")[:8]
        )
        data = dict(AccountSerializer(acct).data)
        data["tier"] = acct.customer.tier.code if acct.customer else None
        data["recent"] = EntrySerializer(recent, many=True).data
        return Response(data)


class StaffCashJournalView(APIView):
    """The cash desk's own book: net cash taken in, plus the latest deposits and withdrawals."""

    permission_classes = [IsAdminUser]

    def get(self, request):
        vault = get_cash_account()
        tx_ids = list(
            Transaction.objects.filter(type__in=["DEPOSIT", "WITHDRAWAL"])
            .order_by("-created_at", "-id")
            .values_list("id", flat=True)[:15]
        )
        entries = (
            LedgerEntry.objects.filter(transaction_id__in=tx_ids)
            .exclude(account=vault)
            .select_related("account", "transaction")
            .order_by("-transaction__created_at", "-transaction_id")
        )
        rows = [
            {
                "reference": e.transaction.reference,
                "type": e.transaction.type,
                "account_number": e.account.account_number,
                "account_name": e.account.owner_name,
                "amount_kobo": e.amount_kobo,
                "amount_display": naira(e.amount_kobo),
                "created_at": e.created_at,
            }
            for e in entries
        ]
        # The vault runs negative by exactly the net cash customers have handed in.
        return Response(
            {"net_cash_kobo": -vault.balance_kobo, "net_cash_display": naira(-vault.balance_kobo), "entries": rows}
        )
