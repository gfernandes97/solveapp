import calendar
import json
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import OuterRef, Q, Subquery, Sum, DecimalField
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
    InvestmentTransaction,
    RecurringTransaction,
    Transaction,
)
from apps.dashboard.templatetags.finance_tags import AVAILABLE_ICONS
from apps.dashboard import achievements as ach

_MONTHS = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]

# All account types that can hold cash and/or investment positions.
# Credit cards are excluded — they only hold a debit balance.
_CUSTODY_TYPES = [
    Account.TYPE_CHECKING,
    Account.TYPE_SAVINGS,
    Account.TYPE_INVESTMENT,
    Account.TYPE_WALLET,
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


def _inv_total_from_txs(user, as_of=None):
    """Return total investment value derived from InvestmentTransaction history.

    Matches the calculation in the investimentos view: sum of (buy - sell + earnings)
    per investment, excluding positions where the net is <= 0 (fully exited).
    Never reads Investment.current_price or Investment.quantity directly, preventing
    stale model-field values from inflating the displayed patrimônio.

    Pass as_of to compute the value as it stood at a specific date (inclusive).
    """
    qs = InvestmentTransaction.objects.filter(user=user)
    if as_of is not None:
        qs = qs.filter(date__lte=as_of)
    rows = (
        qs
        .values("investment_id")
        .annotate(
            buy_total=Sum("amount", filter=Q(type=InvestmentTransaction.TYPE_BUY)),
            sell_total=Sum("amount", filter=Q(type=InvestmentTransaction.TYPE_SELL)),
            earn_total=Sum("amount", filter=Q(type=InvestmentTransaction.TYPE_EARNINGS)),
        )
    )
    total = Decimal("0")
    for row in rows:
        cost = (row["buy_total"] or Decimal("0")) - (row["sell_total"] or Decimal("0"))
        earn = row["earn_total"] or Decimal("0")
        current = cost + earn
        if current > 0:
            total += current
    return total


def _add_months(d, n):
    total = d.year * 12 + (d.month - 1) + n
    y, m = divmod(total, 12)
    return date(y, m + 1, 1)


def _proj_date(r, mo):
    """
    Returns the expected calendar date for a RecurringTransaction in month mo.
    Used to show a concrete date in past/current months instead of 'proj.'.
    """
    if r.frequency in (RecurringTransaction.FREQ_WEEKLY, RecurringTransaction.FREQ_BIWEEKLY):
        if r.day_of_week is not None:
            d = mo
            while d.weekday() != r.day_of_week:
                d += timedelta(days=1)
            return d
    # Monthly / quarterly / semiannual / annual
    # day_of_month overrides start_date.day when explicitly set (supports days 29-31
    # by clamping to the last day of months that are too short)
    target_day = r.day_of_month if r.day_of_month is not None else r.start_date.day
    max_day = calendar.monthrange(mo.year, mo.month)[1]
    return date(mo.year, mo.month, min(target_day, max_day))


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


def _expand_recurring(r, cutoff: date):
    """
    Yields (occurrence_date, amount) for every individual occurrence of
    RecurringTransaction r between r.start_date and min(r.end_date, cutoff).
    Uses the same date-placement rules as _proj_date / _amount_for_month.
    """
    end = min(r.end_date, cutoff) if r.end_date else cutoff
    freq = r.frequency

    if freq in (RecurringTransaction.FREQ_WEEKLY, RecurringTransaction.FREQ_BIWEEKLY):
        step = timedelta(days=7 if freq == RecurringTransaction.FREQ_WEEKLY else 14)
        days_ahead = (r.day_of_week - r.start_date.weekday()) % 7 if r.day_of_week is not None else 0
        occ = r.start_date + timedelta(days=days_ahead)
        while occ <= end:
            if occ >= r.start_date:
                yield (occ, r.amount)
            occ += step

    elif freq == RecurringTransaction.FREQ_MONTHLY:
        mo = r.start_date.replace(day=1)
        while mo <= end.replace(day=1):
            occ = _proj_date(r, mo)
            if r.start_date <= occ <= end:
                yield (occ, r.amount)
            mo = _add_months(mo, 1)

    else:  # quarterly / semiannual / annual
        period = {
            RecurringTransaction.FREQ_QUARTERLY:  3,
            RecurringTransaction.FREQ_SEMIANNUAL: 6,
            RecurringTransaction.FREQ_ANNUAL:     12,
        }.get(freq, 1)
        start_mo = r.start_date.replace(day=1)
        mo = start_mo
        while mo <= end.replace(day=1):
            months_diff = (mo.year - start_mo.year) * 12 + (mo.month - start_mo.month)
            if months_diff % period == 0:
                occ = _proj_date(r, mo)
                if r.start_date <= occ <= end:
                    yield (occ, r.amount)
            mo = _add_months(mo, 1)


def _compute_goal_progress(goals, today):
    """
    Returns {goal_id: {executed, provisioned, executed_pct, provisioned_pct}}

    executed    = RecurringTransaction credits for months up to today_mo (fixas já pagas)
                + Transaction credits with date <= today (variáveis realizadas)

    provisioned = executed
                + RecurringTransaction credits for months today_mo+1 → deadline (fixas futuras)
                + Transaction credits with date > today already in lançamentos (variáveis futuras)
    """
    goal_ids = [g.pk for g in goals]
    if not goal_ids:
        return {}

    today_mo = today.replace(day=1)
    goals_map = {g.pk: g for g in goals}

    # Variable transactions: past (realised) and future (already registered).
    # No type filter — goals track total commitment regardless of credit/debit direction.
    tx_exec = {
        r["goal_id"]: r["total"]
        for r in Transaction.objects.filter(
            goal_id__in=goal_ids,
            date__lte=today,
        ).values("goal_id").annotate(total=Sum("amount"))
    }
    tx_future = {
        r["goal_id"]: r["total"]
        for r in Transaction.objects.filter(
            goal_id__in=goal_ids,
            date__gt=today,
        ).values("goal_id").annotate(total=Sum("amount"))
    }

    # Recurring (fixed): split into past months (executed) and future months (provisioned).
    # No type filter — both expense and income recurring items linked to a goal count.
    rec_exec: dict = {}
    rec_future: dict = {}
    for r in RecurringTransaction.objects.filter(
        goal_id__in=goal_ids,
        is_active=True,
    ):
        gid = r.goal_id
        g = goals_map.get(gid)
        if g is None:
            continue

        # Past: every month from start up to and including today_mo
        mo = r.start_date.replace(day=1)
        while mo <= today_mo:
            amt = _amount_for_month(r, mo)
            if amt:
                rec_exec[gid] = rec_exec.get(gid, Decimal("0")) + amt
            mo = _add_months(mo, 1)

        # Future: today_mo+1 through goal deadline (or 12 months if no deadline)
        end_mo = g.deadline.replace(day=1) if g.deadline else _add_months(today_mo, 12)
        mo = _add_months(today_mo, 1)
        while mo <= end_mo:
            amt = _amount_for_month(r, mo)
            if amt:
                rec_future[gid] = rec_future.get(gid, Decimal("0")) + amt
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


def _projected_cash_balance(user, today):
    """
    Returns the actual total cash balance as of today.

    Algorithm:
      1. Get the latest AccountMonthSnapshot (≤ current_month) for each included
         checking/savings/wallet account.
      2. Project each account's balance forward month-by-month using only completed
         transactions (no recurring estimates) until current_month.
      3. Return the sum across all accounts.

    Accounts with no snapshot at all contribute 0.
    """
    current_mo = today.replace(day=1)

    snap_qs = list(
        AccountMonthSnapshot.objects
        .filter(
            account__user=user,
            account__is_active=True,
            account__include_in_total=True,
            account__type__in=_CUSTODY_TYPES,
            month__lte=current_mo,
        )
        .values("account_id", "month", "balance")
        .order_by("account_id", "month")
    )

    if not snap_qs:
        return Decimal("0")

    # Latest snapshot per account
    anchor_per_acc: dict = {}
    for row in snap_qs:
        s_mo = (row["month"] if isinstance(row["month"], date) else row["month"].date()).replace(day=1)
        anchor_per_acc[row["account_id"]] = (s_mo, row["balance"])

    # If all latest snapshots are already for current_mo, no projection needed
    if all(m >= current_mo for m, _ in anchor_per_acc.values()):
        return sum((bal for _, bal in anchor_per_acc.values()), Decimal("0"))

    earliest_mo = min(m for m, _ in anchor_per_acc.values())
    tx_start = _add_months(earliest_mo, 1)

    # Net transactions per (account_id, month) from tx_start to current_mo
    acc_net: dict = {}
    for row in (
        Transaction.objects
        .filter(
            account__user=user,
            account__is_active=True,
            account__include_in_total=True,
            account__type__in=_CUSTODY_TYPES,
            status=Transaction.STATUS_COMPLETED,
            date__gte=tx_start,
            date__lt=_add_months(current_mo, 1),
            is_transfer=False,
            is_investment=False,
        )
        .annotate(mo=TruncMonth("date"))
        .values("account_id", "mo", "type")
        .annotate(total=Sum("amount"))
    ):
        mo = (row["mo"] if isinstance(row["mo"], date) else row["mo"].date()).replace(day=1)
        key = (row["account_id"], mo)
        delta = row["total"] or Decimal("0")
        acc_net[key] = acc_net.get(key, Decimal("0")) + (delta if row["type"] == "credit" else -delta)

    # Subtract investment portfolio values so the result reflects liquid cash only.
    # Snapshots for custody/brokerage accounts may include the investment portfolio;
    # this mirrors the per_acc_snaps_liquid logic used in the projection rows.
    inv_per_acc: dict = {}
    for _row in (
        InvestmentTransaction.objects
        .filter(user=user, investment__account__isnull=False)
        .values("investment__account_id")
        .annotate(
            buys=Sum("amount", filter=Q(type=InvestmentTransaction.TYPE_BUY)),
            sells=Sum("amount", filter=Q(type=InvestmentTransaction.TYPE_SELL)),
            earns=Sum("amount", filter=Q(type=InvestmentTransaction.TYPE_EARNINGS)),
        )
    ):
        _aid = _row["investment__account_id"]
        if _aid:
            inv_per_acc[_aid] = (
                (_row["buys"] or Decimal("0"))
                - (_row["sells"] or Decimal("0"))
                + (_row["earns"] or Decimal("0"))
            )

    total = Decimal("0")
    for aid, (snap_mo, snap_bal) in anchor_per_acc.items():
        bal = (snap_bal - inv_per_acc.get(aid, Decimal("0")))
        mo = _add_months(snap_mo, 1)
        while mo <= current_mo:
            bal += acc_net.get((aid, mo), Decimal("0"))
            mo = _add_months(mo, 1)
        total += bal

    return total


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
    cash_balance = _projected_cash_balance(request.user, now.date())

    inv_value = _inv_total_from_txs(request.user)

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
    income = month_txs.filter(type=Transaction.TYPE_CREDIT, is_transfer=False, is_investment=False).aggregate(t=Sum("amount"))["t"] or Decimal("0")
    expense = month_txs.filter(type=Transaction.TYPE_DEBIT, is_transfer=False, is_investment=False).aggregate(t=Sum("amount"))["t"] or Decimal("0")
    month_balance = income - expense

    recent_txs = month_txs.filter(is_transfer=False, is_investment=False).select_related("category", "account", "goal").order_by("-date", "-created_at")[:5]

    exp_cat_data = [
        {
            "name": r["category__name"] or "Sem categoria",
            "icon": r["category__icon"] or "more-horizontal",
            "color": r["category__color"] or "#64748B",
            "amount": r["total"],
            "pct": min(int(r["total"] / expense * 100), 100) if expense else 0,
        }
        for r in (
            month_txs.filter(type=Transaction.TYPE_DEBIT, is_investment=False)
            .values("category__name", "category__icon", "category__color")
            .annotate(total=Sum("amount"))
            .order_by("-total")
        )
    ]

    today_expense = Transaction.objects.filter(
        account__user=request.user,
        date=now.date(),
        type=Transaction.TYPE_DEBIT,
        is_transfer=False,
        is_investment=False,
        status=Transaction.STATUS_COMPLETED,
    ).aggregate(t=Sum("amount"))["t"] or Decimal("0")

    latest_snap_subq = AccountMonthSnapshot.objects.filter(
        account=OuterRef("pk")
    ).order_by("-month").values("balance")[:1]
    credit_cards = []
    for acc in (
        Account.objects
        .filter(user=request.user, is_active=True, type=Account.TYPE_CREDIT, credit_limit__gt=0)
        .annotate(latest_balance=Subquery(latest_snap_subq))
    ):
        bal = acc.latest_balance or Decimal("0")
        limit = acc.credit_limit
        pct = min(int(bal / limit * 100), 100) if limit else 0
        acc.usage_pct = pct
        acc.usage_amount = bal
        acc.bar_color = "bg-red-500" if pct >= 80 else "bg-solar" if pct >= 50 else "bg-solve"
        credit_cards.append(acc)

    has_accounts = accounts.exists()
    no_snapshots = (
        has_accounts and
        not AccountMonthSnapshot.objects.filter(account__user=request.user).exists()
    )
    try:
        can_use_goals = request.user.subscription.can_use_goals
    except AttributeError:
        can_use_goals = False

    # ── Gamification ─────────────────────────────────────────────────────────
    # check_achievements runs silently — toasts come only from action triggers
    ach.check_achievements(request.user)
    health_score = ach.compute_health_score(request.user)
    streak = ach.compute_streak(request.user)
    achievements_list = ach.build_achievements_list(request.user)
    earned_count = sum(1 for a in achievements_list if a["earned"])
    total_pts = ach.compute_total_points(request.user)

    return render(request, "dashboard/overview.html", {
        "greeting": greeting,
        "today": today,
        "first_name": first_name,
        "cash_balance": cash_balance,
        "inv_value": inv_value,
        "patrimonio": cash_balance + inv_value,
        "income": income,
        "expense": expense,
        "month_balance": month_balance,
        "goals": goals_list,
        "goals_count": goals_qs.count(),
        "recent_txs": recent_txs,
        "has_accounts": has_accounts,
        "no_snapshots": no_snapshots,
        "can_use_goals": can_use_goals,
        "exp_cat_data": exp_cat_data,
        "today_expense": today_expense,
        "credit_cards": credit_cards,
        "health_score": health_score,
        "streak": streak,
        "achievements_list": achievements_list,
        "earned_count": earned_count,
        "total_achievements": len(ach.ACHIEVEMENTS),
        "total_pts": total_pts,
    })


# ═══════════════════════════════════════════════════════════════════════════
# Diagnóstico
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def diagnostico(request):
    now = _now_br()
    period = request.GET.get("period", "mes")
    if period not in ("mes", "ano", "12m", "24m", "inicio"):
        period = "mes"

    # ── Period boundaries ─────────────────────────────────────────────────────
    prev_year = next_year = prev_month = next_month = None
    year = month = None

    if period == "mes":
        try:
            year  = int(request.GET.get("ano", now.year))
            month = int(request.GET.get("mes", now.month))
            if not (1 <= month <= 12): raise ValueError
        except (ValueError, TypeError):
            year, month = now.year, now.month
        date_from = date(year, month, 1)
        date_to   = _add_months(date_from, 1)
        period_months = [date_from]
        period_label  = f"{_MONTHS[month - 1].capitalize()} {year}"
        _prev = _add_months(date_from, -1)
        _next = _add_months(date_from,  1)
        prev_month, prev_year = _prev.month, _prev.year
        next_month, next_year = _next.month, _next.year

    elif period == "ano":
        try:
            year = int(request.GET.get("ano", now.year))
        except (ValueError, TypeError):
            year = now.year
        date_from = date(year, 1, 1)
        if year < now.year:
            date_to    = date(year + 1, 1, 1)
            n_months   = 12
        else:
            date_to    = _add_months(date(now.year, now.month, 1), 1)
            n_months   = now.month
        period_months = [date(year, m, 1) for m in range(1, n_months + 1)]
        period_label  = str(year)
        prev_year, next_year = year - 1, year + 1

    elif period == "12m":
        date_to       = _add_months(date(now.year, now.month, 1), 1)
        date_from     = _add_months(date_to, -12)
        period_months = [_add_months(date_from, i) for i in range(12)]
        period_label  = "Últimos 12 meses"

    elif period == "24m":
        date_to       = _add_months(date(now.year, now.month, 1), 1)
        date_from     = _add_months(date_to, -24)
        period_months = [_add_months(date_from, i) for i in range(24)]
        period_label  = "Últimos 24 meses"

    else:  # inicio
        _first = (
            Transaction.objects.filter(account__user=request.user)
            .order_by("date").values("date").first()
        )
        if _first:
            _fd = _first["date"]
            if not isinstance(_fd, date): _fd = _fd.date()
            date_from = _fd.replace(day=1)
        else:
            date_from = date(now.year, now.month, 1)
        date_to  = _add_months(date(now.year, now.month, 1), 1)
        _n = (date_to.year - date_from.year) * 12 + (date_to.month - date_from.month)
        period_months = [_add_months(date_from, i) for i in range(max(_n, 1))]
        period_label  = "Desde o início"

    n_months_in_period = len(period_months)

    # ── Common data ───────────────────────────────────────────────────────────
    # For past periods, show patrimônio as of the end of the selected period.
    # For current/future periods, cap at today so we never project forward.
    patrimonio_ref = min(date_to - timedelta(days=1), now.date())
    cash_balance = _projected_cash_balance(request.user, patrimonio_ref)
    inv_value    = _inv_total_from_txs(request.user, as_of=patrimonio_ref)
    patrimonio   = cash_balance + inv_value

    period_txs = Transaction.objects.filter(
        account__user=request.user,
        date__gte=date_from,
        date__lt=date_to,
        status=Transaction.STATUS_COMPLETED,
    )

    fixos_qs = RecurringTransaction.objects.filter(
        user=request.user,
        is_active=True,
        start_date__lt=date_to,
    ).filter(Q(end_date__isnull=True) | Q(end_date__gte=date_from))
    fixos_exp_list = list(fixos_qs.filter(type=RecurringTransaction.TYPE_EXPENSE).select_related("category"))
    fixos_inc_list = list(fixos_qs.filter(type=RecurringTransaction.TYPE_INCOME).select_related("category"))

    def _period_fixo_amt(r):
        return sum(_amount_for_month(r, m) for m in period_months)

    fixos_exp_total = sum(_period_fixo_amt(r) for r in fixos_exp_list)
    fixos_inc_total = sum(_period_fixo_amt(r) for r in fixos_inc_list)

    # Monthly-equivalent totals for "Fixas" header badges
    fixos_exp_monthly_total = sum(r.monthly_amount for r in fixos_exp_list)
    fixos_inc_monthly_total = sum(r.monthly_amount for r in fixos_inc_list)
    fixos_exp_approx = any(r.frequency != RecurringTransaction.FREQ_MONTHLY for r in fixos_exp_list)
    fixos_inc_approx = any(r.frequency != RecurringTransaction.FREQ_MONTHLY for r in fixos_inc_list)

    var_inc_amt    = period_txs.filter(type=Transaction.TYPE_CREDIT, is_transfer=False, is_investment=False).aggregate(t=Sum("amount"))["t"] or Decimal("0")
    var_exp_amt    = period_txs.filter(type=Transaction.TYPE_DEBIT,  is_transfer=False, is_investment=False).aggregate(t=Sum("amount"))["t"] or Decimal("0")
    # Only earnings and dividends count as income — buy/sell boletas are excluded
    earn_amt = period_txs.filter(
        type=Transaction.TYPE_CREDIT, is_investment=True,
        inv_boleta__type=InvestmentTransaction.TYPE_EARNINGS,
    ).aggregate(t=Sum("amount"))["t"] or Decimal("0")
    div_amt = period_txs.filter(
        type=Transaction.TYPE_CREDIT, is_investment=True,
        inv_boleta__type=InvestmentTransaction.TYPE_DIVIDENDS,
    ).aggregate(t=Sum("amount"))["t"] or Decimal("0")
    inv_income_amt = earn_amt + div_amt

    fixed_inc_amt = fixos_inc_total
    fixed_exp_amt = fixos_exp_total
    income        = var_inc_amt + fixos_inc_total + inv_income_amt
    expense       = var_exp_amt + fixos_exp_total
    month_balance = income - expense

    exp_cat_data = [
        {
            "name":   r["category__name"] or "Sem categoria",
            "icon":   r["category__icon"] or "more-horizontal",
            "color":  r["category__color"] or "#64748B",
            "amount": r["total"],
            "pct":    min(int(r["total"] / var_exp_amt * 100), 100) if var_exp_amt else 0,
        }
        for r in (
            period_txs.filter(type=Transaction.TYPE_DEBIT, is_transfer=False, is_investment=False)
            .values("category__name", "category__icon", "category__color")
            .annotate(total=Sum("amount"))
            .order_by("-total")
        )
    ]
    inc_cat_data = [
        {
            "name":   r["category__name"] or "Sem categoria",
            "icon":   r["category__icon"] or "more-horizontal",
            "color":  r["category__color"] or "#64748B",
            "amount": r["total"],
            "pct":    min(int(r["total"] / var_inc_amt * 100), 100) if var_inc_amt else 0,
        }
        for r in (
            period_txs.filter(type=Transaction.TYPE_CREDIT, is_transfer=False, is_investment=False)
            .values("category__name", "category__icon", "category__color")
            .annotate(total=Sum("amount"))
            .order_by("-total")
        )
    ]

    def _merge_cat(base_data, fixos_list, total):
        merged = {}
        for cat in base_data:
            merged[cat["name"]] = dict(cat)
        for r in fixos_list:
            amt = _period_fixo_amt(r)
            if not amt:
                continue
            cat_name = r.category.name if r.category else "Sem categoria"
            if cat_name in merged:
                merged[cat_name]["amount"] += amt
            else:
                merged[cat_name] = {
                    "name":  cat_name,
                    "icon":  r.category.icon if r.category else "more-horizontal",
                    "color": r.category.color if r.category else "#64748B",
                    "amount": amt,
                }
        result = sorted(merged.values(), key=lambda x: -x["amount"])
        for cat in result:
            cat["pct"] = min(int(cat["amount"] / total * 100), 100) if total else 0
        return result

    all_exp_cat_data = _merge_cat(exp_cat_data, fixos_exp_list, expense)
    all_inc_cat_data = _merge_cat(inc_cat_data, fixos_inc_list, income)

    # Append earnings and dividends as separate slices — buy/sell excluded
    if earn_amt:
        all_inc_cat_data.append({
            "name":   "Rendimentos",
            "icon":   "trending-up",
            "color":  "#06B6D4",
            "amount": earn_amt,
        })
    if div_amt:
        all_inc_cat_data.append({
            "name":   "Dividendos",
            "icon":   "dollar-sign",
            "color":  "#F59E0B",
            "amount": div_amt,
        })
    if earn_amt or div_amt:
        all_inc_cat_data.sort(key=lambda x: -x["amount"])

    inc_chart_total = sum(cat["amount"] for cat in all_inc_cat_data) or Decimal("1")
    exp_chart_total = sum(cat["amount"] for cat in all_exp_cat_data) or Decimal("1")
    for cat in all_inc_cat_data:
        cat["pct"] = min(int(cat["amount"] / inc_chart_total * 100), 100)
    for cat in all_exp_cat_data:
        cat["pct"] = min(int(cat["amount"] / exp_chart_total * 100), 100)

    savings_rate    = max(0, int((income - expense) / income * 100)) if income else 0
    commitment_rate = min(100, int(fixos_exp_total / income * 100)) if income else 0

    cash_pct_diag = int(cash_balance / patrimonio * 100) if patrimonio else 50
    inv_pct_diag  = 100 - cash_pct_diag

    today_date = now.date()
    goals_qs   = Goal.objects.filter(user=request.user, is_completed=False)
    goals_diag = []
    avg_monthly_balance = (
        month_balance / Decimal(str(n_months_in_period)) if n_months_in_period > 1 else month_balance
    )
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
                on_track = avg_monthly_balance >= monthly_needed
            else:
                on_track = False
        goals_diag.append({"goal": g, "on_track": on_track, "months_left": months_left})

    has_data = income > 0 or expense > 0

    balance_label = {
        "mes":    "Saldo do Mês",
        "ano":    "Saldo do Ano",
        "12m":    "Saldo 12M",
        "24m":    "Saldo 24M",
        "inicio": "Saldo desde o Início",
    }.get(period, "Saldo do Período")

    exp_chart_json = json.dumps({
        "labels":  [cat["name"] for cat in all_exp_cat_data],
        "amounts": [float(cat["amount"]) for cat in all_exp_cat_data],
        "total":   float(exp_chart_total),
    }, ensure_ascii=False)
    inc_chart_json = json.dumps({
        "labels":  [cat["name"] for cat in all_inc_cat_data],
        "amounts": [float(cat["amount"]) for cat in all_inc_cat_data],
        "total":   float(inc_chart_total),
    }, ensure_ascii=False)

    return render(request, "dashboard/diagnostico.html", {
        "period":         period,
        "period_label":   period_label,
        "balance_label":  balance_label,
        "period_choices": [("mes", "Mês"), ("ano", "Ano"), ("12m", "12m"), ("24m", "24m"), ("inicio", "Início")],
        "is_mes":         period == "mes",
        "is_ano":         period == "ano",
        "has_data":       has_data,
        "diag_year":      year or now.year,
        "month":         month,
        "year":          year,
        "prev_month":    prev_month,
        "prev_year":     prev_year,
        "next_month":    next_month,
        "next_year":     next_year,
        "income":        income,
        "expense":       expense,
        "month_balance": month_balance,
        "fixed_inc_amt": fixed_inc_amt,
        "var_inc_amt":   var_inc_amt,
        "fixed_exp_amt": fixed_exp_amt,
        "var_exp_amt":   var_exp_amt,
        "exp_cat_data":  exp_cat_data,
        "inc_cat_data":  inc_cat_data,
        "all_exp_cat_data": all_exp_cat_data,
        "all_inc_cat_data": all_inc_cat_data,
        "exp_chart_json":   exp_chart_json,
        "inc_chart_json":   inc_chart_json,
        "fixos_exp_list":         fixos_exp_list,
        "fixos_inc_list":         fixos_inc_list,
        "fixos_exp_total":        fixos_exp_total,
        "fixos_inc_total":        fixos_inc_total,
        "fixos_exp_monthly_total": fixos_exp_monthly_total,
        "fixos_inc_monthly_total": fixos_inc_monthly_total,
        "fixos_exp_approx":       fixos_exp_approx,
        "fixos_inc_approx":       fixos_inc_approx,
        "savings_rate":     savings_rate,
        "commitment_rate":  commitment_rate,
        "cash_balance":     cash_balance,
        "inv_value":        inv_value,
        "patrimonio":       patrimonio,
        "cash_pct_diag":    cash_pct_diag,
        "inv_pct_diag":     inv_pct_diag,
        "goals_diag":       goals_diag,
    })


# ═══════════════════════════════════════════════════════════════════════════
# Investimentos
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def investimentos(request):
    now = _now_br()
    today = now.date()
    current_month = today.replace(day=1)

    # ── Period / date-range ────────────────────────────────────────────────────
    period = request.GET.get("period", "mes")
    if period not in ("mes", "ano", "12m", "24m", "inicio"):
        period = "mes"

    prev_month = prev_year = next_month = next_year = None
    month = year = None

    if period == "mes":
        try:
            year  = int(request.GET.get("ano", now.year))
            month = int(request.GET.get("mes", now.month))
        except (ValueError, TypeError):
            year, month = now.year, now.month
        if not (1 <= month <= 12):
            month = now.month
        date_from = date(year, month, 1)
        date_to   = _add_months(date_from, 1)
        period_label = f"{_MONTHS[month - 1].capitalize()} {year}"
        prev_dt = _add_months(date_from, -1)
        next_dt = date_to
        prev_month, prev_year = prev_dt.month, prev_dt.year
        next_month, next_year = next_dt.month, next_dt.year
        is_mes, is_ano = True, False
    elif period == "ano":
        try:
            year = int(request.GET.get("ano", now.year))
        except (ValueError, TypeError):
            year = now.year
        date_from = date(year, 1, 1)
        date_to   = date(year + 1, 1, 1)
        period_label = str(year)
        prev_year, next_year = year - 1, year + 1
        is_mes, is_ano = False, True
    elif period == "12m":
        date_to   = _add_months(current_month, 1)
        date_from = _add_months(date_to, -12)
        period_label = "Últimos 12 meses"
        is_mes = is_ano = False
    elif period == "24m":
        date_to   = _add_months(current_month, 1)
        date_from = _add_months(date_to, -24)
        period_label = "Últimos 24 meses"
        is_mes = is_ano = False
    else:  # inicio
        date_to = _add_months(current_month, 1)
        _first = InvestmentTransaction.objects.filter(user=request.user).order_by("date").values("date").first()
        date_from = _first["date"].replace(day=1) if _first else current_month
        period_label = "Desde o início"
        is_mes = is_ano = False

    period_choices = [("mes", "Mês"), ("ano", "Ano"), ("12m", "12m"), ("24m", "24m"), ("inicio", "Início")]

    # ── Static queries ─────────────────────────────────────────────────────────
    latest_balance_subq = AccountMonthSnapshot.objects.filter(
        account=OuterRef("pk")
    ).order_by("-month").values("balance")[:1]

    cash_accounts = (
        Account.objects
        .filter(user=request.user, is_active=True, type__in=_CUSTODY_TYPES)
        .annotate(latest_balance=Subquery(latest_balance_subq))
    )
    cash_balance = _projected_cash_balance(request.user, today)

    # Investments queryset — used for modal dropdowns (always current)
    investments = Investment.objects.filter(user=request.user).select_related("account").order_by("type", "name")

    acc_map = {a.pk: a for a in Account.objects.filter(user=request.user, is_active=True)}
    inv_map = {i.pk: i for i in investments}

    # ── Filtered tx_agg: position as of date_to (cumulative) ──────────────────
    tx_agg = (
        InvestmentTransaction.objects
        .filter(user=request.user, date__lt=date_to)
        .values("investment_id", "account_id")
        .annotate(
            buy_total=Sum("amount",    filter=Q(type=InvestmentTransaction.TYPE_BUY)),
            sell_total=Sum("amount",   filter=Q(type=InvestmentTransaction.TYPE_SELL)),
            earn_total=Sum("amount",   filter=Q(type=InvestmentTransaction.TYPE_EARNINGS)),
            qty_bought=Sum("quantity", filter=Q(type=InvestmentTransaction.TYPE_BUY)),
            qty_sold=Sum("quantity",   filter=Q(type=InvestmentTransaction.TYPE_SELL)),
            # Earnings/dividends restricted to the selected period for display
            earn_period=Sum("amount",  filter=Q(type=InvestmentTransaction.TYPE_EARNINGS, date__gte=date_from)),
            div_period=Sum("amount",   filter=Q(type=InvestmentTransaction.TYPE_DIVIDENDS, date__gte=date_from)),
        )
    )

    # ── Current tx totals (unfiltered) — for modal effective-price JSON ────────
    _inv_current_total: dict = {}
    for _row in (
        InvestmentTransaction.objects
        .filter(user=request.user)
        .values("investment_id")
        .annotate(
            buy_total=Sum("amount",  filter=Q(type=InvestmentTransaction.TYPE_BUY)),
            sell_total=Sum("amount", filter=Q(type=InvestmentTransaction.TYPE_SELL)),
            earn_total=Sum("amount", filter=Q(type=InvestmentTransaction.TYPE_EARNINGS)),
        )
    ):
        _cur = (
            (_row["buy_total"] or Decimal("0"))
            - (_row["sell_total"] or Decimal("0"))
            + (_row["earn_total"] or Decimal("0"))
        )
        if _cur > 0:
            _inv_current_total[_row["investment_id"]] = _cur

    # ── Position building from period-filtered tx_agg ──────────────────────────
    inv_by_type: dict = {}
    inv_total = Decimal("0")
    _by_acc: dict = {}

    for row in tx_agg:
        inv_obj = inv_map.get(row["investment_id"])
        acc_obj = acc_map.get(row["account_id"]) if row["account_id"] else None
        if not inv_obj:
            continue
        cost        = (row["buy_total"] or Decimal("0")) - (row["sell_total"] or Decimal("0"))
        earn        = row["earn_total"] or Decimal("0")
        current     = cost + earn
        if current <= 0:
            continue

        # Gains shown to the user = only within the selected period
        earn_period = (row["earn_period"] or Decimal("0")) + (row["div_period"] or Decimal("0"))

        key = row["account_id"] or 0
        if key not in _by_acc:
            _by_acc[key] = {
                "account": acc_obj, "positions": [],
                "total": Decimal("0"), "cost": Decimal("0"), "period_earn": Decimal("0"),
            }

        # Historical quantity: computed from filtered buy/sell boletas
        if inv_obj.tracking_mode == Investment.TRACKING_QP:
            hist_qty = (row["qty_bought"] or Decimal("0")) - (row["qty_sold"] or Decimal("0"))
            qty = hist_qty if hist_qty > 0 else None
        else:
            qty = None
        unit_price = (current / qty).quantize(Decimal("0.01")) if qty and qty > 0 else None

        _by_acc[key]["positions"].append({
            "inv": inv_obj,
            "current_value": current,
            "cost": cost,
            "profit_loss": earn_period,   # period earnings for display
            "display_qty": qty,
            "display_unit_price": unit_price,
        })
        _by_acc[key]["total"]       += current
        _by_acc[key]["cost"]        += cost
        _by_acc[key]["period_earn"] += earn_period

        inv_by_type.setdefault(inv_obj.get_type_display(), Decimal("0"))
        inv_by_type[inv_obj.get_type_display()] += current
        inv_total += current

    for g in _by_acc.values():
        g["profit_loss"] = g["period_earn"]   # group-level: period earnings only
        g["positions"].sort(key=lambda p: (p["inv"].type, p["inv"].name))
    custody_groups = sorted(_by_acc.values(), key=lambda g: g["account"].name if g["account"] else "zzz")

    inv_by_acc: dict = {k: g["total"] for k, g in _by_acc.items() if k}
    cash_accounts_list = []
    for _acc in cash_accounts:
        _snap = _acc.latest_balance or Decimal("0")
        _acc.liquid_balance = _snap - inv_by_acc.get(_acc.pk, Decimal("0"))
        cash_accounts_list.append(_acc)

    goals        = Goal.objects.filter(user=request.user, is_completed=False).order_by("deadline")
    inv_accounts = Account.objects.filter(user=request.user, type__in=_CUSTODY_TYPES, is_active=True)
    boleta_accounts = Account.objects.filter(
        user=request.user, is_active=True
    ).exclude(type=Account.TYPE_CREDIT)

    # ── Boletas filtered to selected period ────────────────────────────────────
    recent_boletas = (
        InvestmentTransaction.objects
        .filter(user=request.user, date__gte=date_from, date__lt=date_to)
        .select_related("investment", "account")
        .order_by("date", "created_at")
    )

    inv_modes_json = json.dumps({str(i.pk): i.tracking_mode for i in investments})

    def _effective_price(inv_obj):
        if inv_obj.tracking_mode == Investment.TRACKING_QP and inv_obj.quantity > 0:
            total_val = _inv_current_total.get(inv_obj.pk, Decimal("0"))
            if total_val > 0:
                return float((total_val / inv_obj.quantity).quantize(Decimal("0.000001")))
        return float(inv_obj.current_price)

    return render(request, "dashboard/investimentos.html", {
        "cash_accounts":      cash_accounts_list,
        "cash_balance":       cash_balance,
        "inv_by_type":        inv_by_type,
        "inv_total":          inv_total,
        "disponivel":         cash_balance,
        "patrimonio":         cash_balance + inv_total,
        "goals":              goals,
        "investments":        investments,
        "custody_groups":     custody_groups,
        "inv_accounts":       inv_accounts,
        "investment_types":   Investment.TYPE_CHOICES,
        "boleta_accounts":    boleta_accounts,
        "recent_boletas":     recent_boletas,
        "inv_modes_json":     inv_modes_json,
        "inv_prices_json":    json.dumps({str(i.pk): _effective_price(i) for i in investments}),
        "inv_qty_json":       json.dumps({str(i.pk): float(i.quantity) for i in investments}),
        # Period
        "period":        period,
        "period_label":  period_label,
        "period_choices": period_choices,
        "is_mes":        is_mes,
        "is_ano":        is_ano,
        "month":         month,
        "year":          year,
        "prev_month":    prev_month,
        "prev_year":     prev_year,
        "next_month":    next_month,
        "next_year":     next_year,
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

        if description and amount != 0 and account_pk:
            try:
                acc = Account.objects.get(pk=account_pk, user=request.user)
                category = None
                if category_pk:
                    cat = Category.objects.filter(pk=category_pk).first()
                    expected = "income" if tx_type == Transaction.TYPE_CREDIT else "expense"
                    if cat and cat.type == expected:
                        category = cat
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
                ach.check_achievements(request.user, request)
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
        _period = request.POST.get("period", "mes")
        if _period not in ("mes", "ano", "12m", "24m", "inicio"):
            _period = "mes"
        _tab = "entradas" if tx_type == Transaction.TYPE_CREDIT else "saidas"
        if _period == "mes":
            return redirect(f"/dashboard/lancamentos/?period=mes&ano={tx_date.year}&mes={tx_date.month}&tab={_tab}")
        return redirect(f"/dashboard/lancamentos/?period={_period}&tab={_tab}")

    # ── GET ──
    period = request.GET.get("period", "mes")
    if period not in ("mes", "ano", "12m", "24m", "inicio"):
        period = "mes"

    # ── Period boundaries ─────────────────────────────────────────────────────
    prev_year = next_year = prev_month = next_month = None
    year = month = None

    if period == "mes":
        try:
            year  = int(request.GET.get("ano", now.year))
            month = int(request.GET.get("mes", now.month))
            if not (1 <= month <= 12): raise ValueError
        except (ValueError, TypeError):
            year, month = now.year, now.month
        date_from = date(year, month, 1)
        date_to   = _add_months(date_from, 1)
        period_label  = f"{_MONTHS[month - 1].capitalize()} {year}"
        _prev = _add_months(date_from, -1)
        _next = _add_months(date_from,  1)
        prev_month, prev_year = _prev.month, _prev.year
        next_month, next_year = _next.month, _next.year

    elif period == "ano":
        try:
            year = int(request.GET.get("ano", now.year))
        except (ValueError, TypeError):
            year = now.year
        date_from = date(year, 1, 1)
        if year < now.year:
            date_to = date(year + 1, 1, 1)
        else:
            date_to = _add_months(date(now.year, now.month, 1), 1)
        period_label  = str(year)
        prev_year, next_year = year - 1, year + 1

    elif period == "12m":
        date_to       = _add_months(date(now.year, now.month, 1), 1)
        date_from     = _add_months(date_to, -12)
        period_label  = "Últimos 12 meses"

    elif period == "24m":
        date_to       = _add_months(date(now.year, now.month, 1), 1)
        date_from     = _add_months(date_to, -24)
        period_label  = "Últimos 24 meses"

    else:  # inicio
        _first = (
            Transaction.objects.filter(account__user=request.user)
            .order_by("date").values("date").first()
        )
        if _first:
            _fd = _first["date"]
            if not isinstance(_fd, date): _fd = _fd.date()
            date_from = _fd.replace(day=1)
        else:
            date_from = date(now.year, now.month, 1)
        date_to      = _add_months(date(now.year, now.month, 1), 1)
        period_label = "Desde o início"

    is_mes = (period == "mes")
    is_ano = (period == "ano")
    month_name = _MONTHS[month - 1] if is_mes else period_label

    tab = request.GET.get("tab", "todos")

    txs = Transaction.objects.filter(
        account__user=request.user,
        date__gte=date_from,
        date__lt=date_to,
    ).select_related("category", "account", "goal").order_by("-date", "-created_at")

    if tab == "entradas":
        txs = txs.filter(type=Transaction.TYPE_CREDIT)
    elif tab == "saidas":
        txs = txs.filter(type=Transaction.TYPE_DEBIT)

    var_inc_amt = Transaction.objects.filter(
        account__user=request.user,
        date__gte=date_from, date__lt=date_to,
        type=Transaction.TYPE_CREDIT, is_transfer=False, is_investment=False,
    ).aggregate(t=Sum("amount"))["t"] or Decimal("0")
    var_exp_amt = Transaction.objects.filter(
        account__user=request.user,
        date__gte=date_from, date__lt=date_to,
        type=Transaction.TYPE_DEBIT, is_transfer=False, is_investment=False,
    ).aggregate(t=Sum("amount"))["t"] or Decimal("0")

    # Build the list of months covered by the selected period so we can sum fixos correctly.
    _pm = date_from
    _period_months = []
    while _pm < date_to:
        _period_months.append(_pm)
        _pm = _add_months(_pm, 1)

    # Fixos active in any part of the selected period — used for summary card totals.
    # Values-only query (no select_related needed) to sum amounts across all period months.
    _fixos_period_amounts = list(
        RecurringTransaction.objects.filter(
            user=request.user,
            is_active=True,
            start_date__lt=date_to,
        ).filter(Q(end_date__isnull=True) | Q(end_date__gte=date_from))
        .only("type", "amount", "frequency", "start_date", "end_date", "day_of_week")
    )
    fixos_inc_period = sum(
        _amount_for_month(r, m)
        for r in _fixos_period_amounts
        if r.type == RecurringTransaction.TYPE_INCOME
        for m in _period_months
    )
    fixos_exp_period = sum(
        _amount_for_month(r, m)
        for r in _fixos_period_amounts
        if r.type == RecurringTransaction.TYPE_EXPENSE
        for m in _period_months
    )

    income = var_inc_amt + fixos_inc_period
    expense = var_exp_amt + fixos_exp_period

    if is_mes:
        month_start = date_from
        next_month_start = date_to
        recurring = RecurringTransaction.objects.filter(
            user=request.user,
            is_active=True,
            start_date__lt=next_month_start,
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=month_start)
        ).select_related("account", "category", "goal").order_by("type", "name")
        rec_income = sum(_amount_for_month(r, month_start) for r in recurring if r.type == RecurringTransaction.TYPE_INCOME)
        rec_expense = sum(_amount_for_month(r, month_start) for r in recurring if r.type == RecurringTransaction.TYPE_EXPENSE)
    else:
        cur_mo = date(now.year, now.month, 1)
        cur_mo_end = _add_months(cur_mo, 1)
        recurring = RecurringTransaction.objects.filter(
            user=request.user,
            is_active=True,
            start_date__lt=cur_mo_end,
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=cur_mo)
        ).select_related("account", "category", "goal").order_by("type", "name")
        rec_income = sum(_amount_for_month(r, cur_mo) for r in recurring if r.type == RecurringTransaction.TYPE_INCOME)
        rec_expense = sum(_amount_for_month(r, cur_mo) for r in recurring if r.type == RecurringTransaction.TYPE_EXPENSE)

    accounts = Account.objects.filter(user=request.user, is_active=True)
    categories = Category.objects.filter(
        Q(user=request.user) | Q(user__isnull=True)
    ).order_by("type", "name")
    goals = Goal.objects.filter(user=request.user, is_completed=False).order_by("name")
    investments = Investment.objects.filter(user=request.user).order_by("name")
    boleta_accounts = accounts.exclude(type=Account.TYPE_CREDIT)

    period_choices = [("mes", "Mês"), ("ano", "Ano"), ("12m", "12m"), ("24m", "24m"), ("inicio", "Início")]
    tab_defs = [("todos", "Todos"), ("entradas", "Entradas"), ("saidas", "Saídas"), ("fixos", "Fixos"), ("categorias", "Categorias")]

    return render(request, "dashboard/lancamentos.html", {
        "txs": txs,
        "tab": tab,
        "tab_defs": tab_defs,
        "period": period,
        "period_label": period_label,
        "period_choices": period_choices,
        "is_mes": is_mes,
        "is_ano": is_ano,
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
        "investments": investments,
        "boleta_accounts": boleta_accounts,
        "today": now.date().isoformat(),
        "available_icons": AVAILABLE_ICONS,
    })


@login_required
@require_POST
def lancamento_editar(request, pk):
    tx = get_object_or_404(Transaction, pk=pk, account__user=request.user)

    if tx.is_investment:
        try:
            boleta = tx.inv_boleta
        except InvestmentTransaction.DoesNotExist:
            return redirect("lancamentos")

        new_amount = _d(request.POST.get("amount"), tx.amount)
        new_date   = _dt(request.POST.get("date")) or tx.date
        new_desc   = request.POST.get("description", "").strip() or tx.description

        if new_amount != 0:
            acc = tx.account

            # Reverse old balance then apply new
            if tx.type == Transaction.TYPE_CREDIT:
                acc.balance = acc.balance - tx.amount + new_amount
            else:
                acc.balance = acc.balance + tx.amount - new_amount

            tx.amount      = new_amount
            tx.date        = new_date
            tx.description = new_desc
            tx.save()
            acc.save(update_fields=["balance"])

            # Sync boleta fields
            boleta.amount = new_amount
            boleta.date   = new_date
            if boleta.quantity and boleta.quantity > 0:
                boleta.unit_price = (new_amount / boleta.quantity).quantize(Decimal("0.01"))
            boleta.save(update_fields=["amount", "date", "unit_price"])

            # Recalculate Investment.current_price from full transaction history
            inv = boleta.investment
            agg = InvestmentTransaction.objects.filter(
                user=request.user, investment=inv
            ).aggregate(
                buy_total  = Sum("amount", filter=Q(type=InvestmentTransaction.TYPE_BUY)),
                sell_total = Sum("amount", filter=Q(type=InvestmentTransaction.TYPE_SELL)),
                earn_total = Sum("amount", filter=Q(type=InvestmentTransaction.TYPE_EARNINGS)),
            )
            total_value = (
                (agg["buy_total"]  or Decimal("0"))
                - (agg["sell_total"] or Decimal("0"))
                + (agg["earn_total"] or Decimal("0"))
            )
            if inv.quantity > 0:
                inv.current_price = (total_value / inv.quantity).quantize(Decimal("0.000001"))
            else:
                inv.current_price = total_value
            inv.save(update_fields=["current_price"])

        return redirect("lancamentos")

    old_amount = tx.amount
    old_type = tx.type
    old_goal_id = tx.goal_id

    description = request.POST.get("description", "").strip()
    amount = _d(request.POST.get("amount"), tx.amount)
    tx_date = _dt(request.POST.get("date")) or tx.date
    category_pk = _iv(request.POST.get("category"))
    goal_pk = _iv(request.POST.get("goal"))
    new_account_pk = _iv(request.POST.get("account"))

    if description:
        old_acc = tx.account

        # Determine target account (may have changed)
        if new_account_pk and new_account_pk != old_acc.pk:
            try:
                new_acc = Account.objects.get(pk=new_account_pk, user=request.user)
            except Account.DoesNotExist:
                new_acc = old_acc
        else:
            new_acc = old_acc

        # Reverse the old transaction from the old account
        if old_type == Transaction.TYPE_CREDIT:
            old_acc.balance -= old_amount
        else:
            old_acc.balance += old_amount

        tx.description = description
        tx.amount = amount
        tx.date = tx_date
        tx.account = new_acc
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

        # Apply new amount to target account (may differ from old_acc)
        if tx.type == Transaction.TYPE_CREDIT:
            new_acc.balance += amount
        else:
            new_acc.balance -= amount

        if new_acc.pk == old_acc.pk:
            old_acc.save(update_fields=["balance"])
        else:
            old_acc.save(update_fields=["balance"])
            new_acc.save(update_fields=["balance"])

        ach.check_achievements(request.user, request)

    return redirect("lancamentos")


@login_required
@require_POST
def lancamento_excluir(request, pk):
    tx = get_object_or_404(Transaction, pk=pk, account__user=request.user)
    # Investment transactions are owned by the investment module. Deleting via
    # the boleta (InvestmentTransaction.delete) triggers the signal that cleans
    # up this Transaction. Deleting directly here would orphan the boleta.
    if tx.is_investment:
        try:
            tx.inv_boleta.delete()  # signal handles Transaction removal
        except Exception:
            tx.delete()
        return redirect("lancamentos")
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
    ach.check_achievements(request.user, request)
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

    if request.POST.get("redirect_to") == "projecao":
        return redirect("projecao")
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
    if not is_weekly and day_of_month is None:
        day_of_month = start_date.day
    account_pk = _iv(request.POST.get("account"))
    category_pk = _iv(request.POST.get("category"))
    goal_pk = _iv(request.POST.get("goal"))
    notes = request.POST.get("notes", "").strip()

    if name and amount > 0 and account_pk:
        try:
            account = Account.objects.get(pk=account_pk, user=request.user)
        except Account.DoesNotExist:
            return redirect("/dashboard/lancamentos/?tab=fixos")
        category = None
        if category_pk:
            cat = Category.objects.filter(pk=category_pk).first()
            expected = "income" if fx_type == RecurringTransaction.TYPE_INCOME else "expense"
            if cat and cat.type == expected:
                category = cat
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
        ach.check_achievements(request.user, request)
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
            if rt.day_of_month is None:
                rt.day_of_month = rt.start_date.day
            rt.day_of_week = None
        category_pk = _iv(request.POST.get("category"))
        if category_pk:
            cat = Category.objects.filter(pk=category_pk).first()
            expected = "income" if rt.type == RecurringTransaction.TYPE_INCOME else "expense"
            rt.category = cat if (cat and cat.type == expected) else None
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
        ach.check_achievements(request.user, request)
    return redirect("/dashboard/lancamentos/?tab=fixos")


@login_required
@require_POST
def fixo_excluir(request, pk):
    rt = get_object_or_404(RecurringTransaction, pk=pk, user=request.user)
    rt.delete()
    ach.check_achievements(request.user, request)
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


def _own_category(user, pk):
    """Retorna a categoria se pertencer ao usuário ou for uma padrão do sistema (user=None)."""
    cat = get_object_or_404(Category, pk=pk)
    if cat.user is not None and cat.user != user:
        from django.http import Http404
        raise Http404
    return cat


@login_required
@require_POST
def categoria_editar(request, pk):
    cat = _own_category(request.user, pk)
    name = request.POST.get("name", "").strip()
    if name:
        cat.name = name
        cat.save(update_fields=["name"])
    return redirect("/dashboard/lancamentos/?tab=categorias")


@login_required
@require_POST
def categoria_excluir(request, pk):
    cat = _own_category(request.user, pk)
    has_tx  = Transaction.objects.filter(category=cat).exists()
    has_rec = RecurringTransaction.objects.filter(category=cat).exists()
    if has_tx or has_rec:
        messages.error(
            request,
            f"A categoria \"{cat.name}\" possui lançamentos vinculados e não pode ser excluída.",
        )
    else:
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
            if Account.objects.filter(user=request.user, name__iexact=name, is_active=True).exists():
                messages.warning(
                    request,
                    f"Já existe uma conta com o nome \"{name}\". Escolha um nome diferente.",
                )
            else:
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
                ach.check_achievements(request.user, request)
        return redirect("contas")

    all_accounts = list(
        Account.objects.filter(user=request.user, is_active=True)
        .order_by("type", "name")
    )

    cash_accounts       = [a for a in all_accounts if a.type in (Account.TYPE_CHECKING, Account.TYPE_SAVINGS, Account.TYPE_WALLET)]
    credit_accounts     = [a for a in all_accounts if a.type == Account.TYPE_CREDIT]
    investment_accounts = [a for a in all_accounts if a.type == Account.TYPE_INVESTMENT]

    # ── Matrix: months × accounts ─────────────────────────────────────────────
    all_snaps = AccountMonthSnapshot.objects.filter(
        account__user=request.user, account__is_active=True
    ).select_related("account")

    snap_months = {s.month.replace(day=1) for s in all_snaps}

    # Colunas começam 6 meses antes do primeiro saldo registrado.
    # Se ainda não há saldo informado, 6 meses antes de hoje.
    today = _now_br().date().replace(day=1)
    start = _add_months(min(snap_months), -6) if snap_months else _add_months(today, -6)
    end   = max(max(snap_months), today) if snap_months else today

    months = []
    m = start
    while m <= end:
        months.append(m)
        m = _add_months(m, 1)

    # {account_id: {month_str: {balance, snap_id}}}
    matrix: dict = {a.pk: {} for a in all_accounts}
    for s in all_snaps:
        mo_str = s.month.strftime("%Y-%m")
        matrix.setdefault(s.account_id, {})[mo_str] = {
            "b":  float(s.balance),
            "id": s.pk,
        }

    # Credit accounts carry no patrimonial value — show 0 for every month
    _credit_ids = {a.pk for a in credit_accounts}
    for _cid in _credit_ids:
        for _mo_str in matrix.get(_cid, {}):
            matrix[_cid][_mo_str]["b"] = 0.0

    matrix_json = json.dumps(matrix, ensure_ascii=False)
    months_list = [(m.strftime("%Y-%m"), f"{_MONTHS[m.month - 1][:3].capitalize()}/{m.year}") for m in months]

    total_balance = sum(
        (Decimal(str(matrix[a.pk][months[-1].strftime("%Y-%m")]["b"]))
         for a in all_accounts
         if a.include_in_total and a.type != Account.TYPE_CREDIT
         and months and months[-1].strftime("%Y-%m") in matrix.get(a.pk, {})),
        Decimal("0"),
    ) if months else Decimal("0")

    return render(request, "dashboard/contas.html", {
        "cash_accounts":        cash_accounts,
        "credit_accounts":      credit_accounts,
        "investment_accounts":  investment_accounts,
        "all_accounts":         all_accounts,
        "has_accounts":         bool(all_accounts),
        "total_balance":        total_balance,
        "account_types":        Account.TYPE_CHOICES,
        "months_list":          months_list,
        "matrix_json":          matrix_json,
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
                    f"Não é possível registrar o saldo de {_MONTHS[mo.month - 1].capitalize()}/{mo.year} sem antes preencher os meses "
                    f"intermediários. O último mês registrado para {acc.name} é {_MONTHS[latest.month.month - 1].capitalize()}/{latest.month.year}.",
                )
                return redirect("contas")
            AccountMonthSnapshot.objects.update_or_create(
                account=acc,
                month=mo,
                defaults={"balance": balance, "notes": notes},
            )
            ach.check_achievements(request.user, request)
        except (Account.DoesNotExist, ValueError):
            pass
    return redirect("contas")


@login_required
@require_POST
def snapshot_excluir(request, pk):
    snap = get_object_or_404(AccountMonthSnapshot, pk=pk, account__user=request.user)
    snap.delete()
    ach.check_achievements(request.user, request)
    return redirect("contas")


@login_required
@require_POST
def snapshot_ajax(request):
    """Inline-edit endpoint para a view matricial de contas. Retorna JSON."""
    from django.http import JsonResponse
    account_pk = _iv(request.POST.get("account"))
    month_str  = request.POST.get("month", "").strip()
    balance_str = request.POST.get("balance", "").strip().replace(",", ".")

    if not account_pk or not month_str:
        return JsonResponse({"error": "missing"}, status=400)

    try:
        year_s, mo_s = month_str.split("-")
        mo  = date(int(year_s), int(mo_s), 1)
        acc = Account.objects.get(pk=account_pk, user=request.user)
    except (ValueError, Account.DoesNotExist):
        return JsonResponse({"error": "invalid"}, status=400)

    if not balance_str:
        # Célula apagada — remove o snapshot se existir
        deleted = AccountMonthSnapshot.objects.filter(account=acc, month=mo).delete()[0]
        if deleted:
            ach.check_achievements(request.user, request)
        return JsonResponse({"deleted": True})

    try:
        balance = Decimal(balance_str)
    except Exception:
        return JsonResponse({"error": "invalid_balance"}, status=400)

    snap, _ = AccountMonthSnapshot.objects.update_or_create(
        account=acc, month=mo, defaults={"balance": balance}
    )
    ach.check_achievements(request.user, request)
    return JsonResponse({"ok": True, "snap_id": snap.pk, "balance": float(balance)})


@login_required
@require_POST
def conta_editar(request, pk):
    acc = _own_account(request.user, pk)
    name = request.POST.get("name", "").strip()
    if name:
        duplicate = (
            Account.objects
            .filter(user=request.user, name__iexact=name, is_active=True)
            .exclude(pk=acc.pk)
            .exists()
        )
        if duplicate:
            messages.warning(
                request,
                f"Já existe outra conta com o nome \"{name}\". A edição não foi salva.",
            )
        else:
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
                    ach.check_achievements(request.user, request)
                g.save()
            return redirect("metas")

        name = request.POST.get("name", "").strip()
        if name:
            Goal.objects.create(
                user=request.user,
                name=name,
                description=request.POST.get("description", "").strip(),
                target_amount=_d(request.POST.get("target_amount")),
                current_amount=Decimal("0"),
                deadline=_dt(request.POST.get("deadline")),
                color=request.POST.get("color", "#00C97A"),
            )
            ach.check_achievements(request.user, request)
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

    # Build per-goal drill data (transactions grouped by account)
    all_goal_txs = (
        Transaction.objects
        .filter(goal__in=active_goals)
        .select_related("account", "category", "goal")
        .order_by("account__name", "date")
    )
    txs_by_goal = defaultdict(list)
    for tx in all_goal_txs:
        txs_by_goal[tx.goal_id].append(tx)

    all_goal_rec = (
        RecurringTransaction.objects
        .filter(goal__in=active_goals, is_active=True)
        .select_related("account", "category", "goal")
        .order_by("account__name", "name")
    )
    rec_by_goal = defaultdict(list)
    for r in all_goal_rec:
        rec_by_goal[r.goal_id].append(r)

    for g in active_goals:
        # Horizon: goal deadline or 12 months ahead
        cutoff = g.deadline if g.deadline else _add_months(today, 12)

        by_acc: dict = defaultdict(lambda: {"obj": None, "rows": []})

        # Regular transactions (past and future pending)
        for tx in txs_by_goal[g.pk]:
            by_acc[tx.account_id]["obj"] = tx.account
            by_acc[tx.account_id]["rows"].append({
                "date_raw": tx.date,
                "date": tx.date.strftime("%d/%m/%Y"),
                "desc": tx.description,
                "amount": float(tx.amount),
                "type": tx.type,
                "status": Transaction.STATUS_PENDING if tx.date > today else tx.status,
                "cat": tx.category.name if tx.category else None,
                "recurring": False,
                "freq": None,
            })

        # Recurring transactions — expand into individual occurrences
        for r in rec_by_goal[g.pk]:
            if not r.account:
                continue
            acc_id = r.account_id
            by_acc[acc_id]["obj"] = r.account
            tx_type = "credit" if r.type == RecurringTransaction.TYPE_INCOME else "debit"
            freq_label = r.get_frequency_display()
            for occ_date, occ_amt in _expand_recurring(r, cutoff):
                status = Transaction.STATUS_COMPLETED if occ_date <= today else Transaction.STATUS_PENDING
                by_acc[acc_id]["rows"].append({
                    "date_raw": occ_date,
                    "date": occ_date.strftime("%d/%m/%Y"),
                    "desc": r.name,
                    "amount": float(occ_amt),
                    "type": tx_type,
                    "status": status,
                    "cat": r.category.name if r.category else None,
                    "recurring": True,
                    "freq": freq_label,
                })

        acc_list = []
        for _, bucket in by_acc.items():
            acc = bucket["obj"]
            if acc is None:
                continue
            rows = sorted(bucket["rows"], key=lambda x: x["date_raw"])
            total_credit = sum(r["amount"] for r in rows if r["type"] == "credit")
            total_debit  = sum(r["amount"] for r in rows if r["type"] == "debit")
            # Remove raw date before serialising (not JSON-serialisable)
            for row in rows:
                del row["date_raw"]
            acc_list.append({
                "name": acc.name,
                "color": acc.color,
                "total_credit": total_credit,
                "total_debit": total_debit,
                "txs": rows,
            })
        g.drill_json = json.dumps(acc_list, ensure_ascii=False)

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
        g.deadline = _dt(request.POST.get("deadline")) or g.deadline
        g.color = request.POST.get("color", g.color)
        if g.current_amount >= g.target_amount and not g.is_completed:
            g.is_completed = True
            ach.check_achievements(request.user, request)
        g.save()
    return redirect("metas")


@login_required
@require_POST
def meta_excluir(request, pk):
    get_object_or_404(Goal, pk=pk, user=request.user).delete()
    ach.check_achievements(request.user, request)
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
    qty = _d(request.POST.get("quantity"), Decimal("0"))
    unit_price = _d(request.POST.get("unit_price"), Decimal("0"))
    financeiro = _d(request.POST.get("financeiro"), Decimal("0"))
    purchase_date = _dt(request.POST.get("purchase_date")) or _now_br().date()
    account_pk = _iv(request.POST.get("account"))

    # Derive consistent (quantity, unit_price) from whichever combination was filled.
    if qty > 0 and unit_price > 0:
        financeiro = qty * unit_price
        inv_qty = qty
        inv_price = unit_price
    elif qty > 0 and financeiro > 0:
        inv_qty = qty
        inv_price = financeiro / qty
    elif financeiro > 0:
        inv_qty = Decimal("1")
        inv_price = financeiro
    else:
        return redirect("investimentos")

    if not name:
        return redirect("investimentos")

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
        quantity=inv_qty,
        purchase_price=inv_price,
        current_price=inv_price,
        purchase_date=purchase_date,
    )
    ach.check_achievements(request.user, request)
    return redirect("investimentos")


@login_required
@require_POST
def investimento_excluir(request, pk):
    get_object_or_404(Investment, pk=pk, user=request.user).delete()
    ach.check_achievements(request.user, request)
    return redirect("investimentos")


@login_required
@require_POST
def investimento_editar(request, pk):
    inv = get_object_or_404(Investment, pk=pk, user=request.user)
    name = request.POST.get("name", "").strip()
    if name:
        inv.name = name
    inv.ticker = request.POST.get("ticker", inv.ticker or "").strip().upper()

    qty = _d(request.POST.get("quantity"), Decimal("0"))
    financeiro = _d(request.POST.get("financeiro"), Decimal("0"))

    if qty > 0 and financeiro > 0:
        inv.quantity = qty
        inv.current_price = financeiro / qty
    elif financeiro > 0:
        inv.quantity = Decimal("1")
        inv.current_price = financeiro
    elif qty > 0:
        inv.quantity = qty

    inv.save()
    return redirect("investimentos")


# ═══════════════════════════════════════════════════════════════════════════
# Investment Boleta (BUY / SELL) and Rendimento (EARNINGS)
# ═══════════════════════════════════════════════════════════════════════════

@login_required
@require_POST
def investimento_boleta(request):
    """Unified boleta: BUY, SELL, or EARNINGS. Also handles inline new-asset creation for BUY."""
    _redirect_to = request.POST.get("redirect_to", "investimentos")
    def _success_redirect():
        if _redirect_to == "projecao":
            return redirect("projecao")
        return redirect("investimentos")

    boleta_type = request.POST.get("boleta_type", InvestmentTransaction.TYPE_BUY)
    if boleta_type not in (
        InvestmentTransaction.TYPE_BUY,
        InvestmentTransaction.TYPE_SELL,
        InvestmentTransaction.TYPE_EARNINGS,
        InvestmentTransaction.TYPE_DIVIDENDS,
    ):
        return redirect("investimentos")

    tx_date = _dt(request.POST.get("date")) or _now_br().date()
    notes = request.POST.get("notes", "").strip()

    # Resolve account (optional for earnings, required for buy/sell)
    account_pk = _iv(request.POST.get("account"))
    account = None
    if account_pk:
        try:
            acc = Account.objects.get(pk=account_pk, user=request.user)
            if acc.type != Account.TYPE_CREDIT:
                account = acc
        except Account.DoesNotExist:
            pass

    # Resolve or create investment
    inv_raw = request.POST.get("investment", "").strip()
    if inv_raw == "new":
        if boleta_type != InvestmentTransaction.TYPE_BUY:
            return redirect("investimentos")
        name = request.POST.get("new_name", "").strip()
        if not name:
            return redirect("investimentos")
        inv_type = request.POST.get("new_type", Investment.TYPE_OTHER)
        ticker = request.POST.get("new_ticker", "").strip().upper()
        new_mode = request.POST.get("new_mode", Investment.TRACKING_FIN)
        if new_mode not in (Investment.TRACKING_FIN, Investment.TRACKING_QP):
            new_mode = Investment.TRACKING_FIN
        inv = Investment.objects.create(
            user=request.user,
            account=account,
            name=name,
            ticker=ticker or "",
            type=inv_type,
            tracking_mode=new_mode,
            quantity=Decimal("0"),
            purchase_price=Decimal("0"),
            current_price=Decimal("0"),
            purchase_date=tx_date,
        )
        ach.check_achievements(request.user, request)
    else:
        inv_pk = _iv(inv_raw)
        if not inv_pk:
            return redirect("investimentos")
        try:
            inv = Investment.objects.get(pk=inv_pk, user=request.user)
        except Investment.DoesNotExist:
            return redirect("investimentos")

    # ── EARNINGS ──────────────────────────────────────────────────────────────
    if boleta_type == InvestmentTransaction.TYPE_EARNINGS:
        if inv.tracking_mode == Investment.TRACKING_QP:
            # qp mode: user supplies new_price; gain = qty × (new_price − old_price)
            try:
                new_price = Decimal(str(request.POST.get("new_price", "0")).replace(",", "."))
            except (InvalidOperation, TypeError):
                return redirect("investimentos")
            # Derive old_price from transaction history (same formula the modal uses),
            # not from inv.current_price which may lag after multiple buys.
            if inv.quantity > 0:
                _agg = InvestmentTransaction.objects.filter(
                    user=request.user, investment=inv
                ).aggregate(
                    buy_total=Sum("amount", filter=Q(type=InvestmentTransaction.TYPE_BUY)),
                    sell_total=Sum("amount", filter=Q(type=InvestmentTransaction.TYPE_SELL)),
                    earn_total=Sum("amount", filter=Q(type=InvestmentTransaction.TYPE_EARNINGS)),
                )
                _current_val = (
                    (_agg["buy_total"] or Decimal("0"))
                    - (_agg["sell_total"] or Decimal("0"))
                    + (_agg["earn_total"] or Decimal("0"))
                )
                old_price = _current_val / inv.quantity
            else:
                old_price = inv.current_price
            amount = inv.quantity * (new_price - old_price)
            inv.current_price = new_price
            inv.save(update_fields=["current_price"])
        else:
            # fin mode: direct financial amount
            try:
                amount = Decimal(str(request.POST.get("amount", "0")).replace(",", "."))
            except (InvalidOperation, TypeError):
                return redirect("investimentos")
            if inv.quantity > 0:
                inv.current_price = inv.current_price + amount / inv.quantity
                inv.save(update_fields=["current_price"])

        earn_tx = None
        if account:
            earn_tx = Transaction.objects.create(
                account=account,
                amount=abs(amount),
                type=Transaction.TYPE_CREDIT if amount >= 0 else Transaction.TYPE_DEBIT,
                date=tx_date,
                description=f"Rendimento: {inv.ticker or inv.name}",
                notes=notes,
                status=Transaction.STATUS_COMPLETED,
                is_investment=True,
            )
        InvestmentTransaction.objects.create(
            user=request.user,
            investment=inv,
            account=account,
            type=InvestmentTransaction.TYPE_EARNINGS,
            date=tx_date,
            amount=amount,
            cash_transaction=earn_tx,
            notes=notes,
        )
        return _success_redirect()

    # ── DIVIDENDS ─────────────────────────────────────────────────────────────
    if boleta_type == InvestmentTransaction.TYPE_DIVIDENDS:
        try:
            amount = Decimal(str(request.POST.get("amount", "0")).replace(",", "."))
        except (InvalidOperation, TypeError):
            return redirect("investimentos")
        if amount <= 0:
            return redirect("investimentos")
        div_tx = None
        if account:
            div_tx = Transaction.objects.create(
                account=account,
                amount=amount,
                type=Transaction.TYPE_CREDIT,
                date=tx_date,
                description=f"Dividendo: {inv.ticker or inv.name}",
                notes=notes,
                status=Transaction.STATUS_COMPLETED,
                is_investment=True,
            )
        InvestmentTransaction.objects.create(
            user=request.user,
            investment=inv,
            account=account,
            type=InvestmentTransaction.TYPE_DIVIDENDS,
            date=tx_date,
            amount=amount,
            cash_transaction=div_tx,
            notes=notes,
        )
        return _success_redirect()

    # ── BUY / SELL ────────────────────────────────────────────────────────────
    if not account:
        return redirect("investimentos")

    is_qp = inv.tracking_mode == Investment.TRACKING_QP
    qty_raw = _d(request.POST.get("quantity"), Decimal("0"))
    unit_price_raw = _d(request.POST.get("unit_price"), Decimal("0"))
    financeiro = _d(request.POST.get("financeiro"), Decimal("0"))

    if is_qp:
        if qty_raw > 0 and unit_price_raw > 0:
            total = qty_raw * unit_price_raw
            qty = qty_raw
            up = unit_price_raw
        else:
            return redirect("investimentos")
    else:
        if financeiro > 0:
            total = financeiro
            qty = None
            up = None
        else:
            return redirect("investimentos")

    if boleta_type == InvestmentTransaction.TYPE_BUY:
        tx_type = Transaction.TYPE_DEBIT
        description = f"Compra: {inv.ticker or inv.name}"
        if is_qp:
            old_qty = inv.quantity
            new_qty = old_qty + qty
            if new_qty > 0:
                inv.purchase_price = (old_qty * inv.purchase_price + qty * up) / new_qty
            inv.quantity = new_qty
            inv.current_price = up
        else:
            if inv.quantity <= 0:
                inv.quantity = Decimal("1")
            inv.purchase_price += total
            inv.current_price += total
        inv.account = account
        inv.save()
    else:
        tx_type = Transaction.TYPE_CREDIT
        description = f"Venda: {inv.ticker or inv.name}"
        if is_qp:
            inv.quantity = max(Decimal("0"), inv.quantity - qty)
            inv.save(update_fields=["quantity"])
        else:
            inv.purchase_price = max(Decimal("0"), inv.purchase_price - total)
            inv.current_price = max(Decimal("0"), inv.current_price - total)
            inv.save()

    cash_tx = Transaction.objects.create(
        account=account,
        amount=total,
        type=tx_type,
        date=tx_date,
        description=description,
        notes=notes,
        status=Transaction.STATUS_COMPLETED,
        is_investment=True,
    )
    InvestmentTransaction.objects.create(
        user=request.user,
        investment=inv,
        account=account,
        type=boleta_type,
        date=tx_date,
        quantity=qty,
        unit_price=up,
        amount=total,
        cash_transaction=cash_tx,
        notes=notes,
    )
    return _success_redirect()


@login_required
@require_POST
def investimento_boleta_editar(request, pk):
    """Edit an existing InvestmentTransaction (boleta)."""
    boleta = get_object_or_404(InvestmentTransaction, pk=pk, user=request.user)
    inv = boleta.investment

    tx_date = _dt(request.POST.get("date")) or boleta.date
    notes = request.POST.get("notes", "").strip()

    account_pk = _iv(request.POST.get("account"))
    account = None
    if account_pk:
        try:
            acc = Account.objects.get(pk=account_pk, user=request.user)
            if acc.type != Account.TYPE_CREDIT:
                account = acc
        except Account.DoesNotExist:
            pass

    if boleta.type in (InvestmentTransaction.TYPE_BUY, InvestmentTransaction.TYPE_SELL):
        is_qp = inv.tracking_mode == Investment.TRACKING_QP
        if is_qp:
            qty = _d(request.POST.get("quantity"), Decimal("0"))
            up  = _d(request.POST.get("unit_price"), Decimal("0"))
            if qty <= 0 or up <= 0:
                return redirect("investimentos")
            total = qty * up
        else:
            total = _d(request.POST.get("financeiro"), Decimal("0"))
            if total <= 0:
                return redirect("investimentos")
            qty = None
            up  = None

        boleta.date       = tx_date
        boleta.account    = account
        boleta.quantity   = qty
        boleta.unit_price = up
        boleta.amount     = total
        boleta.notes      = notes
        boleta.save()

        if boleta.cash_transaction:
            ct = boleta.cash_transaction
            ct.date    = tx_date
            ct.amount  = total
            ct.account = account
            ct.notes   = notes
            ct.save()

        # Recompute inv.quantity from full buy/sell history to keep Investment in sync
        if inv.tracking_mode == Investment.TRACKING_QP:
            agg = InvestmentTransaction.objects.filter(
                user=request.user, investment=inv
            ).aggregate(
                qty_bought=Sum("quantity", filter=Q(type=InvestmentTransaction.TYPE_BUY)),
                qty_sold=Sum("quantity", filter=Q(type=InvestmentTransaction.TYPE_SELL)),
            )
            inv.quantity = max(
                Decimal("0"),
                (agg["qty_bought"] or Decimal("0")) - (agg["qty_sold"] or Decimal("0")),
            )
            inv.save(update_fields=["quantity"])

    elif boleta.type == InvestmentTransaction.TYPE_EARNINGS:
        try:
            amount = Decimal(str(request.POST.get("amount", "0")).replace(",", "."))
        except (InvalidOperation, TypeError):
            return redirect("investimentos")

        boleta.date    = tx_date
        boleta.account = account
        boleta.amount  = amount
        boleta.notes   = notes
        boleta.save()

        if boleta.cash_transaction:
            ct = boleta.cash_transaction
            ct.date    = tx_date
            ct.amount  = abs(amount)
            ct.type    = Transaction.TYPE_CREDIT if amount >= 0 else Transaction.TYPE_DEBIT
            ct.account = account
            ct.notes   = notes
            ct.save()
        elif account:
            earn_tx = Transaction.objects.create(
                account=account,
                amount=abs(amount),
                type=Transaction.TYPE_CREDIT if amount >= 0 else Transaction.TYPE_DEBIT,
                date=tx_date,
                description=f"Rendimento: {inv.ticker or inv.name}",
                notes=notes,
                status=Transaction.STATUS_COMPLETED,
                is_investment=True,
            )
            boleta.cash_transaction = earn_tx
            boleta.save(update_fields=["cash_transaction"])

    elif boleta.type == InvestmentTransaction.TYPE_DIVIDENDS:
        try:
            amount = Decimal(str(request.POST.get("amount", "0")).replace(",", "."))
        except (InvalidOperation, TypeError):
            return redirect("investimentos")
        if amount <= 0:
            return redirect("investimentos")

        boleta.date    = tx_date
        boleta.account = account
        boleta.amount  = amount
        boleta.notes   = notes
        boleta.save()

        if boleta.cash_transaction:
            ct = boleta.cash_transaction
            ct.date    = tx_date
            ct.amount  = amount
            ct.account = account
            ct.notes   = notes
            ct.save()
        elif account:
            div_tx = Transaction.objects.create(
                account=account,
                amount=amount,
                type=Transaction.TYPE_CREDIT,
                date=tx_date,
                description=f"Dividendo: {inv.ticker or inv.name}",
                notes=notes,
                status=Transaction.STATUS_COMPLETED,
                is_investment=True,
            )
            boleta.cash_transaction = div_tx
            boleta.save(update_fields=["cash_transaction"])

    return redirect("investimentos")


@login_required
@require_POST
def investimento_rendimento(request, pk):
    """Legacy endpoint — kept for safety; delegates to the unified boleta flow."""
    inv = get_object_or_404(Investment, pk=pk, user=request.user)
    try:
        amount = Decimal(str(request.POST.get("amount", "0")).replace(",", "."))
    except (InvalidOperation, TypeError):
        return redirect("investimentos")
    tx_date = _dt(request.POST.get("date")) or _now_br().date()
    notes = request.POST.get("notes", "").strip()
    account_pk = _iv(request.POST.get("account"))
    account = inv.account
    if account_pk:
        try:
            account = Account.objects.get(pk=account_pk, user=request.user)
        except Account.DoesNotExist:
            pass
    if inv.quantity > 0:
        inv.current_price = inv.current_price + amount / inv.quantity
        inv.save(update_fields=["current_price"])
    earn_tx = None
    if account:
        earn_tx = Transaction.objects.create(
            account=account,
            amount=abs(amount),
            type=Transaction.TYPE_CREDIT if amount >= 0 else Transaction.TYPE_DEBIT,
            date=tx_date,
            description=f"Rendimento: {inv.ticker or inv.name}",
            notes=notes,
            status=Transaction.STATUS_COMPLETED,
            is_investment=True,
        )
    InvestmentTransaction.objects.create(
        user=request.user, investment=inv, account=account,
        type=InvestmentTransaction.TYPE_EARNINGS, date=tx_date, amount=amount,
        cash_transaction=earn_tx, notes=notes,
    )
    return redirect("investimentos")


# ═══════════════════════════════════════════════════════════════════════════
# Projeção
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def projecao(request):
    now = _now_br()
    current_month = now.replace(day=1).date()

    def _int_param(key, default, lo=1, hi=600):
        try:
            return max(lo, min(hi, int(request.GET.get(key, default))))
        except (ValueError, TypeError):
            return default

    first_snap = (
        AccountMonthSnapshot.objects
        .filter(account__user=request.user)
        .order_by("month")
        .values_list("month", flat=True)
        .first()
    )
    if first_snap:
        first_snap_date = (first_snap if isinstance(first_snap, date) else first_snap.date()).replace(day=1)
        default_n_past = (current_month.year - first_snap_date.year) * 12 + (current_month.month - first_snap_date.month)
    else:
        default_n_past = 3

    n_past = _int_param("n_past", max(default_n_past, 1))
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
    # All custody accounts (non-credit) contribute to cash snapshots.
    cash_snap_qs = (
        AccountMonthSnapshot.objects
        .filter(
            account__user=request.user,
            account__is_active=True,
            account__include_in_total=True,
            account__type__in=_CUSTODY_TYPES,
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

    # First snapshot month per account — transactions before this month are ignored.
    acc_first_snap: dict = {}  # {account_id: first_snap_month}
    for _m, _acc_dict in per_acc_snaps.items():
        for _aid in _acc_dict:
            if _aid not in acc_first_snap or _m < acc_first_snap[_aid]:
                acc_first_snap[_aid] = _m

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
            is_investment=False,
        )
        .annotate(mo=TruncMonth("date"))
        .values("mo", "type", "is_recurring", "account_id")
        .annotate(total=Sum("amount"))
    )

    actual: dict = {}
    for row in raw:
        mo = row["mo"] if isinstance(row["mo"], date) else row["mo"].date()
        mo = mo.replace(day=1)
        _aid = row["account_id"]
        _first = acc_first_snap.get(_aid)
        # If the account has a snapshot, only include transactions strictly after it
        if _first is not None and mo <= _first:
            continue
        key = (mo, row["type"], row["is_recurring"])
        actual[key] = actual.get(key, Decimal("0")) + (row["total"] or Decimal("0"))

    # Pre-fetch credit card account IDs so the loops below can treat them differently
    # (no snapshot anchor — every month is fair game for batimento).
    _credit_accs_data = list(
        Account.objects.filter(
            user=request.user, is_active=True, type=Account.TYPE_CREDIT
        ).values("pk", "due_day")
    )
    _credit_acc_ids: set = {a["pk"] for a in _credit_accs_data}
    _credit_closing_days: dict = {a["pk"]: a["due_day"] for a in _credit_accs_data if a["due_day"]}

    # Per-account net transactions — custody + credit card accounts.
    # Credit cards have no snapshots so they are handled without an anchor guard.
    per_acc_tx_raw = (
        Transaction.objects.filter(
            account__user=request.user,
            account__is_active=True,
            account__include_in_total=True,
            account__type__in=_CUSTODY_TYPES + [Account.TYPE_CREDIT],
            status=Transaction.STATUS_COMPLETED,
            date__gte=tx_query_start,
            date__lt=_add_months(end_month, 1),
            is_investment=False,
        )
        .annotate(mo=TruncMonth("date"))
        .values("account_id", "mo", "type")
        .annotate(total=Sum("amount"))
    )
    acc_month_net: dict = {}  # {(account_id, month): net_amount}
    inv_cash: dict = {}      # {(month, "credit"/"debit"): amount} — buy/sell cash flows, kept separate from actual so they don't inflate vi/ve display
    for _row in per_acc_tx_raw:
        _mo = (_row["mo"] if isinstance(_row["mo"], date) else _row["mo"].date()).replace(day=1)
        _aid = _row["account_id"]
        _first = acc_first_snap.get(_aid)
        # Credit cards have no snapshot — include all months; custody accounts require snapshot anchor
        if _aid in _credit_acc_ids:
            pass  # always include
        elif _first is None or _mo <= _first:
            continue
        _delta = _row["total"] or Decimal("0")
        _key = (_aid, _mo)
        acc_month_net[_key] = acc_month_net.get(_key, Decimal("0")) + (
            _delta if _row["type"] == "credit" else -_delta
        )

    # Buy/Sell boletas create is_investment=True cash transactions excluded from per_acc_tx_raw.
    # They must be included in acc_month_net so the batimento doesn't false-alarm when
    # cash leaves (buy) or enters (sell) an account that is separate from the custody account.
    _buysell_raw = (
        InvestmentTransaction.objects.filter(
            user=request.user,
            type__in=[InvestmentTransaction.TYPE_BUY, InvestmentTransaction.TYPE_SELL],
            account__isnull=False,
            date__gte=tx_query_start,
            date__lt=_add_months(end_month, 1),
        )
        .annotate(mo=TruncMonth("date"))
        .values("account_id", "mo", "type")
        .annotate(total=Sum("amount"))
    )
    for _row in _buysell_raw:
        _mo = (_row["mo"] if isinstance(_row["mo"], date) else _row["mo"].date()).replace(day=1)
        _aid = _row["account_id"]
        _first = acc_first_snap.get(_aid)
        if _first is None or _mo <= _first:
            continue
        _delta = _row["total"] or Decimal("0")
        _is_sell = _row["type"] == InvestmentTransaction.TYPE_SELL
        _sign = Decimal("1") if _is_sell else Decimal("-1")
        _key = (_aid, _mo)
        acc_month_net[_key] = acc_month_net.get(_key, Decimal("0")) + _sign * _delta
        # Track cash impact of buy/sell separately — included in balance but NOT in vi/ve display.
        _act_type = "credit" if _is_sell else "debit"
        inv_cash[(_mo, _act_type)] = inv_cash.get((_mo, _act_type), Decimal("0")) + _delta

    # Dividends: always financial, always impact cash, excluded from portfolio value.
    # Their cash transactions are is_investment=True so they're not in per_acc_tx_raw above.
    _div_raw = (
        InvestmentTransaction.objects.filter(
            user=request.user,
            type=InvestmentTransaction.TYPE_DIVIDENDS,
            account__isnull=False,
            date__gte=tx_query_start,
            date__lt=_add_months(end_month, 1),
        )
        .annotate(mo=TruncMonth("date"))
        .values("account_id", "mo")
        .annotate(total=Sum("amount"))
    )
    for _row in _div_raw:
        _mo = (_row["mo"] if isinstance(_row["mo"], date) else _row["mo"].date()).replace(day=1)
        _aid = _row["account_id"]
        _first = acc_first_snap.get(_aid)
        if _first is None or _mo <= _first:
            continue
        _key = (_aid, _mo)
        acc_month_net[_key] = acc_month_net.get(_key, Decimal("0")) + (_row["total"] or Decimal("0"))

    # Earnings + Dividends — both contribute to inv_result in the forward pass.
    # Dividends are already in acc_month_net (cash impact); here we capture them
    # for the investment-result column so they appear in the projection table/chart.
    _earn_raw = (
        InvestmentTransaction.objects.filter(
            user=request.user,
            type__in=[InvestmentTransaction.TYPE_EARNINGS, InvestmentTransaction.TYPE_DIVIDENDS],
            date__gte=tx_query_start,
            date__lt=_add_months(end_month, 1),
        )
        .annotate(mo=TruncMonth("date"))
        .values("mo")
        .annotate(total=Sum("amount"))
    )
    inv_earnings_by_month: dict = {}
    for _row in _earn_raw:
        _m = (_row["mo"] if isinstance(_row["mo"], date) else _row["mo"].date()).replace(day=1)
        inv_earnings_by_month[_m] = inv_earnings_by_month.get(_m, Decimal("0")) + (_row["total"] or Decimal("0"))

    # Individual transactions per account per month — for the drill-down detail view.
    # Includes investment transactions (is_investment=True) for visibility; they are
    # rendered as informational rows and excluded from the running balance calculation.
    tx_detail_qs = (
        Transaction.objects.filter(
            account__user=request.user,
            account__is_active=True,
            account__include_in_total=True,
            account__type__in=_CUSTODY_TYPES + [Account.TYPE_CREDIT],
            status=Transaction.STATUS_COMPLETED,
            date__gte=tx_query_start,
            date__lt=_add_months(end_month, 1),
        )
        .select_related("account", "category", "inv_boleta")
        .order_by("date", "id")
    )
    tx_by_acc_month: dict = {}  # {(account_id, month): [Transaction]}
    for _tx in tx_detail_qs:
        _mo = _tx.date.replace(day=1)
        _first = acc_first_snap.get(_tx.account_id)
        if _first is None:
            # Credit cards have no snapshots — include all their transactions
            if _tx.account.type != Account.TYPE_CREDIT:
                continue
        elif _mo <= _first:
            continue
        tx_by_acc_month.setdefault((_tx.account_id, _mo), []).append(_tx)
        per_acc_names.setdefault(_tx.account_id, _tx.account.name)
        per_acc_colors.setdefault(_tx.account_id, _tx.account.color)

    # ── Cumulative investment value per account per month ─────────────────────
    # Account snapshots represent the TOTAL balance (cash + investments).
    # Subtract cumulative investment value to obtain the liquid (available) balance.
    _all_inv_txs = list(
        InvestmentTransaction.objects.filter(user=request.user, account__isnull=False)
        .values("account_id", "date", "type", "amount")
        .order_by("date", "id")
    )
    _snap_months_sorted = sorted(set(list(per_acc_snaps.keys()) + months))
    _inv_running: dict = {}  # {account_id: Decimal} — cumulative value
    inv_value_by_acc_month: dict = {}  # {(account_id, month): value_at_end_of_month}
    _inv_ti = 0
    _inv_n = len(_all_inv_txs)
    for _smo in _snap_months_sorted:
        while _inv_ti < _inv_n:
            _t = _all_inv_txs[_inv_ti]
            _td = (_t["date"] if isinstance(_t["date"], date) else _t["date"].date())
            if _td.replace(day=1) > _smo:
                break
            _a = _t["account_id"]
            _v = _t["amount"] or Decimal("0")
            if _t["type"] == InvestmentTransaction.TYPE_BUY:
                _inv_running[_a] = _inv_running.get(_a, Decimal("0")) + _v
            elif _t["type"] == InvestmentTransaction.TYPE_SELL:
                _inv_running[_a] = max(Decimal("0"), _inv_running.get(_a, Decimal("0")) - _v)
            elif _t["type"] == InvestmentTransaction.TYPE_EARNINGS:
                _inv_running[_a] = _inv_running.get(_a, Decimal("0")) + _v
            _inv_ti += 1
        for _a, _val in _inv_running.items():
            inv_value_by_acc_month[(_a, _smo)] = _val

    # Liquid (available cash) versions of the snapshot dicts
    per_acc_snaps_liquid: dict = {
        _m: {
            _aid: _bal - inv_value_by_acc_month.get((_aid, _m), Decimal("0"))
            for _aid, _bal in _acc.items()
        }
        for _m, _acc in per_acc_snaps.items()
    }
    cash_snaps_liquid: dict = {
        _m: sum(_per.values())
        for _m, _per in per_acc_snaps_liquid.items()
    }

    recurring_list = list(
        RecurringTransaction.objects.filter(user=request.user, is_active=True)
        .select_related("account", "category")
    )
    recurring_by_acc: dict = {}  # {account_id (or None): [RecurringTransaction]}
    for _r in recurring_list:
        recurring_by_acc.setdefault(_r.account_id, []).append(_r)
        # Seed per-account name/colour from recurring accounts for accounts that may
        # have no actual Transaction records yet.
        if _r.account_id and _r.account:
            per_acc_names.setdefault(_r.account_id, _r.account.name)
            per_acc_colors.setdefault(_r.account_id, _r.account.color)

    def _fixed_for_month(mo, tx_type):
        total = Decimal("0")
        for r in recurring_list:
            if r.type != tx_type:
                continue
            # If linked to an account that has a snapshot, only count after that snapshot
            if r.account_id is not None:
                _first = acc_first_snap.get(r.account_id)
                if _first is not None and mo <= _first:
                    continue
            total += _amount_for_month(r, mo)
        return total

    proj_fixed_income = _fixed_for_month(current_month, RecurringTransaction.TYPE_INCOME)
    proj_fixed_expense = _fixed_for_month(current_month, RecurringTransaction.TYPE_EXPENSE)

    anchor = _projected_cash_balance(request.user, now.date())

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
        for _pm in sorted(m for m in per_acc_snaps_liquid if m < start_month):
            for _aid, _bal in per_acc_snaps_liquid[_pm].items():
                acc_last_known[_aid] = _bal
        _gm = _add_months(anchor_m, 1)
        while _gm < start_month:
            for _aid in list(acc_last_known.keys()):
                if _aid not in per_acc_snaps_liquid.get(_gm, {}):
                    acc_last_known[_aid] += acc_month_net.get((_aid, _gm), Decimal("0"))
            for _aid, _bal in per_acc_snaps_liquid.get(_gm, {}).items():
                acc_last_known[_aid] = _bal
            _gm = _add_months(_gm, 1)

    # ── Initial balance anchor ─────────────────────────────────────────────────
    if prior_snaps:
        anchor_m_liq = max(prior_snaps, key=lambda x: x[0])[0]
        running_balance = cash_snaps_liquid.get(anchor_m_liq, Decimal("0"))
        # Walk from anchor_m+1 to start_month, accumulating net from actual transactions;
        # re-anchor at any intermediate cash snapshot found in the gap.
        m = _add_months(anchor_m, 1)
        while m < start_month:
            gap_net = (
                actual.get((m, "credit", False), Decimal("0"))
                + actual.get((m, "credit", True), Decimal("0"))
                - actual.get((m, "debit", False), Decimal("0"))
                - actual.get((m, "debit", True), Decimal("0"))
                + inv_cash.get((m, "credit"), Decimal("0"))
                - inv_cash.get((m, "debit"), Decimal("0"))
            )
            running_balance += gap_net
            if m in cash_snaps_liquid:
                running_balance = cash_snaps_liquid[m]
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
    # Pre-build investments indexed by account for dividend suggestions in batimento.
    _inv_by_acc: dict = {}
    for _inv in Investment.objects.filter(user=request.user).select_related("account").order_by("name"):
        _inv_by_acc.setdefault(_inv.account_id, []).append(_inv)

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

        # Resultado Investimentos: earnings/losses logged via boletas only.
        earnings_mo = inv_earnings_by_month.get(mo, Decimal("0"))
        inv_result = earnings_mo if earnings_mo else None

        # Per-account batimento: only accounts with CONSECUTIVE monthly snapshots
        batimento_issues = []
        checked_any = False
        for aid, curr_bal in per_acc_snaps_liquid.get(mo, {}).items():
            prev_bal = per_acc_snaps_liquid.get(prev_mo, {}).get(aid)
            if prev_bal is None:
                continue  # First snapshot for this account (or a gap) — no warning
            checked_any = True
            acc_net = acc_month_net.get((aid, mo), Decimal("0"))
            for _r in recurring_by_acc.get(aid, []):
                _ramt = _amount_for_month(_r, mo)
                acc_net += _ramt if _r.type == RecurringTransaction.TYPE_INCOME else -_ramt
            diff = curr_bal - (prev_bal + acc_net)
            if abs(diff) >= Decimal("0.01"):
                batimento_issues.append({
                    "account_id": aid,
                    "account_name": per_acc_names.get(aid, f"Conta {aid}"),
                    "batimento_diff": diff,
                    "batimento_abs": abs(diff),
                    "batimento_abs_str": str(abs(diff)),
                    "account_investments": _inv_by_acc.get(aid, []),
                    "is_credit": False,
                })

        # Credit card batimento: only past months — bill already closed.
        # Current and future months are still open, so no warning is raised.
        if mo < current_month:
            for _cid in _credit_acc_ids:
                _c_txs = tx_by_acc_month.get((_cid, mo), [])

                # Total recurring expenses expected on this card this month
                _total_rec_exp = sum(
                    _amount_for_month(_r, mo)
                    for _r in recurring_by_acc.get(_cid, [])
                    if _r.type == RecurringTransaction.TYPE_EXPENSE
                )

                if not _c_txs and not _total_rec_exp:
                    continue
                checked_any = True

                # Actual transactions: variable purchases, transfers, executed recurring
                _c_net = sum(
                    (t.amount if t.type == Transaction.TYPE_CREDIT else -t.amount)
                    for t in _c_txs
                )

                # Avoid double-counting: subtract recurring expenses already present as
                # is_recurring=True debit transactions before adding the recurring total.
                _executed_rec_exp = sum(
                    t.amount for t in _c_txs
                    if t.is_recurring and t.type == Transaction.TYPE_DEBIT
                )
                _c_net -= max(Decimal("0"), _total_rec_exp - _executed_rec_exp)

                # diff = expected_balance − (prev_balance + net) = 0 − (0 + net) = −net
                _c_diff = -_c_net
                if abs(_c_diff) >= Decimal("0.01"):
                    batimento_issues.append({
                        "account_id": _cid,
                        "account_name": per_acc_names.get(_cid, f"Cartão {_cid}"),
                        "batimento_diff": _c_diff,
                        "batimento_abs": abs(_c_diff),
                        "batimento_abs_str": str(abs(_c_diff)),
                        "account_investments": [],
                        "is_credit": True,
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

        # liquid_end: cash-only balance (running_balance stays liquid for correct increments).
        # end_balance (shown to user): liquid_end + invested value = full patrimonial.
        snap_this_mo = per_acc_snaps_liquid.get(mo, {})
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
            liquid_end = snap_sum + carry_sum
        else:
            inv_net_mo = (
                inv_cash.get((mo, "credit"), Decimal("0"))
                - inv_cash.get((mo, "debit"), Decimal("0"))
            )
            liquid_end = running_balance + net + inv_net_mo
            for _aid in list(acc_last_known.keys()):
                _rec_net = sum(
                    (_amount_for_month(_r, mo) if _r.type == RecurringTransaction.TYPE_INCOME
                     else -_amount_for_month(_r, mo))
                    for _r in recurring_by_acc.get(_aid, [])
                )
                acc_last_known[_aid] += acc_month_net.get((_aid, mo), Decimal("0")) + _rec_net

        running_balance = liquid_end  # always liquid so future net increments stay correct

        # Patrimonial end_balance = liquid cash + cumulative invested value across all accounts
        inv_total_mo = sum(
            inv_value_by_acc_month.get((_aid, mo), Decimal("0"))
            for _aid in {aid for (aid, _) in inv_value_by_acc_month}
        )
        end_balance = liquid_end + inv_total_mo

        # ── Drill-down: per-account transaction breakdown ──────────────────────
        _drill_aids: set = set(per_acc_snaps_liquid.get(mo, {}).keys())
        for (_dk, _dm) in tx_by_acc_month:
            if _dm == mo:
                _drill_aids.add(_dk)
        # Include accounts that have recurring transactions this month.
        # Skip only when a first snapshot EXISTS and the month is at or before it
        # (account hadn't started yet). Accounts without snapshots are always eligible.
        for _a, _recs in recurring_by_acc.items():
            if _a is None:
                continue
            _first = acc_first_snap.get(_a)
            if _first is not None and mo <= _first:
                continue
            if any(_amount_for_month(_r, mo) for _r in _recs):
                _drill_aids.add(_a)

        def _build_drill_entries(items_iter, is_future_row, acc_id):
            _run = opening_bal.get(acc_id)  # None when account has no prior snapshot
            _has_run = _run is not None
            _entries = []
            for _e_credit, _e_debit, _e_date, _e_desc, _e_is_rec, _e_cat, _e_is_transfer, _e_is_inv, _e_is_earn in items_iter:
                if _has_run and not _e_is_earn:
                    _run += _e_credit - _e_debit
                _entries.append({
                    "date": _e_date,
                    "description": _e_desc,
                    "credit": _e_credit,
                    "debit": _e_debit,
                    "is_recurring": _e_is_rec,
                    "is_transfer": _e_is_transfer,
                    "is_investment": _e_is_inv,
                    "is_earnings": _e_is_earn,
                    "category_name": _e_cat,
                    "running_balance": _run if not _e_is_earn else None,
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
                        False, False, False,
                    ))
            else:
                _raw = []
                # Recurring projected amounts for this account/month.
                # Use computed expected date so past/current rows show a real date.
                for _r in sorted(recurring_by_acc.get(_did, []), key=lambda r: r.name):
                    _amt = _amount_for_month(_r, mo)
                    if not _amt:
                        continue
                    _income = _r.type == RecurringTransaction.TYPE_INCOME
                    _raw.append((
                        _amt if _income else Decimal("0"),
                        Decimal("0") if _income else _amt,
                        _proj_date(_r, mo), _r.name, True,
                        _r.category.name if _r.category else None,
                        False, False, False,
                    ))
                # Actual transaction records
                for _tx in tx_by_acc_month.get((_did, mo), []):
                    _isc = _tx.type == Transaction.TYPE_CREDIT
                    try:
                        _is_earn = _tx.inv_boleta.type == InvestmentTransaction.TYPE_EARNINGS
                    except InvestmentTransaction.DoesNotExist:
                        _is_earn = False
                    _raw.append((
                        _tx.amount if _isc else Decimal("0"),
                        Decimal("0") if _isc else _tx.amount,
                        _tx.date, _tx.description, _tx.is_recurring,
                        _tx.category.name if _tx.category else None,
                        _tx.is_transfer, _tx.is_investment, _is_earn,
                    ))
                # Sort: actual transactions (have date) first; recurring projections last
                _raw.sort(key=lambda x: (x[2] is None, x[2] or date.min))
            _entries = _build_drill_entries(_raw, row["is_future"], _did)
            _tc = sum(e["credit"] for e in _entries if not e["is_earnings"])
            _td = sum(e["debit"] for e in _entries if not e["is_earnings"])
            _cash_count = sum(1 for e in _entries if not e["is_investment"])
            _inv_count = sum(1 for e in _entries if e["is_investment"])
            drill_accounts.append({
                "id": _did,
                "name": per_acc_names.get(_did, f"Conta {_did}"),
                "color": per_acc_colors.get(_did, "#64748B"),
                "txs": _entries,
                "total_credit": _tc,
                "total_debit": _td,
                "total_net": _tc - _td,
                "opening_balance": opening_bal.get(_did),
                "cash_tx_count": _cash_count,
                "inv_tx_count": _inv_count,
                "inv_balance": inv_value_by_acc_month.get((_did, mo), Decimal("0")),
            })

        # Unassigned recurring (no account) — shown for all months, not just future
        _unassigned = [
            _r for _r in recurring_by_acc.get(None, [])
            if _amount_for_month(_r, mo)
        ]
        if _unassigned:
            _raw = []
            for _r in sorted(_unassigned, key=lambda r: r.name):
                _amt = _amount_for_month(_r, mo)
                _income = _r.type == RecurringTransaction.TYPE_INCOME
                _proj_d = None if row["is_future"] else _proj_date(_r, mo)
                _raw.append((
                    _amt if _income else Decimal("0"),
                    Decimal("0") if _income else _amt,
                    _proj_d, _r.name, True,
                    _r.category.name if _r.category else None,
                    False, False, False,
                ))
            _entries = _build_drill_entries(_raw, row["is_future"], None)
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
                "cash_tx_count": len(_entries),
                "inv_tx_count": 0,
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
        "net": [float(r["net"]) for r in rows],
        "inv_result": [float(r["inv_result"]) if r["inv_result"] is not None else None for r in rows],
        "balance": [float(r["end_balance"]) for r in rows],
        "types": [
            "current" if r["is_current"] else "future" if r["is_future"] else "past"
            for r in rows
        ],
    })

    cash_accounts = Account.objects.filter(
        user=request.user, is_active=True,
        type__in=_CUSTODY_TYPES,
    ).order_by("name")

    categories = Category.objects.filter(
        Q(user=request.user) | Q(user__isnull=True)
    ).order_by("type", "name")

    # ── Missing snapshot warnings ──────────────────────────────────────────
    # Find the maximum snapshot month across ALL active custody accounts.
    # For that month, every active custody account should also have a snapshot.
    snap_missing = []
    _max_snap_raw = (
        AccountMonthSnapshot.objects
        .filter(account__user=request.user, account__type__in=_CUSTODY_TYPES, account__is_active=True)
        .order_by("-month")
        .values_list("month", flat=True)
        .first()
    )
    if _max_snap_raw is not None:
        _max_mo = (_max_snap_raw if isinstance(_max_snap_raw, date) else _max_snap_raw.date()).replace(day=1)
        _accs_with_snap = set(
            AccountMonthSnapshot.objects
            .filter(account__user=request.user, month__year=_max_mo.year, month__month=_max_mo.month)
            .values_list("account_id", flat=True)
        )
        for _acc in cash_accounts:
            if _acc.pk not in _accs_with_snap:
                snap_missing.append({
                    "account_id": _acc.pk,
                    "account_name": _acc.name,
                    "missing_month": _max_mo,
                    "missing_month_label": f"{_MONTHS[_max_mo.month - 1].capitalize()} {_max_mo.year}",
                })

    # JSON map used by the batimento modal to filter investments per account.
    # position types (dividends / earnings / sell): only investments in that account with qty > 0
    # buy: all investments (may be adding to any position)
    def _inv_label(i):
        return f"{i.ticker} — {i.name}" if i.ticker else i.name

    _inv_by_acc_modal = {
        str(_aid): [{"pk": str(i.pk), "label": _inv_label(i)} for i in _invs if i.quantity > 0]
        for _aid, _invs in _inv_by_acc.items()
    }
    _all_investments_modal = [
        {"pk": str(i.pk), "label": _inv_label(i)}
        for i in Investment.objects.filter(user=request.user).order_by("name")
    ]

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
        "inv_by_acc_json": json.dumps(_inv_by_acc_modal),
        "all_investments_json": json.dumps(_all_investments_modal),
        "credit_closing_days_json": json.dumps(_credit_closing_days),
        "snap_missing": snap_missing,
        "cash_accounts": cash_accounts,
        "categories": categories,
        "investments": Investment.objects.filter(user=request.user).order_by("name"),
    })


# ═══════════════════════════════════════════════════════════════════════════
# Settings
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def settings(request):
    profile = getattr(request.user, "profile", None)
    return render(request, "dashboard/settings.html", {"profile": profile})


@login_required
@require_POST
def settings_update(request):
    user = request.user
    profile = getattr(user, "profile", None)

    first_name = request.POST.get("first_name", "").strip()
    last_name = request.POST.get("last_name", "").strip()
    phone = request.POST.get("phone", "").strip()

    user.first_name = first_name
    user.last_name = last_name
    user.save(update_fields=["first_name", "last_name"])

    if profile:
        profile.phone = phone
        profile.save(update_fields=["phone"])

    messages.success(request, "Dados atualizados com sucesso.")
    return redirect("settings")


@login_required
@require_POST
def sol_mark_shown(request):
    """Marca o tour da Sol como exibido para este usuário (chamado pelo JS no primeiro login)."""
    from django.http import JsonResponse
    try:
        profile = request.user.profile
        if not profile.sol_tour_shown:
            profile.sol_tour_shown = True
            profile.save(update_fields=["sol_tour_shown"])
    except Exception:
        pass
    return JsonResponse({"ok": True})

