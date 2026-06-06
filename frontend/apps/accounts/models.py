from django.contrib.auth.models import User
from django.db import models


class UserProfile(models.Model):
    """Dados complementares do usuário e controle do onboarding."""

    STEP_PLAN = "plan"
    STEP_PROFILE = "profile"
    STEP_ACCOUNT = "account"
    STEP_DONE = "done"

    STEP_CHOICES = [
        (STEP_PLAN, "Escolha do plano"),
        (STEP_PROFILE, "Dados do perfil"),
        (STEP_ACCOUNT, "Primeira conta"),
        (STEP_DONE, "Concluído"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    phone = models.CharField(max_length=20, blank=True)
    avatar_url = models.URLField(blank=True)
    onboarding_step = models.CharField(
        max_length=20, choices=STEP_CHOICES, default=STEP_PLAN
    )
    onboarding_completed = models.BooleanField(default=False)
    # LGPD — account deletion with 30-day grace period
    pending_deletion = models.BooleanField(default=False)
    deletion_scheduled_at = models.DateTimeField(null=True, blank=True)
    # LGPD — consent tracking
    lgpd_consent_at = models.DateTimeField(null=True, blank=True)
    lgpd_consent_version = models.CharField(max_length=10, blank=True, default="1.0")
    # Sol tour — mostrado ao primeiro login
    sol_tour_shown = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Perfil do usuário"
        verbose_name_plural = "Perfis de usuários"

    def __str__(self):
        return f"Perfil de {self.user.email}"
