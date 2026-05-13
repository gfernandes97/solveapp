from django.contrib.auth.models import User
from django.db import models


class Plan(models.Model):
    SLUG_FREE = "free"
    SLUG_ESSENCIAL = "essencial"
    SLUG_PRO = "pro"

    SLUG_CHOICES = [
        (SLUG_FREE, "Grátis"),
        (SLUG_ESSENCIAL, "Essencial"),
        (SLUG_PRO, "Pro"),
    ]

    slug = models.CharField(max_length=20, choices=SLUG_CHOICES, unique=True)
    name = models.CharField(max_length=50)
    price = models.DecimalField(max_digits=6, decimal_places=2)
    # null = ilimitado
    max_accounts = models.PositiveIntegerField(null=True, blank=True)
    has_investments = models.BooleanField(default=False)
    has_goals = models.BooleanField(default=False)
    has_advanced_reports = models.BooleanField(default=False)
    has_personalized_guidance = models.BooleanField(default=False)
    has_priority_support = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["price"]
        verbose_name = "Plano"
        verbose_name_plural = "Planos"

    def __str__(self):
        return f"{self.name} (R${self.price})"


class Subscription(models.Model):
    STATUS_ACTIVE = "active"
    STATUS_CANCELLED = "cancelled"
    STATUS_PAST_DUE = "past_due"
    STATUS_TRIALING = "trialing"

    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Ativa"),
        (STATUS_CANCELLED, "Cancelada"),
        (STATUS_PAST_DUE, "Em atraso"),
        (STATUS_TRIALING, "Trial"),
    ]

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="subscription"
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    started_at = models.DateTimeField(auto_now_add=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    # Preenchido no futuro ao integrar gateway (Stripe, Asaas, PagSeguro...)
    external_id = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = "Assinatura"
        verbose_name_plural = "Assinaturas"

    def __str__(self):
        return f"{self.user.email} — {self.plan.name} ({self.status})"

    @property
    def is_active(self):
        return self.status == self.STATUS_ACTIVE

    @property
    def can_use_investments(self):
        return self.is_active and self.plan.has_investments

    @property
    def can_use_goals(self):
        return self.is_active and self.plan.has_goals

    @property
    def can_add_account(self, current_count: int) -> bool:
        if self.plan.max_accounts is None:
            return True
        return current_count < self.plan.max_accounts
