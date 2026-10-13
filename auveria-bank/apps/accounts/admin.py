from django.contrib import admin

from .models import Account
from .money import naira


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("account_number", "owner_name", "status", "balance", "created_at")
    search_fields = ("account_number", "owner_name")
    fields = ("account_number", "owner_name", "customer", "status", "is_system", "balance")
    readonly_fields = ("account_number", "balance")

    @admin.display(description="Balance", ordering="balance_kobo")
    def balance(self, obj):
        return naira(obj.balance_kobo)
