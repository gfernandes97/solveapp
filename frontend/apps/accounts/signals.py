from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import UserProfile

LGPD_CONSENT_VERSION = "1.0"


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Cria UserProfile automaticamente para qualquer novo usuário (email ou Google)."""
    if created:
        UserProfile.objects.get_or_create(user=instance)


def record_lgpd_consent(sender, request, user, **kwargs):
    """
    Registra o consentimento LGPD no momento do cadastro (email ou social).
    Conectado ao sinal allauth.account.signals.user_signed_up via AccountsConfig.ready().
    """
    try:
        profile = user.profile
    except UserProfile.DoesNotExist:
        profile, _ = UserProfile.objects.get_or_create(user=user)

    if not profile.lgpd_consent_at:
        profile.lgpd_consent_at = timezone.now()
        profile.lgpd_consent_version = LGPD_CONSENT_VERSION
        profile.save(update_fields=["lgpd_consent_at", "lgpd_consent_version"])
