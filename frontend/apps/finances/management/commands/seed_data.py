"""
Management command to seed realistic demo data for a given user.

Usage:
    python manage.py seed_data --email user@example.com
    python manage.py seed_data --email user@example.com --clear
"""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.finances.models import (
    Account,
    Category,
    Goal,
    Investment,
    RecurringTransaction,
    Transaction,
)


def _first_of(year, month):
    return date(year, month, 1)


def _add_months(d, n):
    total = d.year * 12 + (d.month - 1) + n
    y, m = divmod(total, 12)
    return date(y, m + 1, 1)


class Command(BaseCommand):
    help = "Seed realistic demo data for a user"

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True, help="User email")
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete existing finances data for this user before seeding",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        email = options["email"]
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise CommandError(f"No user found with email '{email}'")

        if options["clear"]:
            Transaction.objects.filter(account__user=user).delete()
            Account.objects.filter(user=user).delete()
            RecurringTransaction.objects.filter(user=user).delete()
            Goal.objects.filter(user=user).delete()
            Investment.objects.filter(user=user).delete()
            self.stdout.write(self.style.WARNING(f"Cleared existing data for {email}"))

        # ── Accounts ─────────────────────────────────────────────────────────
        nubank, _ = Account.objects.get_or_create(
            user=user,
            name="Nubank",
            defaults=dict(
                type=Account.TYPE_CHECKING,
                bank_name="Nubank",
                balance=Decimal("4820.00"),
                balance_date=date.today(),
                color="#8A05BE",
                include_in_total=True,
            ),
        )
        itau, _ = Account.objects.get_or_create(
            user=user,
            name="Itaú",
            defaults=dict(
                type=Account.TYPE_SAVINGS,
                bank_name="Itaú",
                balance=Decimal("12350.00"),
                balance_date=date.today(),
                color="#EC7000",
                include_in_total=True,
            ),
        )
        xp, _ = Account.objects.get_or_create(
            user=user,
            name="XP Investimentos",
            defaults=dict(
                type=Account.TYPE_INVESTMENT,
                bank_name="XP",
                balance=Decimal("0.00"),
                color="#2563EB",
                include_in_total=False,
            ),
        )

        self.stdout.write("  OK Contas criadas")

        # ── Categories (ensure defaults exist) ───────────────────────────────
        cat_salario, _ = Category.objects.get_or_create(
            user=None, name="Salário", defaults=dict(type="income", is_default=True)
        )
        cat_freelance, _ = Category.objects.get_or_create(
            user=None, name="Freelance", defaults=dict(type="income", is_default=True)
        )
        cat_aluguel, _ = Category.objects.get_or_create(
            user=None, name="Aluguel", defaults=dict(type="expense", is_default=True)
        )
        cat_alimentacao, _ = Category.objects.get_or_create(
            user=None, name="Alimentação", defaults=dict(type="expense", is_default=True)
        )
        cat_transporte, _ = Category.objects.get_or_create(
            user=None, name="Transporte", defaults=dict(type="expense", is_default=True)
        )
        cat_lazer, _ = Category.objects.get_or_create(
            user=None, name="Lazer", defaults=dict(type="expense", is_default=True)
        )
        cat_saude, _ = Category.objects.get_or_create(
            user=None, name="Saúde", defaults=dict(type="expense", is_default=True)
        )
        cat_streaming, _ = Category.objects.get_or_create(
            user=None, name="Assinaturas", defaults=dict(type="expense", is_default=True)
        )

        self.stdout.write("  OKCategorias verificadas")

        # ── Recurring transactions ────────────────────────────────────────────
        start = _first_of(date.today().year, 1)

        RecurringTransaction.objects.get_or_create(
            user=user,
            name="Salário",
            defaults=dict(
                type=RecurringTransaction.TYPE_INCOME,
                amount=Decimal("8500.00"),
                frequency=RecurringTransaction.FREQ_MONTHLY,
                start_date=start,
                day_of_month=5,
                account=nubank,
                category=cat_salario,
            ),
        )
        RecurringTransaction.objects.get_or_create(
            user=user,
            name="Aluguel",
            defaults=dict(
                type=RecurringTransaction.TYPE_EXPENSE,
                amount=Decimal("2200.00"),
                frequency=RecurringTransaction.FREQ_MONTHLY,
                start_date=start,
                day_of_month=10,
                account=nubank,
                category=cat_aluguel,
            ),
        )
        RecurringTransaction.objects.get_or_create(
            user=user,
            name="Netflix",
            defaults=dict(
                type=RecurringTransaction.TYPE_EXPENSE,
                amount=Decimal("39.90"),
                frequency=RecurringTransaction.FREQ_MONTHLY,
                start_date=start,
                day_of_month=15,
                account=nubank,
                category=cat_streaming,
            ),
        )
        RecurringTransaction.objects.get_or_create(
            user=user,
            name="Spotify",
            defaults=dict(
                type=RecurringTransaction.TYPE_EXPENSE,
                amount=Decimal("21.90"),
                frequency=RecurringTransaction.FREQ_MONTHLY,
                start_date=start,
                day_of_month=20,
                account=nubank,
                category=cat_streaming,
            ),
        )

        self.stdout.write("  OKLançamentos fixos criados")

        # ── Historical transactions (6 months) ───────────────────────────────
        today = date.today()
        current_month = today.replace(day=1)

        # Salário, Aluguel, Netflix, Spotify omitted here — they are RecurringTransactions
        # and already drive the fixed columns in projeção. Duplicating them as Transactions
        # would cause double-counting.
        monthly_txs = [
            # variable income
            ("Freelance design", Decimal("1200.00"), Transaction.TYPE_CREDIT, cat_freelance, nubank, 12, False),
            # variable expenses
            ("Supermercado", Decimal("680.00"), Transaction.TYPE_DEBIT, cat_alimentacao, nubank, 8, False),
            ("iFood", Decimal("320.00"), Transaction.TYPE_DEBIT, cat_alimentacao, nubank, 18, False),
            ("Uber", Decimal("180.00"), Transaction.TYPE_DEBIT, cat_transporte, nubank, 14, False),
            ("Academia", Decimal("120.00"), Transaction.TYPE_DEBIT, cat_saude, nubank, 7, False),
            ("Bar + lazer", Decimal("280.00"), Transaction.TYPE_DEBIT, cat_lazer, nubank, 22, False),
            ("Farmácia", Decimal("95.00"), Transaction.TYPE_DEBIT, cat_saude, nubank, 16, False),
        ]

        created_tx = 0
        for i in range(6, 0, -1):
            mo = _add_months(current_month, -i)
            for desc, amount, tx_type, cat, acc, day, is_rec in monthly_txs:
                tx_date = date(mo.year, mo.month, min(day, 28))
                if not Transaction.objects.filter(
                    account__user=user,
                    description=desc,
                    date=tx_date,
                ).exists():
                    Transaction.objects.create(
                        account=acc,
                        category=cat,
                        amount=amount,
                        type=tx_type,
                        date=tx_date,
                        description=desc,
                        status=Transaction.STATUS_COMPLETED,
                        is_recurring=is_rec,
                    )
                    created_tx += 1

        # Current month transactions
        for desc, amount, tx_type, cat, acc, day, is_rec in monthly_txs:
            tx_date = date(today.year, today.month, min(day, today.day))
            if not Transaction.objects.filter(
                account__user=user,
                description=desc,
                date=tx_date,
            ).exists():
                Transaction.objects.create(
                    account=acc,
                    category=cat,
                    amount=amount,
                    type=tx_type,
                    date=tx_date,
                    description=desc,
                    status=Transaction.STATUS_COMPLETED,
                    is_recurring=is_rec,
                )
                created_tx += 1

        self.stdout.write(f"  OK{created_tx} transações históricas criadas")

        # ── Goals ─────────────────────────────────────────────────────────────
        Goal.objects.get_or_create(
            user=user,
            name="Reserva de emergência",
            defaults=dict(
                description="6 meses de despesas fixas",
                target_amount=Decimal("25000.00"),
                current_amount=Decimal("12350.00"),
                deadline=date(today.year + 1, 6, 1),
                color="#00C97A",
            ),
        )
        Goal.objects.get_or_create(
            user=user,
            name="Viagem à Europa",
            defaults=dict(
                description="Portugal e Espanha — julho/2027",
                target_amount=Decimal("15000.00"),
                current_amount=Decimal("3200.00"),
                deadline=date(today.year + 1, 5, 1),
                color="#2563EB",
            ),
        )
        Goal.objects.get_or_create(
            user=user,
            name="Notebook novo",
            defaults=dict(
                target_amount=Decimal("8000.00"),
                current_amount=Decimal("2500.00"),
                color="#F59E0B",
            ),
        )

        self.stdout.write("  OKMetas criadas")

        # ── Investments ────────────────────────────────────────────────────────
        Investment.objects.get_or_create(
            user=user,
            name="Tesouro Selic 2029",
            defaults=dict(
                type=Investment.TYPE_FIXED_INCOME,
                quantity=Decimal("2.000000"),
                purchase_price=Decimal("13245.50"),
                current_price=Decimal("13890.20"),
                purchase_date=date(today.year - 1, 3, 15),
                account=xp,
            ),
        )
        Investment.objects.get_or_create(
            user=user,
            name="PETR4",
            ticker="PETR4",
            defaults=dict(
                type=Investment.TYPE_STOCKS,
                quantity=Decimal("100.000000"),
                purchase_price=Decimal("32.50"),
                current_price=Decimal("37.80"),
                purchase_date=date(today.year - 1, 6, 10),
                account=xp,
            ),
        )
        Investment.objects.get_or_create(
            user=user,
            name="MXRF11",
            ticker="MXRF11",
            defaults=dict(
                type=Investment.TYPE_FII,
                quantity=Decimal("200.000000"),
                purchase_price=Decimal("9.95"),
                current_price=Decimal("10.42"),
                purchase_date=date(today.year - 1, 9, 5),
                account=xp,
            ),
        )

        self.stdout.write("  OKInvestimentos criados")

        self.stdout.write(
            self.style.SUCCESS(f"\nDados semeados com sucesso para {email}!")
        )
