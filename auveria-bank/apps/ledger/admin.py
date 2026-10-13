from django.contrib import admin

from apps.accounts.money import naira

from .models import LedgerEntry, Transaction


class ReadOnlyAdmin(admin.ModelAdmin):
    """Ledger data is immutable, so staff can look but never touch."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Transaction)
class TransactionAdmin(ReadOnlyAdmin):
    list_display = ("reference", "type", "status", "created_at")


@admin.register(LedgerEntry)
class LedgerEntryAdmin(ReadOnlyAdmin):
    list_display = ("transaction", "account", "direction", "amount", "created_at")

    @admin.display(description="Amount", ordering="amount_kobo")
    def amount(self, obj):
        return naira(obj.amount_kobo)
