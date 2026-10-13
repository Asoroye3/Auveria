from django.contrib.auth.password_validation import validate_password as django_validate_password
from rest_framework import serializers

from apps.accounts.models import Account
from apps.accounts.money import naira
from apps.ledger.models import LedgerEntry


class RegisterSerializer(serializers.Serializer):
    bvn = serializers.CharField(max_length=11)
    nin = serializers.CharField(max_length=11)
    phone = serializers.CharField(max_length=20)
    password = serializers.CharField(write_only=True, min_length=8)

    def validate_password(self, value):
        django_validate_password(value)
        return value


class LoginSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)
    password = serializers.CharField()


class SetPinSerializer(serializers.Serializer):
    pin = serializers.CharField(min_length=4, max_length=4)
    current_pin = serializers.CharField(required=False, allow_blank=True, max_length=4)
    otp = serializers.CharField(required=False, allow_blank=True, max_length=6)


class TransferSerializer(serializers.Serializer):
    from_account = serializers.CharField(max_length=10)
    to_account = serializers.CharField(max_length=10)
    amount_kobo = serializers.IntegerField(min_value=1)
    pin = serializers.CharField(min_length=4, max_length=4)
    otp = serializers.CharField(required=False, allow_blank=True, max_length=6)


class OtpRequestSerializer(serializers.Serializer):
    purpose = serializers.ChoiceField(choices=["TRANSFER", "PIN_CHANGE"])
    # Only needed for TRANSFER: the code is bound to exactly this transfer.
    from_account = serializers.CharField(max_length=10, required=False)
    to_account = serializers.CharField(max_length=10, required=False)
    amount_kobo = serializers.IntegerField(min_value=1, required=False)


class StaffMoneySerializer(serializers.Serializer):
    account_number = serializers.CharField(max_length=10)
    amount_kobo = serializers.IntegerField(min_value=1)


class AccountSerializer(serializers.ModelSerializer):
    balance_display = serializers.SerializerMethodField()

    class Meta:
        model = Account
        fields = ("account_number", "owner_name", "status", "balance_kobo", "balance_display")

    def get_balance_display(self, obj):
        return naira(obj.balance_kobo)


class EntrySerializer(serializers.ModelSerializer):
    reference = serializers.CharField(source="transaction.reference")
    type = serializers.CharField(source="transaction.type")
    amount_display = serializers.SerializerMethodField()

    class Meta:
        model = LedgerEntry
        fields = ("reference", "type", "direction", "amount_kobo", "amount_display", "created_at")

    def get_amount_display(self, obj):
        return naira(obj.amount_kobo)
