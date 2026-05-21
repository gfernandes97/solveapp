import json
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import OuterRef, Q, Subquery, Sum
from django.db.models.functions import TruncMonth
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from django.db.models import Prefetch

from apps.finances.models import (
    Account,
    AccountMonthSnapshot,
    Category,
    Goal,
    Investment,
    RecurringTransaction,
    Transaction,
)
from apps.dashboard.templatetags.finance_tags import AVAILABLE_ICONS

_MONTHS = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def _now_br():
    return datetime.now(ZoneInfo("America/Sao_Paulo"))


# ─── Parsers ───────────────────────────────────────────────────────────────

def _d(val, default=Decimal("0")):
    """POST value → Decimal, fallback to default."""
    try:
        return Decimal(str(val).replace(",", ".")) if val else default
    except (InvalidOperation, TypeError):
        return default


def _dt(val):
    """POST value → date or None."""
    if not val:
        return None
    try:
        return date.fromisoformat(str(val))
    except ValueError:
        return None


def _iv(val):
    """POST value → int or None."""
    try:
        v = str(val).strip()
        return int(v) if v else None
    except (ValueError, TypeError):
        return None


def _own_account(user, pk):
    return get_object_or_404(Account, pk=pk, user=user)


def _add_months(d, n):
    total = d.year * 12 + (d.month - 1) + n
    y, m = divmod(total, 12)
    return date(y, m + 1, 1)


def _amount_for_month(r, mo):
    """
    Exact amount contributed by RecurringTransaction r in calendar month mo.

    - Weekly/biweekly : counts actual weekday occurrences (4 or 5 Mondays, etc.)
    - Monthly         : full amount every month
    - Quarterly/semiannual/annual : full amount only in the months the payment
                        actually falls (every 3/6/12 months from start_date),
                        zero in all other months — never a spread average
    Both paths respect start_date and end_date.
    """
    next_mo = _add_months(mo, 1)

    # Outside active window
    if r.start_date.replace(day=1) >= next_mo:
        return Decimal("0")
    if r.end_date and r.end_date.replace(day=1) < mo:
        return Decimal("0")

    freq = r.frequency

    # ── Weekly / biweekly: count actual occurrences of the weekday ──────────
    if freq in (RecurringTransaction.FREQ_WEEKLY, RecurringTransaction.FREQ_BIWEEKLY):
        if r.day_of_week is None:
            return r.monthly_amount  # fallback if not set
        step = 7 if freq == RecurringTransaction.FREQ_WEEKLY else 14
        days_ahead = (r.day_of_week - r.start_date.weekday()) % 7
        first_occ = r.start_date + timedelta(days=days_ahead)
        if first_occ < mo:
            diff = (mo - first_occ).days
            n = diff // step
            first_occ += timedelta(days=n * step)
            if first_occ < mo:
                first_occ += timedelta(days=step)
        count = 0
        occ = first_occ
        while occ < next_mo:
            if r.end_date and occ > r.end_date:
                break
            count += 1
            occ += timedelta(days=step)
        return r.amount * Decimal(count)

    # ── Monthly: occurs in every active month ────────────────────────────────
    if freq == RecurringTransaction.FREQ_MONTHLY:
        return r.amount

    # ── Periodic (quarterly / semiannual / annual): one occurrence every N months
    period = {
        RecurringTransaction.FREQ_QUARTERLY:  3,
        RecurringTransaction.FREQ_SEMIANNUAL: 6,
        RecurringTransaction.FREQ_ANNUAL:     12,
    }.get(freq)
    if period:
        start_mo = r.start_date.replace(day=1)
        months_diff = (mo.year - start_mo.year) * 12 + (mo.month - start_mo.month)
        return r.amount if months_diff % period == 0 else Decimal("0")

    return r.monthly_amount  # fallback for unknown frequencies


def _compute_goal_progress(goals, today):
    """
    Returns {goal_id: {executed, provisioned, executed_pct, provisioned_pct}}
    executed   = variable credits + recurring amounts up to today
    provisioned = executed + future variable credits + future recurring up to deadline
    """
    goal_ids = [g.pk for g in goals]
    if not goal_ids:
        return {}

    today_mo = today.replace(day=1)

    tx_exec = {
        r["goal_id"]: r["total"]
        for r in Transaction.objects.filter(
            goal_id__in=goal_ids,
            type=Transaction.TYPE_CREDIT,
            date__lte=today,
            status=Transaction.STATUS_COMPLETED,
        ).values("goal_id").annotate(total=Sum("amount"))
    }
    tx_future = {
        r["goal_id"]: r["total"]
        for r in Transaction.objects.filter(
            goal_id__in=goal_ids,
            type=Transaction.TYPE_CREDIT,
            date__gt=today,
        ).values("goal_id").annotate(total=Sum("amount"))
    }

    goals_map = {g.pk: g for g in goals}
    rec_exec: dict = {}
    rec_future: dict = {}
    rec_qs = list(
        RecurringTransaction.objects.filter(
            goal_id__in=goal_ids,
            type=RecurringTransaction.TYPE_INCOME,
            is_active=True,
        )
    )
    for r in rec_qs:
        gid = r.goal_id
        g = goals_map.get(gid)
        if g is None:
            continue
        mo = r.start_date.replace(day=1)
        while mo <= today_mo:
            rec_exec[gid] = rec_exec.get(gid, Decimal("0")) + _amount_for_month(r, mo)
            mo = _add_months(mo, 1)
        end_mo = g.deadline.replace(day=1) if g.deadline else _add_months(today_mo, 12)
        mo = _add_months(today_mo, 1)
        while mo <= end_mo:
            rec_future[gid] = rec_future.get(gid, Decimal("0")) + _amount_for_month(r, mo)
            mo = _add_months(mo, 1)

    result = {}
    for g in goals:
        gid = g.pk
        executed = tx_exec.get(gid, Decimal("0")) + rec_exec.get(gid, Decimal("0"))
        provisioned = executed + tx_future.get(gid, Decimal("0")) + rec_future.get(gid, Decimal("0"))
        tgt = g.target_amount if g.target_amount else Decimal("1")
        result[gid] = {
            "executed": executed,
            "provisioned": provisioned,
            "executed_pct": min(int(executed / tgt * 100), 100),
            "provisioned_pct": min(int(provisioned / tgt * 100), 100),
        }
    return result


# ═══════════════════════════════════════════════════════════════════════════
# Dashboard overview
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def overview(request):
    now = _now_br()
    hour = now.hour
    if hour < 12:
        greeting = "Bom dia"
    elif hour < 18:
        greeting = "Boa tarde"
    else:
        greeting = "Boa noite"

    today = f"{now.day} de {_MONTHS[now.month - 1]} de {now.year}"
    first_name = request.user.first_name or request.user.email.split("@")[0]

    accounts = Account.objects.filter(user=request.user, is_active=True, include_in_total=True)
    cash_balance = accounts.exclude(type=Account.TYPE_INVESTMENT).aggregate(
        total=Sum("balance")
    )["total"] or Decimal("0")

    investments = Investment.objects.filter(user=request.user)
    inv_value = sum(i.current_value for i in investments)

    goals_qs = Goal.objects.filter(user=request.user, is_completed=False)
    goals_list = list(goals_qs.order_by("deadline"))
    goal_progress = _compute_goal_progress(goals_list, now.date())
    for g in goals_list:
        prog = goal_progress.get(g.pk, {})
        g.executed_amount = prog.get("executed", Decimal("0"))
        g.provisioned_amount = prog.get("provisioned", Decimal("0"))
        g.executed_pct = prog.get("executed_pct", 0)
        g.provisioned_pct = prog.get("provisioned_pct", 0)

    month_txs = Transaction.objects.filter(
        account__user=request.user,
        date__year=now.year,
        date__month=now.month,
        status=Transaction.STATUS_COMPLETED,
    )
    income = month_txs.filter(type=Transaction.TYPE_CREDIT, is_transfer=False).aggregate(t=Sum("amount"))["t"] or Decimal("0")
    expense = month_txs.filter(type=Transaction.TYPE_DEBIT, is_transfer=False).aggregate(t=Sum("amount"))["t"] or Decimal("0")
    month_balance = income - expense

    recent_txs = month_txs.filter(is_transfer=False).select_related("category", "account", "goal").order_by("-date", "-created_at")[:5]

    exp_cat_data = [
        {
            "name": r["category__name"] or "Sem categoria",
            "icon": r["category__icon"] or "more-horizontal",
            "color": r["category__color"] or "#64748B",
            "amount": r["total"],
            "pct": min(int(r["total"] / expense * 100), 100) if expense else 0,
        }
        for r in (
            month_txs.filter(type=Transaction.TYPE_DEBIT)
            .values("category__name", "category__icon", "category__color")
            .annotate(total=Sum("amount"))
            .order_by("-total")
        )
    ]

    return render(request, "dashboard/overview.html", {
        "greeting": greeting,
        "today": today,
        "first_name": first_name,
        "cash_balance": cash_balance,
        "inv_value": inv_value,
        "patrimonio": cash_balance + Decimal(str(inv_value)),
        "income": income,
        "expense": expense,
        "month_balance": month_balance,
        "goals": goals_list,
        "goals_count": goals_qs.count(),
        "recent_txs": recent_txs,
        "has_accounts": accounts.exists(),
        "exp_cat_data": exp_cat_data,
    })


# ═══════════════════════════════════════════════════════════════════════════
# Diagnóstico
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def diagnostico(request):
    now = _now_br()
    try:
        year = int(request.GET.get("ano", now.year))
        month = int(request.GET.get("mes", now.month))
        if not (1 <= month <= 12):
            raise ValueError
    except (ValueError, TypeError):
        year, month = now.year, now.month

    month_start = date(year, month, 1)
    next_month_start = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)

    accounts = Account.objects.filter(user=request.user, is_active=True, include_in_total=True)
    cash_balance = accounts.exclude(type=Account.TYPE_INVESTMENT).aggregate(
        total=Sum("balance")
    )["total"] or Decimal("0")
    investments = Investment.objects.filter(user=request.user)
    inv_value = Decimal(str(sum(i.current_value for i in investments)))
    patrimonio = cash_balance + inv_value

    month_txs = Transaction.objects.filter(
        account__user=request.user,
        date__year=year,
        date__month=month,
        status=Transaction.STATUS_COMPLETED,
    )
    income = month_txs.filter(type=Transaction.TYPE_CREDIT).aggregate(t=Sum("amount"))["t"] or Decimal("0")
    expense = month_txs.filter(type=Transaction.TYPE_DEBIT).aggregate(t=Sum("amount"))["t"] or Decimal("0")
    month_balance = income - expense

    fixed_inc_amt = month_txs.filter(
        type=Transaction.TYPE_CREDIT, is_recurring=True
    ).aggregate(t=Sum("amount"))["t"] or Decimal("0")
    var_inc_amt = income - fixed_inc_amt
    fixed_exp_amt = month_txs.filter(
        type=Transaction.TYPE_DEBIT, is_recurring=True
    ).aggregate(t=Sum("amount"))["t"] or Decimal("0")
    var_exp_amt = expense - fixed_exp_amt

    exp_cat_data = [
        {
            "name": r["category__name"] or "Sem categoria",
            "icon": r["category__icon"] or "more-horizontal",
            "color": r["category__color"] or "#64748B",
            "amount": r["total"],
            "pct": min(int(r["total"] / expense * 100), 100) if expense else 0,
        }
        for r in (
            month_txs.filter(type=Transaction.TYPE_DEBIT)
            .values("category__name", "category__icon", "category__color")
            .annotate(total=Sum("amount"))
            .order_by("-total")
        )
    ]
    inc_cat_data = [
        {
            "name": r["category__name"] or "Sem categoria",
            "icon": r["category__icon"] or "more-horizontal",
            "color": r["category__color"] or "#64748B",
            "amount": r["total"],
            "pct": min(int(r["total"] / income * 100), 100) if income else 0,
        }
        for r in (
            month_txs.filter(type=Transaction.TYPE_CREDIT)
            .values("category__name", "category__icon", "category__color")
            .annotate(total=Sum("amount"))
            .order_by("-total")
        )
    ]

    fixos_qs = RecurringTransaction.objects.filter(
        user=request.user,
        is_active=True,
        start_date__lt=next_month_start,
    ).filter(Q(end_date__isnull=True) | Q(end_date__gte=month_start))
    fixos_exp_list = list(fixos_qs.filter(type=RecurringTransaction.TYPE_EXPENSE).select_related("category"))
    fixos_inc_list = list(fixos_qs.filter(type=RecurringTransaction.TYPE_INCOME).select_related("category"))
    fixos_exp_total = sum(r.monthly_amount for r in fixos_exp_list)
    fixos_inc_total = sum(r.monthly_amount for r in fixos_inc_list)

    savings_rate = max(0, int((income - expense) / income * 100)) if income else 0
    commitment_rate = min(100, int(fixos_exp_total / income * 100)) if income else 0

    cash_pct_diag = int(cash_balance / patrimonio * 100) if patrimonio else 50
    inv_pct_diag = 100 - cash_pct_diag

    today_date = now.date()
    goals_qs = Goal.objects.filter(user=request.user, is_completed=False)
    goals_diag = []
    for g in goals_qs.order_by("deadline"):
        on_track = None
        months_left = None
        if g.deadline:
            days_remaining = (g.deadline - today_date).days
            months_left = max(round(days_remaining / 30), 0)
            needed = g.target_amount - g.current_amount
            if needed <= Decimal("0"):
                on_track = True
            elif days_remaining > 0:
                monthly_needed = needed / Decimal(str(max(days_remaining / 30, 0.5)))
                on_track = month_balance >= monthly_needed
            else:
                on_track = False
        goals_diag.append({"goal": g, "on_track": on_track, "months_left": months_left})

    if month == 1:
        prev_month, prev_year = 12, year - 1
    else:
        prev_month, prev_year = month - 1, year
    if month == 12:
        next_month, next_year = 1, year + 1
    else:
        next_month, next_year = month + 1, year

    return render(request, "dashboard/diagnostico.html", {
        "diag_month_name": _MONTHS[month - 1].capitalize(),
        "diag_year": year,
        "month": month,
        "year": year,
        "prev_month": prev_month,
        "prev_year": prev_year,
        "next_month": next_month,
        "next_year": next_year,
        "income": income,
        "expense": expense,
        "month_balance": month_balance,
        "fixed_inc_amt": fixed_inc_amt,
        "var_inc_amt": var_inc_amt,
        "fixed_exp_amt": fixed_exp_amt,
        "var_exp_amt": var_exp_amt,
        "exp_cat_data": exp_cat_data,
        "inc_cat_data": inc_cat_data,
        "fixos_exp_list": fixos_exp_list,
        "fixos_inc_list": fixos_inc_list,
        "fixos_exp_total": fixos_exp_total,
        "fixos_inc_total": fixos_inc_total,
        "savings_rate": savings_rate,
        "commitment_rate": commitment_rate,
        "cash_balance": cash_balance,
        "inv_value": inv_value,
        "patrimonio": patrimonio,
        "cash_pct_diag": cash_pct_diag,
        "inv_pct_diag": inv_pct_diag,
        "goals_diag": goals_diag,
    })


# ═══════════════════════════════════════════════════════════════════════════
# Investimentos
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def investimentos(request):
    accounts = Account.objects.filter(user=request.user, is_active=True)
    cash_accounts = accounts.exclude(type=Account.TYPE_INVESTMENT)
    cash_balance = cash_accounts.filter(include_in_total=True).aggregate(
        total=Sum("balance")
    )["total"] or Decimal("0")

    investments = Investment.objects.filter(user=request.user).select_related("account")
    inv_by_type: dict = {}
    inv_total = Decimal("0")
    for inv in investments:
        val = Decimal(str(inv.current_value))
        inv_by_type.setdefault(inv.get_type_display(), Decimal("0"))
        inv_by_type[inv.get_type_display()] += val
        inv_total += val

    goals = Goal.objects.filter(user=request.user, is_completed=False).order_by("deadline")
    inv_accounts = Account.objects.filter(user=request.user, type=Account.TYPE_INVESTMENT, is_active=True)

    return render(request, "dashboard/investimentos.html", {
        "cash_accounts": cash_accounts,
        "cash_balance": cash_balance,
        "inv_by_type": inv_by_type,
        "inv_total": inv_total,
        "patrimonio": cash_balance + inv_total,
        "goals": goals,
        "investments": investments,
        "inv_accounts": inv_accounts,
        "investment_types": Investment.TYPE_CHOICES,
    })


# ═══════════════════════════════════════════════════════════════════════════
# Lançamentos (list + create transaction)
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def lancamentos(request):
    now = _now_br()

    if request.method == "POST":
        tx_type = request.POST.get("tx_type", Transaction.TYPE_DEBIT)
        description = request.POST.get("description", "").strip()
        amount = _d(request.POST.get("amount"))
        tx_date = _dt(request.POST.get("date")) or now.date()
        account_pk = _iv(request.POST.get("account"))
        category_pk = _iv(request.POST.get("category"))
        is_recurring = "is_recurring" in request.POST
        notes = request.POST.get("notes", "").strip()

        goal_pk = _iv(request.POST.get("goal"))

        if description and amount > 0 and account_pk:
            try:
                acc = Account.objects.get(pk=account_pk, user=request.user)
                category = Category.objects.get(pk=category_pk) if category_pk else None
                goal = None
                if goal_pk:
                    try:
                        goal = Goal.objects.get(pk=goal_pk, user=request.user)
                    except Goal.DoesNotExist:
                        pass
                Transaction.objects.create(
                    account=acc,
                    category=category,
                    goal=goal,
                    amount=amount,
                    type=tx_type,
                    date=tx_date,
                    description=description,
                    notes=notes,
                    status=Transaction.STATUS_COMPLETED,
                    is_recurring=is_recurring,
                )
                if tx_type == Transaction.TYPE_CREDIT:
                    acc.balance += amount
                else:
                    acc.balance -= amount
                acc.save(update_fields=["balance"])
                if goal:
                    goal.current_amount += amount
                    goal.save(update_fields=["current_amount"])
            except (Account.DoesNotExist, Category.DoesNotExist):
                pass
        redirect_to = request.POST.get("redirect_to", "")
        if redirect_to == "projecao":
            return redirect("projecao")
        tab = "entradas" if tx_type == Transaction.TYPE_CREDIT else "saidas"
        return redirect(f"/dashboard/lancamentos/?ano={tx_date.year}&mes={tx_date.month}&tab={tab}")

    # ── GET ──
    try:
        year = int(request.GET.get("ano", now.year))
        month = int(request.GET.get("mes", now.month))
        if not (1 <= month <= 12):
            raise ValueError
    except (ValueError, TypeError):
        year, month = now.year, now.month

    month_name = _MONTHS[month - 1]
    tab = request.GET.get("tab", "todos")

    txs = Transaction.objects.filter(
        account__user=request.user,
        date__year=year,
        date__month=month,
    ).select_related("category", "account", "goal").order_by("-date", "-created_at")

    if tab == "entradas":
        txs = txs.filter(type=Transaction.TYPE_CREDIT)
    elif tab == "saidas":
        txs = txs.filter(type=Transaction.TYPE_DEBIT)

    income = Transaction.objects.filter(
        account__user=request.user, date__year=year, date__month=month,
        type=Transaction.TYPE_CREDIT, is_transfer=False,
    ).aggregate(t=Sum("amount"))["t"] or Decimal("0")
    expense = Transaction.objects.filter(
        account__user=request.user, date__year=year, date__month=month,
        type=Transaction.TYPE_DEBIT, is_transfer=False,
    ).aggregate(t=Sum("amount"))["t"] or Decimal("0")

    month_start = date(year, month, 1)
    next_month_start = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)

    # Only show fixos that are active during the viewed month
    recurring = RecurringTransaction.objects.filter(
        user=request.user,
        is_active=True,
        start_date__lt=next_month_start,
    ).filter(
        Q(end_date__isnull=True) | Q(end_date__gte=month_start)
    ).select_related("account", "category", "goal").order_by("type", "name")

    rec_income = sum(_amount_for_month(r, month_start) for r in recurring if r.type == RecurringTransaction.TYPE_INCOME)
    rec_expense = sum(_amount_for_month(r, month_start) for r in recurring if r.type == RecurringTransaction.TYPE_EXPENSE)

    accounts = Account.objects.filter(user=request.user, is_active=True)
    categories = Category.objects.filter(
        Q(user=request.user) | Q(user__isnull=True)
    ).order_by("type", "name")
    goals = Goal.objects.filter(user=request.user, is_completed=False).order_by("name")

    if month == 1:
        prev_month, prev_year = 12, year - 1
    else:
        prev_month, prev_year = month - 1, year
    if month == 12:
        next_month, next_year = 1, year + 1
    else:
        next_month, next_year = month + 1, year

    tab_defs = [("todos", "Todos"), ("entradas", "Entradas"), ("saidas", "Saídas"), ("fixos", "Fixos"), ("categorias", "Categorias")]

    return render(request, "dashboard/lancamentos.html", {
        "txs": txs,
        "tab": tab,
        "tab_defs": tab_defs,
        "month_name": month_name,
        "month": month,
        "year": year,
        "prev_month": prev_month,
        "prev_year": prev_year,
        "next_month": next_month,
        "next_year": next_year,
        "income": income,
        "expense": expense,
        "balance": income - expense,
        "recurring": recurring,
        "rec_income": rec_income,
        "rec_expense": rec_expense,
        "accounts": accounts,
        "categories": categories,
        "goals": goals,
        "today": now.date().isoformat(),
        "available_icons": AVAILABLE_ICONS,
    })


@login_required
@require_POST
def lancamento_editar(request, pk):
    tx = get_object_or_404(Transaction, pk=pk, account__user=request.user)
    old_amount = tx.amount
    old_type = tx.type
    old_goal_id = tx.goal_id

    description = request.POST.get("description", "").strip()
    amount = _d(request.POST.get("amount"), tx.amount)
    tx_date = _dt(request.POST.get("date")) or tx.date
    category_pk = _iv(request.POST.get("category"))
    goal_pk = _iv(request.POST.get("goal"))

    if description:
        acc = tx.account
        if old_type == Transaction.TYPE_CREDIT:
            acc.balance -= old_amount
        else:
            acc.balance += old_amount

        tx.description = description
        tx.amount = amount
        tx.date = tx_date
        tx.category = Category.objects.get(pk=category_pk) if category_pk else tx.category

        new_goal = None
        if goal_pk:
            try:
                new_goal = Goal.objects.get(pk=goal_pk, user=request.user)
            except Goal.DoesNotExist:
                pass

        new_goal_id = new_goal.pk if new_goal else None
        if old_goal_id == new_goal_id:
            if new_goal and old_amount != amount:
                new_goal.current_amount = max(Decimal("0"), new_goal.current_amount + (amount - old_amount))
                new_goal.save(update_fields=["current_amount"])
        else:
            if old_goal_id:
                old_goal = Goal.objects.get(pk=old_goal_id)
                old_goal.current_amount = max(Decimal("0"), old_goal.current_amount - old_amount)
                old_goal.save(update_fields=["current_amount"])
            if new_goal:
                new_goal.current_amount += amount
                new_goal.save(update_fields=["current_amount"])

        tx.goal = new_goal
        tx.save()

        if tx.type == Transaction.TYPE_CREDIT:
            acc.balance += amount
        else:
            acc.balance -= amount
        acc.save(update_fields=["balance"])

    return redirect("lancamentos")


@login_required
@require_POST
def lancamento_excluir(request, pk):
    tx = get_object_or_404(Transaction, pk=pk, account__user=request.user)
    acc = tx.account
    if tx.type == Transaction.TYPE_CREDIT:
        acc.balance -= tx.amount
    else:
        acc.balance += tx.amount
    acc.save(update_fields=["balance"])
    if tx.goal_id:
        goal = tx.goal
        goal.current_amount = max(Decimal("0"), goal.current_amount - tx.amount)
        goal.save(update_fields=["current_amount"])
    # If this is one side of a transfer, delete the paired transaction too
    if tx.is_transfer and tx.transfer_ref:
        pair = Transaction.objects.filter(transfer_ref=tx.transfer_ref).exclude(pk=tx.pk).first()
        if pair:
            pair_acc = pair.account
            if pair.type == Transaction.TYPE_CREDIT:
                pair_acc.balance -= pair.amount
            else:
                pair_acc.balance += pair.amount
            pair_acc.save(update_fields=["balance"])
            pair.delete()
    tx.delete()
    return redirect("lancamentos")


@login_required
@require_POST
def transferencia_criar(request):
    from_pk = _iv(request.POST.get("from_account"))
    to_pk = _iv(request.POST.get("to_account"))
    amount = _d(request.POST.get("amount"))
    tx_date = _dt(request.POST.get("date")) or _now_br().date()
    description = request.POST.get("description", "").strip()

    if not from_pk or not to_pk or from_pk == to_pk or amount <= 0:
        return redirect("lancamentos")
    try:
        from_acc = Account.objects.get(pk=from_pk, user=request.user)
        to_acc = Account.objects.get(pk=to_pk, user=request.user)
    except Account.DoesNotExist:
        return redirect("lancamentos")

    ref = str(uuid.uuid4())
    desc_out = description or f"Transf. → {to_acc.name}"
    desc_in = description or f"Transf. ← {from_acc.name}"

    Transaction.objects.create(
        account=from_acc, amount=amount, type=Transaction.TYPE_DEBIT,
        date=tx_date, description=desc_out, status=Transaction.STATUS_COMPLETED,
        is_transfer=True, transfer_ref=ref,
    )
    Transaction.objects.create(
        account=to_acc, amount=amount, type=Transaction.TYPE_CREDIT,
        date=tx_date, description=desc_in, status=Transaction.STATUS_COMPLETED,
        is_transfer=True, transfer_ref=ref,
    )
    from_acc.balance -= amount
    from_acc.save(update_fields=["balance"])
    to_acc.balance += amount
    to_acc.save(update_fields=["balance"])

    return redirect(f"/dashboard/lancamentos/?ano={tx_date.year}&mes={tx_date.month}&tab=todos")


# ═══════════════════════════════════════════════════════════════════════════
# Fixos (RecurringTransaction)
# ═══════════════════════════════════════════════════════════════════════════

@login_required
@require_POST
def fixo_criar(request):
    name = request.POST.get("name", "").strip()
    amount = _d(request.POST.get("amount"))
    fx_type = request.POST.get("type", RecurringTransaction.TYPE_EXPENSE)
    frequency = request.POST.get("frequency", RecurringTransaction.FREQ_MONTHLY)
    start_date = _dt(request.POST.get("start_date")) or _now_br().date()
    end_date = _dt(request.POST.get("end_date"))
    is_weekly = frequency in (RecurringTransaction.FREQ_WEEKLY, RecurringTransaction.FREQ_BIWEEKLY)
    day_of_week = _iv(request.POST.get("day_of_week")) if is_weekly else None
    day_of_month = _iv(request.POST.get("day_of_month")) if not is_weekly else None
    account_pk = _iv(request.POST.get("account"))
    category_pk = _iv(request.POST.get("category"))
    goal_pk = _iv(request.POST.get("goal"))
    notes = request.POST.get("notes", "").strip()

    if name and amount > 0 and account_pk:
        try:
            account = Account.objects.get(pk=account_pk, user=request.user)
        except Account.DoesNotExist:
            return redirect("/dashboard/lancamentos/?tab=fixos")
        category = Category.objects.get(pk=category_pk) if category_pk else None
        goal = None
        if goal_pk:
            try:
                goal = Goal.objects.get(pk=goal_pk, user=request.user)
            except Goal.DoesNotExist:
                pass
        RecurringTransaction.objects.create(
            user=request.user,
            account=account,
            category=category,
            goal=goal,
            name=name,
            amount=amount,
            type=fx_type,
            frequency=frequency,
            start_date=start_date,
            end_date=end_date,
            day_of_week=day_of_week,
            day_of_month=day_of_month,
            notes=notes,
        )
    return redirect("/dashboard/lancamentos/?tab=fixos")


@login_required
@require_POST
def fixo_editar(request, pk):
    rt = get_object_or_404(RecurringTransaction, pk=pk, user=request.user)
    name = request.POST.get("name", "").strip()
    account_pk = _iv(request.POST.get("account"))
    if name and account_pk:
        rt.name = name
        rt.amount = _d(request.POST.get("amount"), rt.amount)
        rt.type = request.POST.get("type", rt.type)
        rt.frequency = request.POST.get("frequency", rt.frequency)
        rt.start_date = _dt(request.POST.get("start_date")) or rt.start_date
        rt.end_date = _dt(request.POST.get("end_date"))
        try:
            rt.account = Account.objects.get(pk=account_pk, user=request.user)
        except Account.DoesNotExist:
            return redirect("/dashboard/lancamentos/?tab=fixos")
        freq = rt.frequency
        if freq in (RecurringTransaction.FREQ_WEEKLY, RecurringTransaction.FREQ_BIWEEKLY):
            rt.day_of_week = _iv(request.POST.get("day_of_week"))
            rt.day_of_month = None
        else:
            rt.day_of_month = _iv(request.POST.get("day_of_month"))
            rt.day_of_week = None
        category_pk = _iv(request.POST.get("category"))
        if category_pk:
            try:
                rt.category = Category.objects.get(pk=category_pk)
            except Category.DoesNotExist:
                rt.category = None
        else:
            rt.category = None
        goal_pk = _iv(request.POST.get("goal"))
        if goal_pk:
            try:
                rt.goal = Goal.objects.get(pk=goal_pk, user=request.user)
            except Goal.DoesNotExist:
                rt.goal = None
        else:
            rt.goal = None
        rt.notes = request.POST.get("notes", rt.notes).strip()
        rt.save()
    return redirect("/dashboard/lancamentos/?tab=fixos")


@login_required
@require_POST
def fixo_excluir(request, pk):
    rt = get_object_or_404(RecurringTransaction, pk=pk, user=request.user)
    rt.delete()
    return redirect("/dashboard/lancamentos/?tab=fixos")


# ═══════════════════════════════════════════════════════════════════════════
# Categorias (Category CRUD)
# ═══════════════════════════════════════════════════════════════════════════

@login_required
@require_POST
def categoria_criar(request):
    name = request.POST.get("name", "").strip()
    cat_type = request.POST.get("type", "expense")
    icon = request.POST.get("icon", "tag")
    color = request.POST.get("color", "#64748B")
    if name and cat_type in ("income", "expense"):
        Category.objects.get_or_create(
            user=request.user,
            name=name,
            type=cat_type,
            defaults={"icon": icon, "color": color},
        )
    return redirect("/dashboard/lancamentos/?tab=categorias")


@login_required
@require_POST
def categoria_excluir(request, pk):
    cat = get_object_or_404(Category, pk=pk, user=request.user)
    cat.delete()
    return redirect("/dashboard/lancamentos/?tab=categorias")


# ═══════════════════════════════════════════════════════════════════════════
# Contas (Account CRUD)
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def contas(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if name:
            acc_type = request.POST.get("type", Account.TYPE_CHECKING)
            Account.objects.create(
                user=request.user,
                name=name,
                type=acc_type,
                bank_name=request.POST.get("bank_name", "").strip(),
                color=request.POST.get("color", "#00C97A"),
                include_in_total="include_in_total" in request.POST,
                credit_limit=_d(request.POST.get("credit_limit")) if acc_type == Account.TYPE_CREDIT else None,
                closing_day=_iv(request.POST.get("closing_day")),
                due_day=_iv(request.POST.get("due_day")),
            )
        return redirect("contas")

    latest_balance_subq = AccountMonthSnapshot.objects.filter(
        account=OuterRef("pk")
    ).order_by("-month").values("balance")[:1]

    all_accounts = list(
        Account.objects.filter(user=request.user)
        .annotate(latest_balance=Subquery(latest_balance_subq))
        .order_by("type", "name")
        .prefetch_related(
            Prefetch("monthly_snapshots", queryset=AccountMonthSnapshot.objects.order_by("-month"))
        )
    )

    cash_accounts = [a for a in all_accounts if a.type in (Account.TYPE_CHECKING, Account.TYPE_SAVINGS, Account.TYPE_WALLET)]
    credit_accounts = [a for a in all_accounts if a.type == Account.TYPE_CREDIT]
    investment_accounts = [a for a in all_accounts if a.type == Account.TYPE_INVESTMENT]

    total_balance = sum(
        (acc.latest_balance for acc in all_accounts
         if acc.latest_balance is not None
         and acc.is_active
         and acc.include_in_total
         and acc.type != Account.TYPE_INVESTMENT),
        Decimal("0"),
    )

    return render(request, "dashboard/contas.html", {
        "cash_accounts": cash_accounts,
        "credit_accounts": credit_accounts,
        "investment_accounts": investment_accounts,
        "has_accounts": bool(all_accounts),
        "total_balance": total_balance,
        "account_types": Account.TYPE_CHOICES,
    })


@login_required
@require_POST
def snapshot_criar(request):
    account_pk = _iv(request.POST.get("account"))
    month_str = request.POST.get("month", "").strip()  # "YYYY-MM"
    balance = _d(request.POST.get("balance"))
    notes = request.POST.get("notes", "").strip()

    if account_pk and month_str:
        try:
            year_s, mo_s = month_str.split("-")
            mo = date(int(year_s), int(mo_s), 1)
            acc = Account.objects.get(pk=account_pk, user=request.user)
            latest = AccountMonthSnapshot.objects.filter(account=acc).order_by("-month").first()
            if latest and latest.month != mo and _add_months(latest.month, 1) < mo:
                messages.error(
                    request,
                    f"Não é possível registrar o saldo de {mo.strftime('%B/%Y')} sem antes preencher os meses "
                    f"intermediários. O último mês registrado para {acc.name} é {latest.month.strftime('%B/%Y')}.",
                )
                return redirect("contas")
            AccountMonthSnapshot.objects.update_or_create(
                account=acc,
                month=mo,
                defaults={"balance": balance, "notes": notes},
            )
        except (Account.DoesNotExist, ValueError):
            pass
    return redirect("contas")


@login_required
@require_POST
def snapshot_excluir(request, pk):
    snap = get_object_or_404(AccountMonthSnapshot, pk=pk, account__user=request.user)
    snap.delete()
    return redirect("contas")


@login_required
@require_POST
def conta_editar(request, pk):
    acc = _own_account(request.user, pk)
    name = request.POST.get("name", "").strip()
    if name:
        acc.name = name
        acc.type = request.POST.get("type", acc.type)
        acc.bank_name = request.POST.get("bank_name", "").strip()
        acc.color = request.POST.get("color", acc.color)
        acc.include_in_total = "include_in_total" in request.POST
        acc.is_active = "is_active" in request.POST
        if acc.type == Account.TYPE_CREDIT:
            cl = request.POST.get("credit_limit", "").strip()
            acc.credit_limit = _d(cl) if cl else acc.credit_limit
            acc.closing_day = _iv(request.POST.get("closing_day")) or acc.closing_day
            acc.due_day = _iv(request.POST.get("due_day")) or acc.due_day
        acc.save()
    return redirect("contas")


@login_required
@require_POST
def conta_excluir(request, pk):
    acc = _own_account(request.user, pk)
    acc.is_active = False
    acc.save(update_fields=["is_active"])
    return redirect("contas")


# ═══════════════════════════════════════════════════════════════════════════
# Metas (Goal CRUD)
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def metas(request):
    if request.method == "POST":
        action = request.POST.get("action", "create")
        if action == "aporte":
            pk = _iv(request.POST.get("goal_id"))
            amount = _d(request.POST.get("aporte_amount"))
            if pk and amount > 0:
                g = get_object_or_404(Goal, pk=pk, user=request.user)
                g.current_amount += amount
                if g.current_amount >= g.target_amount:
                    g.is_completed = True
                    from datetime import datetime as _dt_cls
                    g.completed_at = _dt_cls.now(ZoneInfo("America/Sao_Paulo"))
                g.save()
            return redirect("metas")

        name = request.POST.get("name", "").strip()
        if name:
            Goal.objects.create(
                user=request.user,
                name=name,
                description=request.POST.get("description", "").strip(),
                target_amount=_d(request.POST.get("target_amount")),
                current_amount=_d(request.POST.get("current_amount")),
                deadline=_dt(request.POST.get("deadline")),
                color=request.POST.get("color", "#00C97A"),
            )
        return redirect("metas")

    today = _now_br().date()
    goals = list(Goal.objects.filter(user=request.user).order_by("is_completed", "deadline"))
    active_goals = [g for g in goals if not g.is_completed]
    goal_progress = _compute_goal_progress(active_goals, today)
    for g in active_goals:
        prog = goal_progress.get(g.pk, {})
        g.executed_amount = prog.get("executed", Decimal("0"))
        g.provisioned_amount = prog.get("provisioned", Decimal("0"))
        g.executed_pct = prog.get("executed_pct", 0)
        g.provisioned_pct = prog.get("provisioned_pct", 0)
    return render(request, "dashboard/metas.html", {
        "goals": goals,
        "active": active_goals,
        "completed": [g for g in goals if g.is_completed],
    })


@login_required
@require_POST
def meta_editar(request, pk):
    g = get_object_or_404(Goal, pk=pk, user=request.user)
    name = request.POST.get("name", "").strip()
    if name:
        g.name = name
        g.description = request.POST.get("description", g.description).strip()
        g.target_amount = _d(request.POST.get("target_amount"), g.target_amount)
        g.current_amount = _d(request.POST.get("current_amount"), g.current_amount)
        g.deadline = _dt(request.POST.get("deadline")) or g.deadline
        g.color = request.POST.get("color", g.color)
        if g.current_amount >= g.target_amount and not g.is_completed:
            g.is_completed = True
        g.save()
    return redirect("metas")


@login_required
@require_POST
def meta_excluir(request, pk):
    get_object_or_404(Goal, pk=pk, user=request.user).delete()
    return redirect("metas")


# ═══════════════════════════════════════════════════════════════════════════
# Investimentos (Investment CRUD)
# ═══════════════════════════════════════════════════════════════════════════

@login_required
@require_POST
def investimento_criar(request):
    name = request.POST.get("name", "").strip()
    inv_type = request.POST.get("type", Investment.TYPE_OTHER)
    ticker = request.POST.get("ticker", "").strip().upper()
    quantity = _d(request.POST.get("quantity"), Decimal("1"))
    purchase_price = _d(request.POST.get("purchase_price"))
    current_price = _d(request.POST.get("current_price"), purchase_price)
    purchase_date = _dt(request.POST.get("purchase_date")) or _now_br().date()
    account_pk = _iv(request.POST.get("account"))

    if name and purchase_price > 0:
        account = None
        if account_pk:
            try:
                account = Account.objects.get(pk=account_pk, user=request.user)
            except Account.DoesNotExist:
                pass
        Investment.objects.create(
            user=request.user,
            account=account,
            name=name,
            ticker=ticker,
            type=inv_type,
            quantity=quantity,
            purchase_price=purchase_price,
            current_price=current_price,
            purchase_date=purchase_date,
        )
    return redirect("investimentos")


@login_required
@require_POST
def investimento_excluir(request, pk):
    get_object_or_404(Investment, pk=pk, user=request.user).delete()
    return redirect("investimentos")


@login_required
@require_POST
def investimento_editar(request, pk):
    inv = get_object_or_404(Investment, pk=pk, user=request.user)
    inv.current_price = _d(request.POST.get("current_price"), inv.current_price)
    inv.quantity = _d(request.POST.get("quantity"), inv.quantity)
    name = request.POST.get("name", "").strip()
    if name:
        inv.name = name
    inv.ticker = request.POST.get("ticker", inv.ticker).strip().upper()
    inv.save()
    return redirect("investimentos")


# ═══════════════════════════════════════════════════════════════════════════
# Projeção
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def projecao(request):
    now = _now_br()
    current_month = now.replace(day=1).date()

    def _int_param(key, default, lo=1, hi=60):
        try:
            return max(lo, min(hi, int(request.GET.get(key, default))))
        except (ValueError, TypeError):
            return default

    n_past = _int_param("n_past", 3)
    n_future = _int_param("n", 12)
    view_mode = request.GET.get("view", "table")
    if view_mode not in ("table", "chart"):
        view_mode = "table"

    start_month = _add_months(current_month, -n_past)
    end_month = _add_months(current_month, n_future)

    months = []
    m = start_month
    while m <= end_month:
        months.append(m)
        m = _add_months(m, 1)

    # ── Snapshot data ─────────────────────────────────────────────────────────
    # Query cash snapshots without aggregation so we can track per-account.
    cash_snap_qs = (
        AccountMonthSnapshot.objects
        .filter(
            account__user=request.user,
            account__is_active=True,
            account__include_in_total=True,
            account__type__in=[Account.TYPE_CHECKING, Account.TYPE_SAVINGS, Account.TYPE_WALLET],
        )
        .select_related("account")
    )
    cash_snaps: dict = {}                   # {month: total_balance}
    per_acc_snaps: dict = {}                # {month: {account_id: balance}}
    per_acc_names: dict = {}                # {account_id: name}
    per_acc_colors: dict = {}               # {account_id: color}
    for _snap in cash_snap_qs:
        _m = (_snap.month if isinstance(_snap.month, date) else _snap.month.date()).replace(day=1)
        cash_snaps[_m] = cash_snaps.get(_m, Decimal("0")) + _snap.balance
        per_acc_snaps.setdefault(_m, {})[_snap.account_id] = _snap.balance
        per_acc_names[_snap.account_id] = _snap.account.name
        per_acc_colors[_snap.account_id] = _snap.account.color

    inv_snap_qs = (
        AccountMonthSnapshot.objects
        .filter(
            account__user=request.user,
            account__is_active=True,
            account__type=Account.TYPE_INVESTMENT,
        )
        .values("month")
        .annotate(total=Sum("balance"))
    )
    inv_snaps: dict = {}
    for _row in inv_snap_qs:
        _m = _row["month"] if isinstance(_row["month"], date) else _row["month"].date()
        inv_snaps[_m.replace(day=1)] = _row["total"]

    # Expand transaction query back to the most recent prior cash snapshot so the
    # gap months are available when computing the initial balance anchor.
    prior_snaps = [(m, v) for m, v in cash_snaps.items() if m < start_month]
    if prior_snaps:
        anchor_m = max(prior_snaps, key=lambda x: x[0])[0]
        tx_query_start = _add_months(anchor_m, 1)
    else:
        tx_query_start = start_month

    raw = (
        Transaction.objects.filter(
            account__user=request.user,
            date__gte=tx_query_start,
            date__lt=_add_months(end_month, 1),
            status=Transaction.STATUS_COMPLETED,
            is_transfer=False,
        )
        .annotate(mo=TruncMonth("date"))
        .values("mo", "type", "is_recurring")
        .annotate(total=Sum("amount"))
    )

    actual: dict = {}
    for row in raw:
        mo = row["mo"] if isinstance(row["mo"], date) else row["mo"].date()
        mo = mo.replace(day=1)
        actual[(mo, row["type"], row["is_recurring"])] = row["total"] or Decimal("0")

    # Per-account net transactions for cash accounts (credit − debit per account per month).
    # Uses the same tx_query_start window as `raw`, so tx_query_start is already defined above.
    per_acc_tx_raw = (
        Transaction.objects.filter(
            account__user=request.user,
            account__is_active=True,
            account__include_in_total=True,
            account__type__in=[Account.TYPE_CHECKING, Account.TYPE_SAVINGS, Account.TYPE_WALLET],
            status=Transaction.STATUS_COMPLETED,
            date__gte=tx_query_start,
            date__lt=_add_months(end_month, 1),
        )
        .annotate(mo=TruncMonth("date"))
        .values("account_id", "mo", "type")
        .annotate(total=Sum("amount"))
    )
    acc_month_net: dict = {}  # {(account_id, month): net_amount}
    for _row in per_acc_tx_raw:
        _mo = (_row["mo"] if isinstance(_row["mo"], date) else _row["mo"].date()).replace(day=1)
        _aid = _row["account_id"]
        _delta = _row["total"] or Decimal("0")
        _key = (_aid, _mo)
        acc_month_net[_key] = acc_month_net.get(_key, Decimal("0")) + (
            _delta if _row["type"] == "credit" else -_delta
        )

    # Individual transactions per account per month — for the drill-down detail view.
    tx_detail_qs = (
        Transaction.objects.filter(
            account__user=request.user,
            account__is_active=True,
            account__include_in_total=True,
            account__type__in=[Account.TYPE_CHECKING, Account.TYPE_SAVINGS, Account.TYPE_WALLET],
            status=Transaction.STATUS_COMPLETED,
            date__gte=tx_query_start,
            date__lt=_add_months(end_month, 1),
        )
        .select_related("account", "category")
        .order_by("date", "id")
    )
    tx_by_acc_month: dict = {}  # {(account_id, month): [Transaction]}
    for _tx in tx_detail_qs:
        _mo = _tx.date.replace(day=1)
        tx_by_acc_month.setdefault((_tx.account_id, _mo), []).append(_tx)
        per_acc_names.setdefault(_tx.account_id, _tx.account.name)
        per_acc_colors.setdefault(_tx.account_id, _tx.account.color)

    recurring_list = list(RecurringTransaction.objects.filter(user=request.user, is_active=True))
    recurring_by_acc: dict = {}  # {account_id (or None): [RecurringTransaction]}
    for _r in recurring_list:
        recurring_by_acc.setdefault(_r.account_id, []).append(_r)

    def _fixed_for_month(mo, tx_type):
        total = Decimal("0")
        for r in recurring_list:
            if r.type != tx_type:
                continue
            total += _amount_for_month(r, mo)
        return total

    proj_fixed_income = _fixed_for_month(current_month, RecurringTransaction.TYPE_INCOME)
    proj_fixed_expense = _fixed_for_month(current_month, RecurringTransaction.TYPE_EXPENSE)

    anchor = (
        Account.objects.filter(user=request.user, is_active=True, include_in_total=True)
        .aggregate(t=Sum("balance"))["t"]
        or Decimal("0")
    )

    def _get(mo, typ, recurring):
        return actual.get((mo, typ, recurring), Decimal("0"))

    rows = []
    for mo in months:
        is_past = mo < current_month
        is_current = mo == current_month
        is_future = mo > current_month

        fi = _fixed_for_month(mo, RecurringTransaction.TYPE_INCOME)
        fe = _fixed_for_month(mo, RecurringTransaction.TYPE_EXPENSE)

        vi = _get(mo, "credit", False) + _get(mo, "credit", True)
        ve = _get(mo, "debit", False) + _get(mo, "debit", True)

        ti = fi + vi
        te = fe + ve
        net = ti - te

        rows.append({
            "month": mo,
            "label": f"{_MONTHS[mo.month - 1][:3].capitalize()}/{mo.year}",
            "is_past": is_past,
            "is_current": is_current,
            "is_future": is_future,
            "fixed_income": fi,
            "var_income": vi,
            "total_income": ti,
            "fixed_expense": fe,
            "var_expense": ve,
            "total_expense": te,
            "net": net,
            "end_balance": Decimal("0"),
            # filled in the forward pass below
            "inv_result": None,
            "result_total": None,
            "cash_snap": None,
            "batimento_ok": None,
        })

    # ── Per-account last-known balance initialisation ─────────────────────────
    # Seed acc_last_known from prior snapshot months then advance through the gap
    # to start_month, so carry-forward is correct on the first forward-pass row.
    acc_last_known: dict = {}  # {account_id: Decimal}
    if prior_snaps:
        for _pm in sorted(m for m in per_acc_snaps if m < start_month):
            for _aid, _bal in per_acc_snaps[_pm].items():
                acc_last_known[_aid] = _bal
        _gm = _add_months(anchor_m, 1)
        while _gm < start_month:
            for _aid in list(acc_last_known.keys()):
                if _aid not in per_acc_snaps.get(_gm, {}):
                    acc_last_known[_aid] += acc_month_net.get((_aid, _gm), Decimal("0"))
            for _aid, _bal in per_acc_snaps.get(_gm, {}).items():
                acc_last_known[_aid] = _bal
            _gm = _add_months(_gm, 1)

    # ── Initial balance anchor ─────────────────────────────────────────────────
    if prior_snaps:
        _, running_balance = max(prior_snaps, key=lambda x: x[0])
        # Walk from anchor_m+1 to start_month, accumulating net from actual transactions;
        # re-anchor at any intermediate cash snapshot found in the gap.
        m = _add_months(anchor_m, 1)
        while m < start_month:
            gap_net = (
                actual.get((m, "credit", False), Decimal("0"))
                + actual.get((m, "credit", True), Decimal("0"))
                - actual.get((m, "debit", False), Decimal("0"))
                - actual.get((m, "debit", True), Decimal("0"))
            )
            running_balance += gap_net
            if m in cash_snaps:
                running_balance = cash_snaps[m]
            m = _add_months(m, 1)
    else:
        # Fallback: accumulate fixos from the earliest recurring transaction start.
        if recurring_list:
            origin_month = min(r.start_date.replace(day=1) for r in recurring_list)
        else:
            origin_month = start_month
        running_balance = Decimal("0")
        m = origin_month
        while m < start_month:
            running_balance += _fixed_for_month(m, RecurringTransaction.TYPE_INCOME)
            running_balance -= _fixed_for_month(m, RecurringTransaction.TYPE_EXPENSE)
            m = _add_months(m, 1)

    # ── Forward pass: end_balance, investment results, batimento ──────────────
    # Batimento is checked per-account using consecutive monthly snapshots.
    # An account's FIRST snapshot is never compared (no prior month to check against).
    # Only when both snap[M] and snap[M-1] exist for the same account do we verify:
    #   snap[M] ≈ snap[M-1] + account_net[M]
    warnings_count = 0
    for row in rows:
        mo = row["month"]
        net = row["net"]

        cs = cash_snaps.get(mo)
        prev_mo = _add_months(mo, -1)
        iv = inv_snaps.get(mo)
        prev_iv = inv_snaps.get(prev_mo)

        # Resultado Investimentos: change in investment snapshot vs previous month
        if iv is not None and prev_iv is not None:
            inv_result = iv - prev_iv
        else:
            inv_result = None

        # Per-account batimento: only accounts with CONSECUTIVE monthly snapshots
        batimento_issues = []
        checked_any = False
        for aid, curr_bal in per_acc_snaps.get(mo, {}).items():
            prev_bal = per_acc_snaps.get(prev_mo, {}).get(aid)
            if prev_bal is None:
                continue  # First snapshot for this account (or a gap) — no warning
            checked_any = True
            acc_net = acc_month_net.get((aid, mo), Decimal("0"))
            diff = curr_bal - (prev_bal + acc_net)
            if abs(diff) >= Decimal("0.01"):
                batimento_issues.append({
                    "account_id": aid,
                    "account_name": per_acc_names.get(aid, f"Conta {aid}"),
                    "batimento_diff": diff,
                    "batimento_abs": abs(diff),
                    "batimento_abs_str": str(abs(diff)),
                })

        if batimento_issues:
            batimento_ok = False
            warnings_count += 1
        elif checked_any:
            batimento_ok = True
        else:
            batimento_ok = None

        # Capture opening balances for drill-down before acc_last_known is modified.
        opening_bal = dict(acc_last_known)

        # end_balance: merge snapshot accounts with carry-forward for non-snapshot ones.
        # When only a subset of known accounts has a snapshot in month M, carry forward
        # the others using actual transactions so the total stays incremental.
        snap_this_mo = per_acc_snaps.get(mo, {})
        if snap_this_mo:
            snap_sum = sum(snap_this_mo.values())
            carry_sum = Decimal("0")
            for _aid, _last in list(acc_last_known.items()):
                if _aid not in snap_this_mo:
                    _carried = _last + acc_month_net.get((_aid, mo), Decimal("0"))
                    acc_last_known[_aid] = _carried
                    carry_sum += _carried
            for _aid, _snap_bal in snap_this_mo.items():
                acc_last_known[_aid] = _snap_bal
            end_balance = snap_sum + carry_sum
        else:
            end_balance = running_balance + net
            for _aid in list(acc_last_known.keys()):
                acc_last_known[_aid] += acc_month_net.get((_aid, mo), Decimal("0"))

        running_balance = end_balance

        # ── Drill-down: per-account transaction breakdown ──────────────────────
        _drill_aids: set = set(per_acc_snaps.get(mo, {}).keys())
        for (_dk, _dm) in tx_by_acc_month:
            if _dm == mo:
                _drill_aids.add(_dk)
        if row["is_future"]:
            _drill_aids.update(_a for _a in recurring_by_acc if _a is not None)

        def _build_drill_entries(items_iter, is_future_row, acc_id):
            _run = opening_bal.get(acc_id)  # None when account has no prior snapshot
            _has_run = _run is not None
            _entries = []
            for _e_credit, _e_debit, _e_date, _e_desc, _e_is_rec, _e_cat, _e_is_transfer in items_iter:
                if _has_run:
                    _run += _e_credit - _e_debit
                _entries.append({
                    "date": _e_date,
                    "description": _e_desc,
                    "credit": _e_credit,
                    "debit": _e_debit,
                    "is_recurring": _e_is_rec,
                    "is_transfer": _e_is_transfer,
                    "category_name": _e_cat,
                    "running_balance": _run,
                })
            return _entries

        drill_accounts = []
        for _did in sorted(_drill_aids, key=lambda a: per_acc_names.get(a, "")):
            if row["is_future"]:
                _raw = []
                for _r in sorted(recurring_by_acc.get(_did, []), key=lambda r: r.name):
                    _amt = _amount_for_month(_r, mo)
                    if not _amt:
                        continue
                    _income = _r.type == RecurringTransaction.TYPE_INCOME
                    _raw.append((
                        _amt if _income else Decimal("0"),
                        Decimal("0") if _income else _amt,
                        None, _r.name, True,
                        _r.category.name if _r.category else None,
                        False,
                    ))
            else:
                _raw = []
                for _tx in tx_by_acc_month.get((_did, mo), []):
                    _isc = _tx.type == Transaction.TYPE_CREDIT
                    _raw.append((
                        _tx.amount if _isc else Decimal("0"),
                        Decimal("0") if _isc else _tx.amount,
                        _tx.date, _tx.description, _tx.is_recurring,
                        _tx.category.name if _tx.category else None,
                        _tx.is_transfer,
                    ))
            _entries = _build_drill_entries(_raw, row["is_future"], _did)
            _tc = sum(e["credit"] for e in _entries)
            _td = sum(e["debit"] for e in _entries)
            drill_accounts.append({
                "id": _did,
                "name": per_acc_names.get(_did, f"Conta {_did}"),
                "color": per_acc_colors.get(_did, "#64748B"),
                "txs": _entries,
                "total_credit": _tc,
                "total_debit": _td,
                "total_net": _tc - _td,
                "opening_balance": opening_bal.get(_did),
            })

        if row["is_future"]:
            _unassigned = [
                _r for _r in recurring_by_acc.get(None, [])
                if _amount_for_month(_r, mo)
            ]
            if _unassigned:
                _raw = []
                for _r in sorted(_unassigned, key=lambda r: r.name):
                    _amt = _amount_for_month(_r, mo)
                    _income = _r.type == RecurringTransaction.TYPE_INCOME
                    _raw.append((
                        _amt if _income else Decimal("0"),
                        Decimal("0") if _income else _amt,
                        None, _r.name, True,
                        _r.category.name if _r.category else None,
                        False,
                    ))
                _entries = _build_drill_entries(_raw, True, None)
                _tc = sum(e["credit"] for e in _entries)
                _td = sum(e["debit"] for e in _entries)
                drill_accounts.append({
                    "id": None,
                    "name": "Sem custódia",
                    "color": "#94A3B8",
                    "txs": _entries,
                    "total_credit": _tc,
                    "total_debit": _td,
                    "total_net": _tc - _td,
                    "opening_balance": None,
                })

        row["end_balance"] = end_balance
        row["inv_result"] = inv_result
        row["result_total"] = (net + inv_result) if inv_result is not None else None
        row["cash_snap"] = cs
        row["batimento_ok"] = batimento_ok
        row["batimento_issues"] = batimento_issues
        row["drill"] = drill_accounts

    proj_net_monthly = proj_fixed_income - proj_fixed_expense
    future_rows = [r for r in rows if r["is_future"]]
    proj_balance_n = future_rows[-1]["end_balance"] if future_rows else anchor

    chart_data = json.dumps({
        "labels": [r["label"] for r in rows],
        "income": [float(r["total_income"]) for r in rows],
        "expense": [float(r["total_expense"]) for r in rows],
        "balance": [float(r["end_balance"]) for r in rows],
        "types": [
            "current" if r["is_current"] else "future" if r["is_future"] else "past"
            for r in rows
        ],
    })

    cash_accounts = Account.objects.filter(
        user=request.user, is_active=True,
        type__in=[Account.TYPE_CHECKING, Account.TYPE_SAVINGS, Account.TYPE_WALLET],
    ).order_by("name")

    return render(request, "dashboard/projecao.html", {
        "rows": rows,
        "n_past": n_past,
        "n_future": n_future,
        "view_mode": view_mode,
        "anchor": anchor,
        "proj_fixed_income": proj_fixed_income,
        "proj_fixed_expense": proj_fixed_expense,
        "proj_net_monthly": proj_net_monthly,
        "proj_balance_n": proj_balance_n,
        "chart_data": chart_data,
        "warnings_count": warnings_count,
        "cash_accounts": cash_accounts,
    })


# ═══════════════════════════════════════════════════════════════════════════
# Settings
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def settings(request):
    return render(request, "dashboard/settings.html")
