"""
LGPD — Exclui permanentemente as contas cujo prazo de grace period (30 dias)
já expirou.

Uso:
    python manage.py purge_pending_deletions           # modo real
    python manage.py purge_pending_deletions --dry-run # apenas lista, não exclui

Agendar via cron (diário às 3h):
    0 3 * * * cd /app && python manage.py purge_pending_deletions >> /var/log/purge.log 2>&1
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import UserProfile


class Command(BaseCommand):
    help = "Exclui contas com solicitação de exclusão LGPD vencida (grace period de 30 dias)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Lista as contas a serem excluídas sem efetuar a exclusão",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        now = timezone.now()

        expired = UserProfile.objects.filter(
            pending_deletion=True,
            deletion_scheduled_at__lte=now,
        ).select_related("user")

        count = expired.count()

        if count == 0:
            self.stdout.write("Nenhuma conta com grace period vencido.")
            return

        self.stdout.write(f"{'[DRY-RUN] ' if dry_run else ''}Contas a excluir: {count}")

        for profile in expired:
            user = profile.user
            self.stdout.write(
                f"  {'[DRY-RUN] ' if dry_run else ''}Excluindo: {user.email} "
                f"(agendado em {profile.deletion_scheduled_at.date()})"
            )
            if not dry_run:
                user.delete()  # CASCADE remove todos os dados financeiros vinculados

        if not dry_run:
            self.stdout.write(
                self.style.SUCCESS(f"{count} conta(s) excluída(s) com sucesso.")
            )
        else:
            self.stdout.write(self.style.WARNING("Dry-run concluído — nenhuma conta foi excluída."))
