from django.contrib import admin

from .models import Account, Budget, Category, Goal, Investment, Statement, Transaction


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "type", "balance", "is_active")
    list_filter = ("type", "is_active")
    search_fields = ("user__email", "name")
    raw_id_fields = ("user",)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "type", "user", "is_default")
    list_filter = ("type", "is_default")
    search_fields = ("name",)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("description", "amount", "type", "date", "status", "account")
    list_filter = ("type", "status", "date")
    search_fields = ("description", "account__user__email")
    raw_id_fields = ("account", "category")
    date_hierarchy = "date"


@admin.register(Statement)
class StatementAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "account", "uploaded_at", "processed", "transaction_count")
    list_filter = ("processed",)


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ("user", "category", "month", "amount_limit")
    list_filter = ("month",)
    raw_id_fields = ("user",)


@admin.register(Goal)
class GoalAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "target_amount", "current_amount", "deadline", "is_completed")
    list_filter = ("is_completed",)
    raw_id_fields = ("user",)


@admin.register(Investment)
class InvestmentAdmin(admin.ModelAdmin):
    list_display = ("name", "ticker", "type", "user", "quantity", "purchase_price", "current_price")
    list_filter = ("type",)
    search_fields = ("name", "ticker", "user__email")
    raw_id_fields = ("user",)
