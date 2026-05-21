from decimal import Decimal

from django.contrib.auth.models import User
from django.db import models


class Account(models.Model):
    """Conta financeira do usuário (corrente, poupança, cartão, investimento)."""

    TYPE_CHECKING = "checking"
    TYPE_SAVINGS = "savings"
    TYPE_CREDIT = "credit"
    TYPE_INVESTMENT = "investment"
    TYPE_WALLET = "wallet"

    TYPE_CHOICES = [
        (TYPE_CHECKING, "Conta Corrente"),
        (TYPE_SAVINGS, "Poupança"),
        (TYPE_CREDIT, "Cartão de Crédito"),
        (TYPE_INVESTMENT, "Investimentos"),
        (TYPE_WALLET, "Carteira"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="accounts")
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    bank_name = models.CharField(max_length=100, blank=True)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    balance_date = models.DateField(null=True, blank=True)
    # Campos exclusivos de cartão de crédito
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    closing_day = models.PositiveSmallIntegerField(null=True, blank=True)
    due_day = models.PositiveSmallIntegerField(null=True, blank=True)
    currency = models.CharField(max_length=3, default="BRL")
    color = models.CharField(max_length=7, default="#00C97A")
    include_in_total = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Conta"
        verbose_name_plural = "Contas"

    def __str__(self):
        return f"{self.name} ({self.user.email})"


class Category(models.Model):
    """Categoria de transação. user=None indica categoria padrão do sistema."""

    TYPE_INCOME = "income"
    TYPE_EXPENSE = "expense"
    TYPE_TRANSFER = "transfer"

    TYPE_CHOICES = [
        (TYPE_INCOME, "Receita"),
        (TYPE_EXPENSE, "Despesa"),
        (TYPE_TRANSFER, "Transferência"),
    ]

    # null/blank → categoria padrão do sistema, visível para todos
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, blank=True, related_name="categories"
    )
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=15, choices=TYPE_CHOICES)
    icon = models.CharField(max_length=50, blank=True)
    color = models.CharField(max_length=7, default="#64748B")
    is_default = models.BooleanField(default=False)
    parent = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="subcategories"
    )

    class Meta:
        ordering = ["type", "name"]
        verbose_name = "Categoria"
        verbose_name_plural = "Categorias"

    def __str__(self):
        return self.name


class Transaction(models.Model):
    """Lançamento financeiro (crédito ou débito) em uma conta."""

    TYPE_CREDIT = "credit"
    TYPE_DEBIT = "debit"

    TYPE_CHOICES = [
        (TYPE_CREDIT, "Crédito"),
        (TYPE_DEBIT, "Débito"),
    ]

    STATUS_PENDING = "pending"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pendente"),
        (STATUS_COMPLETED, "Realizada"),
        (STATUS_CANCELLED, "Cancelada"),
    ]

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="transactions")
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="transactions"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    date = models.DateField()
    description = models.CharField(max_length=200)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default=STATUS_COMPLETED)
    is_recurring = models.BooleanField(default=False)
    is_installment = models.BooleanField(default=False)
    installment_number = models.PositiveSmallIntegerField(null=True, blank=True)
    installment_total = models.PositiveSmallIntegerField(null=True, blank=True)
    goal = models.ForeignKey(
        "Goal", on_delete=models.SET_NULL, null=True, blank=True, related_name="contributions"
    )
    is_transfer = models.BooleanField(default=False)
    transfer_ref = models.CharField(max_length=36, blank=True, db_index=True)
    # Preenchido quando a transação veio de um extrato importado
    imported_from = models.ForeignKey(
        "Statement", on_delete=models.SET_NULL, null=True, blank=True, related_name="transactions"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "Transação"
        verbose_name_plural = "Transações"

    def __str__(self):
        return f"{self.description} — R${self.amount}"


class Statement(models.Model):
    """Extrato bancário importado (CSV ou OFX)."""

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="statements")
    file = models.FileField(upload_to="statements/%Y/%m/")
    original_filename = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    transaction_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-uploaded_at"]
        verbose_name = "Extrato"
        verbose_name_plural = "Extratos"

    def __str__(self):
        return f"{self.original_filename} — {self.account.name}"


class Budget(models.Model):
    """Limite de gasto mensal por categoria."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="budgets")
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="budgets")
    # Sempre o primeiro dia do mês (ex.: 2025-05-01)
    month = models.DateField()
    amount_limit = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "category", "month")
        ordering = ["-month", "category__name"]
        verbose_name = "Orçamento"
        verbose_name_plural = "Orçamentos"

    def __str__(self):
        return f"{self.user.email} — {self.category.name} ({self.month:%Y-%m})"


class Goal(models.Model):
    """Meta financeira (viagem, reserva de emergência, aposentadoria...)."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="goals")
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    target_amount = models.DecimalField(max_digits=12, decimal_places=2)
    current_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deadline = models.DateField(null=True, blank=True)
    icon = models.CharField(max_length=50, blank=True)
    color = models.CharField(max_length=7, default="#00C97A")
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["deadline", "-created_at"]
        verbose_name = "Meta"
        verbose_name_plural = "Metas"

    def __str__(self):
        return f"{self.name} — {self.user.email}"

    @property
    def progress_percent(self):
        if not self.target_amount:
            return 0
        return min(int((self.current_amount / self.target_amount) * 100), 100)


class RecurringTransaction(models.Model):
    """Lançamento recorrente (fixo) — salário, aluguel, assinatura, etc."""

    FREQ_WEEKLY = "weekly"
    FREQ_BIWEEKLY = "biweekly"
    FREQ_MONTHLY = "monthly"
    FREQ_QUARTERLY = "quarterly"
    FREQ_SEMIANNUAL = "semiannual"
    FREQ_ANNUAL = "annual"

    FREQUENCY_CHOICES = [
        (FREQ_WEEKLY, "Semanal"),
        (FREQ_BIWEEKLY, "Quinzenal"),
        (FREQ_MONTHLY, "Mensal"),
        (FREQ_QUARTERLY, "Trimestral"),
        (FREQ_SEMIANNUAL, "Semestral"),
        (FREQ_ANNUAL, "Anual"),
    ]

    TYPE_INCOME = "income"
    TYPE_EXPENSE = "expense"

    TYPE_CHOICES = [
        (TYPE_INCOME, "Entrada"),
        (TYPE_EXPENSE, "Saída"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="recurring_transactions")
    account = models.ForeignKey(
        Account, on_delete=models.SET_NULL, null=True, blank=True, related_name="recurring_transactions"
    )
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="recurring_transactions"
    )
    goal = models.ForeignKey(
        "Goal", on_delete=models.SET_NULL, null=True, blank=True, related_name="recurring_contributions"
    )
    name = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    # dia do mês (1-31) para frequências mensais/trimestrais/etc.
    day_of_month = models.PositiveSmallIntegerField(null=True, blank=True)
    # dia da semana (0=segunda) para frequências semanais/quinzenais
    day_of_week = models.PositiveSmallIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["type", "name"]
        verbose_name = "Lançamento Recorrente"
        verbose_name_plural = "Lançamentos Recorrentes"

    def __str__(self):
        return f"{self.name} ({self.get_frequency_display()}) — {self.user.email}"

    @property
    def monthly_amount(self):
        """Valor equivalente mensal para projeções."""
        factors = {
            self.FREQ_WEEKLY: Decimal("52") / Decimal("12"),
            self.FREQ_BIWEEKLY: Decimal("26") / Decimal("12"),
            self.FREQ_MONTHLY: Decimal("1"),
            self.FREQ_QUARTERLY: Decimal("1") / Decimal("3"),
            self.FREQ_SEMIANNUAL: Decimal("1") / Decimal("6"),
            self.FREQ_ANNUAL: Decimal("1") / Decimal("12"),
        }
        return self.amount * factors.get(self.frequency, Decimal("1"))


class AccountMonthSnapshot(models.Model):
    """Saldo registrado pelo usuário no fechamento de cada mês, por conta."""

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="monthly_snapshots")
    month = models.DateField()  # sempre dia 1 do mês
    balance = models.DecimalField(max_digits=12, decimal_places=2)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("account", "month")
        ordering = ["-month"]
        verbose_name = "Saldo Mensal"
        verbose_name_plural = "Saldos Mensais"

    def __str__(self):
        return f"{self.account.name} — {self.month:%Y-%m} — R${self.balance}"


class Investment(models.Model):
    """Item do portfólio de investimentos (disponível apenas no plano Pro)."""

    TYPE_STOCKS = "stocks"
    TYPE_FII = "fii"
    TYPE_FIXED_INCOME = "fixed_income"
    TYPE_CRYPTO = "crypto"
    TYPE_OTHER = "other"

    TYPE_CHOICES = [
        (TYPE_STOCKS, "Ações"),
        (TYPE_FII, "FIIs"),
        (TYPE_FIXED_INCOME, "Renda Fixa"),
        (TYPE_CRYPTO, "Cripto"),
        (TYPE_OTHER, "Outros"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="investments")
    account = models.ForeignKey(
        Account, on_delete=models.SET_NULL, null=True, blank=True, related_name="investments"
    )
    name = models.CharField(max_length=100)
    ticker = models.CharField(max_length=20, blank=True)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    quantity = models.DecimalField(max_digits=12, decimal_places=6, default=1)
    purchase_price = models.DecimalField(max_digits=12, decimal_places=2)
    current_price = models.DecimalField(max_digits=12, decimal_places=2)
    purchase_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["type", "name"]
        verbose_name = "Investimento"
        verbose_name_plural = "Investimentos"

    def __str__(self):
        return f"{self.ticker or self.name} — {self.user.email}"

    @property
    def total_invested(self):
        return self.quantity * self.purchase_price

    @property
    def current_value(self):
        return self.quantity * self.current_price

    @property
    def profit_loss(self):
        return self.current_value - self.total_invested
