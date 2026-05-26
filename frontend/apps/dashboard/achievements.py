"""
Gamification engine: Health Score, Achievements, Streak.
All logic is isolated here to keep views.py clean.
"""
from datetime import date
from decimal import Decimal

from django.db.models import Q, Sum

ACHIEVEMENTS = {
    "first_account": {
        "name": "Primeira Conta",
        "description": "Cadastrou sua primeira conta financeira",
        "icon": "🏦",
        "points": 100,
        "color": "#00C97A",
    },
    "first_snapshot": {
        "name": "Saldo Registrado",
        "description": "Registrou o saldo inicial de uma conta",
        "icon": "📸",
        "points": 150,
        "color": "#2563EB",
    },
    "first_transaction": {
        "name": "Primeiro Lançamento",
        "description": "Registrou sua primeira transação",
        "icon": "✏️",
        "points": 100,
        "color": "#00C97A",
    },
    "fixos_configured": {
        "name": "Fixos no Controle",
        "description": "Configurou pelo menos um gasto ou receita fixo",
        "icon": "🔁",
        "points": 200,
        "color": "#F59E0B",
    },
    "first_goal": {
        "name": "Meta Criada",
        "description": "Definiu sua primeira meta financeira",
        "icon": "🎯",
        "points": 200,
        "color": "#2563EB",
    },
    "goal_completed": {
        "name": "Meta Conquistada",
        "description": "Concluiu uma meta financeira",
        "icon": "🏆",
        "points": 500,
        "color": "#F59E0B",
    },
    "setup_complete": {
        "name": "Setup Completo",
        "description": "Completou todos os passos de configuração inicial",
        "icon": "🚀",
        "points": 300,
        "color": "#00C97A",
    },
    "month_all_categorized": {
        "name": "Tudo Categorizado",
        "description": "Categorizou 100% dos lançamentos de um mês",
        "icon": "🏷️",
        "points": 250,
        "color": "#2563EB",
    },
    "positive_balance_3": {
        "name": "Equilíbrio Constante",
        "description": "Manteve saldo positivo por 3 meses consecutivos",
        "icon": "📈",
        "points": 400,
        "color": "#00C97A",
    },
    "first_investment": {
        "name": "Investidor",
        "description": "Cadastrou seu primeiro investimento",
        "icon": "💼",
        "points": 250,
        "color": "#F59E0B",
    },
}


def award(user, slug, request=None):
    """Grant an achievement if not already earned. Returns True if newly awarded."""
    from apps.finances.models import UserAchievement

    _, created = UserAchievement.objects.get_or_create(user=user, slug=slug)
    if created and request is not None:
        pending = request.session.get("_achievements", [])
        pending.append(slug)
        request.session["_achievements"] = pending
        request.session.modified = True
    return created


def check_achievements(user, request=None):
    """Check all condition-based achievements and award where applicable."""
    from apps.finances.models import (
        Account, AccountMonthSnapshot, Goal, Investment,
        RecurringTransaction, Transaction,
    )

    # first_account
    if Account.objects.filter(user=user).exists():
        award(user, "first_account", request)

    # first_snapshot
    if AccountMonthSnapshot.objects.filter(account__user=user).exists():
        award(user, "first_snapshot", request)

    # first_transaction
    if Transaction.objects.filter(account__user=user).exists():
        award(user, "first_transaction", request)

    # fixos_configured
    if RecurringTransaction.objects.filter(user=user, is_active=True).exists():
        award(user, "fixos_configured", request)

    # first_goal / goal_completed
    goals = Goal.objects.filter(user=user)
    if goals.exists():
        award(user, "first_goal", request)
    if goals.filter(is_completed=True).exists():
        award(user, "goal_completed", request)

    # setup_complete: has account, snapshot, transaction, fixo, and goal
    has_setup = (
        Account.objects.filter(user=user).exists()
        and AccountMonthSnapshot.objects.filter(account__user=user).exists()
        and Transaction.objects.filter(account__user=user).exists()
        and RecurringTransaction.objects.filter(user=user, is_active=True).exists()
        and goals.exists()
    )
    if has_setup:
        award(user, "setup_complete", request)

    # first_investment
    if Investment.objects.filter(user=user).exists():
        award(user, "first_investment", request)

    # month_all_categorized: any recent month where all variable txs have a category
    today = date.today()
    for months_back in range(3):
        y = today.year if today.month - months_back > 0 else today.year - 1
        m = (today.month - months_back - 1) % 12 + 1
        month_txs = Transaction.objects.filter(
            account__user=user,
            date__year=y, date__month=m,
            status=Transaction.STATUS_COMPLETED,
            is_transfer=False,
        )
        total = month_txs.count()
        if total > 0:
            uncategorized = month_txs.filter(category__isnull=True).count()
            if uncategorized == 0:
                award(user, "month_all_categorized", request)
                break

    # positive_balance_3: last 3 months all had income > expense
    positive_count = 0
    for months_back in range(1, 4):
        y = today.year if today.month - months_back > 0 else today.year - 1
        m = (today.month - months_back - 1) % 12 + 1
        inc = Transaction.objects.filter(
            account__user=user, date__year=y, date__month=m,
            type=Transaction.TYPE_CREDIT, is_transfer=False,
            status=Transaction.STATUS_COMPLETED,
        ).aggregate(t=Sum("amount"))["t"] or Decimal("0")
        exp = Transaction.objects.filter(
            account__user=user, date__year=y, date__month=m,
            type=Transaction.TYPE_DEBIT, is_transfer=False,
            status=Transaction.STATUS_COMPLETED,
        ).aggregate(t=Sum("amount"))["t"] or Decimal("0")
        if inc > exp:
            positive_count += 1
        else:
            break
    if positive_count >= 3:
        award(user, "positive_balance_3", request)


def compute_streak(user):
    """Count consecutive months (going back from current) with ≥1 completed transaction."""
    from apps.finances.models import Transaction

    today = date.today()
    streak = 0
    for months_back in range(1, 25):
        y = today.year if today.month - months_back > 0 else today.year - 1
        m = (today.month - months_back - 1) % 12 + 1
        has_tx = Transaction.objects.filter(
            account__user=user,
            date__year=y, date__month=m,
            status=Transaction.STATUS_COMPLETED,
        ).exists()
        if has_tx:
            streak += 1
        else:
            break
    return streak


def compute_health_score(user):
    """
    Returns dict: score(0-100), label, color, breakdown list.

    Components:
      setup       20pts  — has account + snapshot + fixo
      savings     30pts  — savings rate this month (income - expense) / income
      commitment  25pts  — fixos / total expense ratio
      goals       15pts  — progress toward active goals
      categories  10pts  — % of transactions with a category
    """
    from apps.finances.models import (
        Account, AccountMonthSnapshot, Goal, RecurringTransaction, Transaction,
    )

    today = date.today()
    year, month = today.year, today.month

    # ── Setup (20pts) ────────────────────────────────────────────────────────
    has_account = Account.objects.filter(user=user).exists()
    has_snapshot = AccountMonthSnapshot.objects.filter(account__user=user).exists()
    has_fixo = RecurringTransaction.objects.filter(user=user, is_active=True).exists()
    setup_pts = 0
    if has_account:
        setup_pts += 7
    if has_snapshot:
        setup_pts += 7
    if has_fixo:
        setup_pts += 6

    # ── Savings rate (30pts) ─────────────────────────────────────────────────
    inc = Transaction.objects.filter(
        account__user=user, date__year=year, date__month=month,
        type=Transaction.TYPE_CREDIT, is_transfer=False,
        status=Transaction.STATUS_COMPLETED,
    ).aggregate(t=Sum("amount"))["t"] or Decimal("0")
    exp = Transaction.objects.filter(
        account__user=user, date__year=year, date__month=month,
        type=Transaction.TYPE_DEBIT, is_transfer=False,
        status=Transaction.STATUS_COMPLETED,
    ).aggregate(t=Sum("amount"))["t"] or Decimal("0")
    if inc > 0:
        rate = float((inc - exp) / inc)
        if rate >= 0.30:
            savings_pts = 30
        elif rate >= 0.20:
            savings_pts = 24
        elif rate >= 0.10:
            savings_pts = 18
        elif rate >= 0:
            savings_pts = 10
        else:
            savings_pts = 0
    else:
        savings_pts = 0

    # ── Commitment rate (25pts) — fixo expense / total expense ──────────────
    from datetime import timedelta
    month_start = date(year, month, 1)
    import calendar as _cal
    last_day = _cal.monthrange(year, month)[1]
    next_month_start = date(year, month + 1, 1) if month < 12 else date(year + 1, 1, 1)

    fixos_qs = RecurringTransaction.objects.filter(
        user=user, is_active=True, start_date__lt=next_month_start,
    ).filter(Q(end_date__isnull=True) | Q(end_date__gte=month_start))

    fixos_exp = fixos_qs.filter(type=RecurringTransaction.TYPE_EXPENSE)
    fixos_total = Decimal("0")
    for r in fixos_exp:
        fixos_total += _amount_for_month_local(r, month_start)

    total_exp = exp + fixos_total
    if total_exp > 0:
        commitment_ratio = float(fixos_total / total_exp)
        if commitment_ratio >= 0.5:
            commitment_pts = 25
        elif commitment_ratio >= 0.3:
            commitment_pts = 20
        elif commitment_ratio >= 0.1:
            commitment_pts = 12
        elif commitment_ratio > 0:
            commitment_pts = 6
        else:
            commitment_pts = 0
    else:
        commitment_pts = 0

    # ── Goal progress (15pts) ────────────────────────────────────────────────
    goals = Goal.objects.filter(user=user, is_completed=False)
    if goals.exists():
        avg_progress = sum(
            min(float(g.current_amount / g.target_amount), 1.0)
            for g in goals
            if g.target_amount > 0
        ) / goals.count()
        goal_pts = int(avg_progress * 15)
    else:
        goal_pts = 0

    # ── Categorization rate (10pts) ──────────────────────────────────────────
    month_txs = Transaction.objects.filter(
        account__user=user, date__year=year, date__month=month,
        status=Transaction.STATUS_COMPLETED, is_transfer=False,
    )
    total_txs = month_txs.count()
    if total_txs > 0:
        categorized = month_txs.filter(category__isnull=False).count()
        cat_rate = categorized / total_txs
        cat_pts = int(cat_rate * 10)
    else:
        cat_pts = 0

    score = setup_pts + savings_pts + commitment_pts + goal_pts + cat_pts
    score = min(max(score, 0), 100)

    if score >= 80:
        label, color, ring_color = "Excelente", "#00C97A", "#00C97A"
    elif score >= 60:
        label, color, ring_color = "Bom", "#2563EB", "#2563EB"
    elif score >= 40:
        label, color, ring_color = "Regular", "#F59E0B", "#F59E0B"
    else:
        label, color, ring_color = "Atenção", "#EF4444", "#EF4444"

    # SVG ring: r=38 → circumference ≈ 238.76; dashoffset = circ × (1 − score/100)
    ring_offset = round(238.76 * (1 - score / 100), 1)

    return {
        "score": score,
        "label": label,
        "color": color,
        "ring_color": ring_color,
        "ring_offset": ring_offset,
        "breakdown": [
            {"name": "Configuração", "pts": setup_pts, "max": 20},
            {"name": "Taxa de poupança", "pts": savings_pts, "max": 30},
            {"name": "Comprometimento", "pts": commitment_pts, "max": 25},
            {"name": "Metas", "pts": goal_pts, "max": 15},
            {"name": "Categorização", "pts": cat_pts, "max": 10},
        ],
    }


# ── Local helper (avoids circular import with views.py) ─────────────────────

def _add_months_local(d, n):
    total = d.year * 12 + (d.month - 1) + n
    y, m = divmod(total, 12)
    return date(y, m + 1, 1)


def _amount_for_month_local(r, mo):
    """Mirrors views._amount_for_month to avoid circular import."""
    from datetime import timedelta
    from apps.finances.models import RecurringTransaction

    next_mo = _add_months_local(mo, 1)
    if r.start_date.replace(day=1) >= next_mo:
        return Decimal("0")
    if r.end_date and r.end_date.replace(day=1) < mo:
        return Decimal("0")

    freq = r.frequency
    if freq in (RecurringTransaction.FREQ_WEEKLY, RecurringTransaction.FREQ_BIWEEKLY):
        if r.day_of_week is None:
            return r.monthly_amount
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
            if occ >= mo:
                count += 1
            occ += timedelta(days=step)
        return r.amount * count

    # Monthly
    if freq == RecurringTransaction.FREQ_MONTHLY:
        return r.amount

    # Quarterly / semiannual / annual
    period_map = {
        RecurringTransaction.FREQ_QUARTERLY: 3,
        RecurringTransaction.FREQ_SEMIANNUAL: 6,
        RecurringTransaction.FREQ_ANNUAL: 12,
    }
    period = period_map.get(freq)
    if period is None:
        return r.amount
    ref = r.start_date.replace(day=1)
    mo_offset = (mo.year - ref.year) * 12 + (mo.month - ref.month)
    if mo_offset >= 0 and mo_offset % period == 0:
        return r.amount
    return Decimal("0")
