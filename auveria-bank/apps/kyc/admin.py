from django.contrib import admin

from apps.accounts.money import naira

from .models import Customer, Tier


@admin.register(Tier)
class TierAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "daily_limit", "max_balance")

    @admin.display(description="Daily limit", ordering="daily_limit_kobo")
    def daily_limit(self, obj):
        return naira(obj.daily_limit_kobo)

    @admin.display(description="Max balance", ordering="max_balance_kobo")
    def max_balance(self, obj):
        return naira(obj.max_balance_kobo)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("full_name", "phone", "tier", "bvn_last4", "nin_last4", "verified_at")
    search_fields = ("full_name", "phone")
    readonly_fields = (
        "identity_hash", "bvn_last4", "nin_last4", "verified_at",
        "pin_failed_attempts", "pin_locked_until",
    )
    exclude = ("pin_hash",)
