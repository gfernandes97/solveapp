from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    label = "accounts"

    def ready(self):
        import apps.accounts.signals  # noqa: F401

        from allauth.account.signals import user_signed_up
        from apps.accounts.signals import record_lgpd_consent

        user_signed_up.connect(record_lgpd_consent)
