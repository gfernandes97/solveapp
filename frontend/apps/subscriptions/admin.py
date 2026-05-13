from django.contrib import admin

from .models import Plan, Subscription


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "price", "max_accounts", "has_investments", "has_goals", "is_active")
    list_filter = ("is_active",)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "plan", "status", "started_at", "ends_at")
    list_filter = ("status", "plan")
    search_fields = ("user__email",)
    raw_id_fields = ("user",)
