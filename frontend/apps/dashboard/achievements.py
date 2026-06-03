"""
Gamification engine: Health Score, Achievements (4-tier progression), Streak.

Travadas: milestone achievements — only go up, never decrease.
Vivas:    habit achievements — reflect current behaviour, can increase or decrease.
          best_level is preserved even when the live level regresses.
"""
import json
from datetime import date
from decimal import Decimal

from django.db.models import Q, Sum

# ── Tier metadata ─────────────────────────────────────────────────────────────

TIER_NAMES  = ["Bronze", "Prata", "Ouro", "Platina"]
TIER_COLORS = ["#B45309", "#64748B", "#D97706", "#7C3AED"]

# ── Achievement definitions ───────────────────────────────────────────────────
#
# thresholds:        metric values that unlock each tier (Bronze → Platina)
# tier_pts:          points awarded at each tier
# criterion_labels:  human-readable label per tier shown in the journey modal
# metric_fmt:        "{v} ..." template for the current-progress line in modal
# viva:              True → live (can regress); False → ratchet (never decreases)

ACHIEVEMENTS = {
    # ── Travadas ──────────────────────────────────────────────────────────────
    "first_account": {
        "name": "Primeira Conta",
        "description": "Cadastrou contas financeiras",
        "icon": "🏦",
        "viva": False,
        "thresholds":        [1, 2, 3, 5],
        "tier_pts":          [100, 180, 280, 450],
        "criterion_labels":  ["1 conta cadastrada", "2 contas cadastradas",
                               "3 contas cadastradas", "5 contas cadastradas"],
        "metric_fmt":        "{v} conta(s) cadastrada(s)",
    },
    "first_transaction": {
        "name": "Primeiro Lançamento",
        "description": "Registrou transações",
        "icon": "✏️",
        "viva": False,
        "thresholds":        [1, 50, 200, 500],
        "tier_pts":          [100, 200, 400, 700],
        "criterion_labels":  ["1 lançamento registrado", "50 lançamentos",
                               "200 lançamentos", "500 lançamentos"],
        "metric_fmt":        "{v} lançamento(s) no total",
    },
    "first_goal": {
        "name": "Meta Criada",
        "description": "Definiu metas financeiras",
        "icon": "🎯",
        "viva": False,
        "thresholds":        [1, 3, 7, 12],
        "tier_pts":          [100, 250, 420, 650],
        "criterion_labels":  ["1 meta criada", "3 metas criadas",
                               "7 metas criadas", "12 metas criadas"],
        "metric_fmt":        "{v} meta(s) criada(s)",
    },
    "goal_completed": {
        "name": "Meta Conquistada",
        "description": "Concluiu metas financeiras",
        "icon": "🏆",
        "viva": False,
        "thresholds":        [1, 2, 3, 5],
        "tier_pts":          [500, 800, 1100, 1800],
        "criterion_labels":  ["1 meta concluída", "2 metas concluídas",
                               "3 metas concluídas", "5 metas concluídas"],
        "metric_fmt":        "{v} meta(s) concluída(s)",
    },
    "setup_complete": {
        "name": "Setup Completo",
        "description": "Configurou o perfil financeiro",
        "icon": "🚀",
        "viva": True,
        "thresholds":        [1, 2, 3, 4],
        "tier_pts":          [80, 160, 280, 420],
        "criterion_labels":  ["Conta + saldo registrado",
                               "+ primeiro lançamento",
                               "+ fixo/recorrente configurado",
                               "+ investimento e meta criados"],
        "metric_fmt":        "{v} de 4 etapas concluídas",
    },
    "first_investment": {
        "name": "Investidor",
        "description": "Cadastrou investimentos",
        "icon": "💼",
        "viva": False,
        "thresholds":        [1, 5, 10, 20],
        "tier_pts":          [150, 350, 600, 950],
        "criterion_labels":  ["1 investimento cadastrado", "5 investimentos",
                               "10 investimentos", "20 investimentos"],
        "metric_fmt":        "{v} investimento(s) cadastrado(s)",
    },
    # ── Vivas ─────────────────────────────────────────────────────────────────
    "first_snapshot": {
        "name": "Saldo Registrado",
        "description": "Meses consecutivos com saldo registrado",
        "icon": "📸",
        "viva": True,
        "thresholds":        [1, 3, 6, 12],
        "tier_pts":          [75, 225, 500, 750],
        "criterion_labels":  ["1 mês com saldo registrado", "3 meses seguidos",
                               "6 meses seguidos", "12 meses seguidos"],
        "metric_fmt":        "{v} mês(es) consecutivo(s) com saldo",
    },
    "month_all_categorized": {
        "name": "Tudo Categorizado",
        "description": "Meses consecutivos 100% categorizados",
        "icon": "🏷️",
        "viva": True,
        "thresholds":        [1, 2, 4, 6],
        "tier_pts":          [100, 250, 450, 700],
        "criterion_labels":  ["1 mês 100% categorizado", "2 meses seguidos",
                               "4 meses seguidos", "6 meses seguidos"],
        "metric_fmt":        "{v} mês(es) consecutivo(s) 100% categorizado(s)",
    },
    "positive_balance_3": {
        "name": "Equilíbrio Constante",
        "description": "Meses consecutivos com saldo positivo",
        "icon": "📈",
        "viva": True,
        "thresholds":        [1, 3, 6, 12],
        "tier_pts":          [100, 400, 750, 1100],
        "criterion_labels":  ["1 mês com saldo positivo", "3 meses seguidos",
                               "6 meses seguidos", "12 meses seguidos"],
        "metric_fmt":        "{v} mês(es) consecutivo(s) positivo(s)",
    },
    "fixos_configured": {
        "name": "Fixos no Controle",
        "description": "Recorrentes ativos configurados",
        "icon": "🔁",
        "viva": True,
        "thresholds":        [2, 5, 8, 12],
        "tier_pts":          [100, 280, 520, 820],
        "criterion_labels":  ["2 fixos ativos", "5 fixos ativos",
                               "8 fixos ativos", "12 fixos ativos"],
        "metric_fmt":        "{v} fixo(s) ativo(s) atualmente",
    },
}


# ── Core helpers ──────────────────────────────────────────────────────────────

def _tlevel(value, thresholds):
    """Return tier level 1–4. 0 if below first threshold."""
    level = 0
    for i, t in enumerate(thresholds):
        if value >= t:
            level = i + 1
    return level


def _update_level(user, slug, new_level, viva, request=None):
    """Persist achievement level. Travadas only increase; vivas reflect exact new_level."""
    from apps.finances.models import UserAchievement

    if new_level == 0:
        if viva:
            try:
                obj = UserAchievement.objects.get(user=user, slug=slug)
                if obj.level != 0:
                    obj.level = 0
                    obj.save(update_fields=["level"])
            except UserAchievement.DoesNotExist:
                pass
        return

    try:
        obj = UserAchievement.objects.get(user=user, slug=slug)
        old_level = obj.level
        target   = new_level if viva else max(obj.level, new_level)
        new_best = max(obj.best_level, new_level)
        if target == old_level and new_best == obj.best_level:
            return
        obj.level = target
        obj.best_level = new_best
        obj.save(update_fields=["level", "best_level"])
        if target > old_level:
            _notify(request, slug, target)
    except UserAchievement.DoesNotExist:
        UserAchievement.objects.create(user=user, slug=slug, level=new_level, best_level=new_level)
        _notify(request, slug, new_level)


def _notify(request, slug, level):
    if request is None:
        return
    pending = request.session.get("_achievements", [])
    pending.append({"slug": slug, "level": level})
    request.session["_achievements"] = pending
    request.session.modified = True


# ── Metric computers ──────────────────────────────────────────────────────────

def _setup_steps(user):
    from apps.finances.models import (
        Account, AccountMonthSnapshot, Goal, Investment, RecurringTransaction, Transaction,
    )
    if not Account.objects.filter(user=user).exists():
        return 0
    if not AccountMonthSnapshot.objects.filter(account__user=user).exists():
        return 0
    steps = 1
    if not Transaction.objects.filter(account__user=user, is_transfer=False).exists():
        return steps
    steps = 2
    if not RecurringTransaction.objects.filter(user=user, is_active=True).exists():
        return steps
    steps = 3
    if Investment.objects.filter(user=user).exists() and Goal.objects.filter(user=user).exists():
        steps = 4
    return steps


def _snapshot_streak(user):
    from apps.finances.models import AccountMonthSnapshot
    today = date.today()
    streak = 0
    mo = _add_months_local(date(today.year, today.month, 1), -1)
    for _ in range(24):
        if AccountMonthSnapshot.objects.filter(
            account__user=user, month__year=mo.year, month__month=mo.month,
        ).exists():
            streak += 1
        else:
            break
        mo = _add_months_local(mo, -1)
    return streak


def _categorized_streak(user):
    from apps.finances.models import Transaction
    today = date.today()
    streak = 0
    mo = _add_months_local(date(today.year, today.month, 1), -1)
    for _ in range(24):
        txs = Transaction.objects.filter(
            account__user=user, date__year=mo.year, date__month=mo.month,
            status=Transaction.STATUS_COMPLETED, is_transfer=False,
        )
        total = txs.count()
        if total == 0:
            break
        if txs.filter(category__isnull=True).count() == 0:
            streak += 1
        else:
            break
        mo = _add_months_local(mo, -1)
    return streak


def _positive_streak(user):
    from apps.finances.models import RecurringTransaction, Transaction
    today = date.today()
    streak = 0
    mo = _add_months_local(date(today.year, today.month, 1), -1)
    for _ in range(24):
        mo_end = _add_months_local(mo, 1)
        inc = Transaction.objects.filter(
            account__user=user, date__year=mo.year, date__month=mo.month,
            type=Transaction.TYPE_CREDIT, is_transfer=False,
            status=Transaction.STATUS_COMPLETED,
        ).aggregate(t=Sum("amount"))["t"] or Decimal("0")
        exp = Transaction.objects.filter(
            account__user=user, date__year=mo.year, date__month=mo.month,
            type=Transaction.TYPE_DEBIT, is_transfer=False,
            status=Transaction.STATUS_COMPLETED,
        ).aggregate(t=Sum("amount"))["t"] or Decimal("0")
        fixos = RecurringTransaction.objects.filter(
            user=user, is_active=True, start_date__lt=mo_end,
        ).filter(Q(end_date__isnull=True) | Q(end_date__gte=mo))
        for r in fixos.filter(type=RecurringTransaction.TYPE_INCOME):
            inc += _amount_for_month_local(r, mo)
        for r in fixos.filter(type=RecurringTransaction.TYPE_EXPENSE):
            exp += _amount_for_month_local(r, mo)
        if (inc + exp) == 0:
            break
        if inc > exp:
            streak += 1
        else:
            break
        mo = _add_months_local(mo, -1)
    return streak


def _compute_metric(slug, user):
    """Return the current raw metric value for a given achievement slug."""
    from apps.finances.models import Account, Goal, Investment, RecurringTransaction, Transaction
    if slug == "first_account":
        return Account.objects.filter(user=user).count()
    if slug == "first_transaction":
        return Transaction.objects.filter(account__user=user, is_transfer=False).count()
    if slug == "first_goal":
        return Goal.objects.filter(user=user).count()
    if slug == "goal_completed":
        return Goal.objects.filter(user=user, is_completed=True).count()
    if slug == "setup_complete":
        return _setup_steps(user)
    if slug == "first_investment":
        return Investment.objects.filter(user=user).count()
    if slug == "first_snapshot":
        return _snapshot_streak(user)
    if slug == "month_all_categorized":
        return _categorized_streak(user)
    if slug == "positive_balance_3":
        return _positive_streak(user)
    if slug == "fixos_configured":
        return RecurringTransaction.objects.filter(user=user, is_active=True).count()
    return 0


# ── Public API ────────────────────────────────────────────────────────────────

def check_achievements(user, request=None):
    """Compute current level for every achievement and persist changes."""
    from apps.finances.models import Account, Goal, Investment, RecurringTransaction, Transaction

    _update_level(user, "first_account",
                  _tlevel(Account.objects.filter(user=user).count(), [1, 2, 3, 5]),
                  False, request)
    _update_level(user, "first_transaction",
                  _tlevel(Transaction.objects.filter(account__user=user, is_transfer=False).count(),
                           [1, 50, 200, 500]),
                  False, request)
    _update_level(user, "first_goal",
                  _tlevel(Goal.objects.filter(user=user).count(), [1, 3, 7, 12]),
                  False, request)
    _update_level(user, "goal_completed",
                  _tlevel(Goal.objects.filter(user=user, is_completed=True).count(), [1, 2, 3, 5]),
                  False, request)
    _update_level(user, "first_investment",
                  _tlevel(Investment.objects.filter(user=user).count(), [1, 5, 10, 20]),
                  False, request)
    _update_level(user, "setup_complete", _setup_steps(user), True, request)

    _update_level(user, "fixos_configured",
                  _tlevel(RecurringTransaction.objects.filter(user=user, is_active=True).count(),
                           [2, 5, 8, 12]),
                  True, request)
    _update_level(user, "first_snapshot",
                  _tlevel(_snapshot_streak(user), [1, 3, 6, 12]),
                  True, request)
    _update_level(user, "month_all_categorized",
                  _tlevel(_categorized_streak(user), [1, 2, 4, 6]),
                  True, request)
    _update_level(user, "positive_balance_3",
                  _tlevel(_positive_streak(user), [1, 3, 6, 12]),
                  True, request)


def build_achievements_list(user):
    """Return list of dicts ready for template rendering, including modal_json."""
    from apps.finances.models import UserAchievement
    uas = {ua.slug: ua for ua in UserAchievement.objects.filter(user=user)}
    result = []
    for slug, data in ACHIEVEMENTS.items():
        ua         = uas.get(slug)
        level      = ua.level if ua else 0
        best_level = ua.best_level if ua else 0
        pts        = data["tier_pts"][level - 1] if level > 0 else 0
        next_pts   = data["tier_pts"][level] if level < 4 else None
        delta_pts  = (next_pts - pts) if next_pts is not None else None
        metric_val = _compute_metric(slug, user)
        regressed  = data["viva"] and best_level > level

        # Build per-tier journey list
        journey = []
        for i in range(4):
            tn = i + 1
            journey.append({
                "name":          TIER_NAMES[i],
                "color":         TIER_COLORS[i],
                "pts":           data["tier_pts"][i],
                "threshold":     data["thresholds"][i],
                "label":         data["criterion_labels"][i],
                "reached":       level >= tn,
                "current":       level == tn,
                "next":          tn == level + 1,
                "best_regressed": data["viva"] and best_level == tn and level < tn,
            })

        progress_text = data["metric_fmt"].replace("{v}", str(metric_val))

        modal_data = {
            "name":          data["name"],
            "description":   data["description"],
            "icon":          data["icon"],
            "viva":          data["viva"],
            "level":         level,
            "best_level":    best_level,
            "level_name":    TIER_NAMES[level - 1] if level > 0 else None,
            "level_color":   TIER_COLORS[level - 1] if level > 0 else None,
            "regressed":     regressed,
            "progress_text": progress_text,
            "journey":       journey,
        }

        result.append({
            "slug":           slug,
            "name":           data["name"],
            "icon":           data["icon"],
            "viva":           data["viva"],
            "level":          level,
            "level_name":     TIER_NAMES[level - 1] if level > 0 else None,
            "level_color":    TIER_COLORS[level - 1] if level > 0 else None,
            "best_level":     best_level,
            "best_level_name": TIER_NAMES[best_level - 1] if best_level > 0 else None,
            "points":         pts,
            "next_pts":       next_pts,
            "delta_pts":      delta_pts,
            "next_level_name": TIER_NAMES[level] if level < 4 else None,
            "earned":         level > 0,
            "at_max":         level == 4,
            "regressed":      regressed,
            "level_dots":     [i < level for i in range(4)],
            "modal_json":     json.dumps(modal_data, ensure_ascii=False),
        })
    return result


def compute_total_points(user):
    """Sum of tier_pts[current_level-1] across all earned achievements."""
    from apps.finances.models import UserAchievement
    total = 0
    for ua in UserAchievement.objects.filter(user=user):
        data = ACHIEVEMENTS.get(ua.slug)
        if data and ua.level > 0:
            total += data["tier_pts"][ua.level - 1]
    return total


def compute_streak(user):
    """Count consecutive months with financial activity (txs or fixos)."""
    from apps.finances.models import RecurringTransaction, Transaction
    today = date.today()
    streak = 0
    for months_back in range(1, 25):
        mo_start = _add_months_local(date(today.year, today.month, 1), -months_back)
        mo_end = _add_months_local(mo_start, 1)
        has_tx = Transaction.objects.filter(
            account__user=user, date__year=mo_start.year, date__month=mo_start.month,
            status=Transaction.STATUS_COMPLETED,
        ).exists()
        if not has_tx:
            has_fixo = RecurringTransaction.objects.filter(
                user=user, is_active=True, start_date__lt=mo_end,
            ).filter(Q(end_date__isnull=True) | Q(end_date__gte=mo_start)).exists()
            if not has_fixo:
                break
        streak += 1
    return streak


def compute_health_score(user):
    """
    Returns dict: score(0–100), label, color, breakdown list.

    Components (total 100 pts):
      setup         15pts  — has account + snapshot + fixo
      savings       25pts  — savings rate this month
      commitment    20pts  — fixos / total expense ratio
      goals         10pts  — avg progress toward active goals
      categories    10pts  — % of transactions with a category
      achievements  20pts  — total achievement points earned (up to ~2200)
    """
    from apps.finances.models import (
        Account, AccountMonthSnapshot, Goal, RecurringTransaction, Transaction,
    )
    today = date.today()
    year, month = today.year, today.month
    month_start = date(year, month, 1)
    next_month_start = date(year, month + 1, 1) if month < 12 else date(year + 1, 1, 1)

    # ── Setup (15pts) ─────────────────────────────────────────────────────────
    # Accounts (5pts): 1pt ≥1, 3pt ≥2, 5pt ≥4 (requires building a complete picture)
    active_acc_count = Account.objects.filter(user=user, is_active=True).count()
    account_pts = 5 if active_acc_count >= 4 else 3 if active_acc_count >= 2 else 1 if active_acc_count >= 1 else 0

    # Snapshots (5pts): require time — 4+ months AND 2+ accounts for full credit
    snap_months_n = AccountMonthSnapshot.objects.filter(account__user=user).values("month").distinct().count()
    snap_accs_n   = AccountMonthSnapshot.objects.filter(account__user=user).values("account_id").distinct().count()
    snapshot_pts = 5 if (snap_months_n >= 4 and snap_accs_n >= 2) else 3 if (snap_months_n >= 2 and snap_accs_n >= 2) else 2 if snap_months_n >= 2 else 1 if snap_months_n >= 1 else 0

    # Fixos (5pts): require richer mapping — 1pt any, 3pt 1inc+2exp, 5pt 2inc+4exp
    inc_fixo_n = RecurringTransaction.objects.filter(user=user, is_active=True, type=RecurringTransaction.TYPE_INCOME).count()
    exp_fixo_n = RecurringTransaction.objects.filter(user=user, is_active=True, type=RecurringTransaction.TYPE_EXPENSE).count()
    fixo_pts = 5 if (inc_fixo_n >= 2 and exp_fixo_n >= 4) else 3 if (inc_fixo_n >= 1 and exp_fixo_n >= 2) else 1 if (inc_fixo_n + exp_fixo_n) >= 1 else 0

    setup_pts = account_pts + snapshot_pts + fixo_pts

    # ── Savings rate (25pts) ──────────────────────────────────────────────────
    # Variable transactions are required to unlock the higher tiers;
    # fixos-only income produces a rate but caps the score at 10pts.
    inc_var = Transaction.objects.filter(
        account__user=user, date__year=year, date__month=month,
        type=Transaction.TYPE_CREDIT, is_transfer=False,
        status=Transaction.STATUS_COMPLETED,
    ).aggregate(t=Sum("amount"))["t"] or Decimal("0")
    exp_var = Transaction.objects.filter(
        account__user=user, date__year=year, date__month=month,
        type=Transaction.TYPE_DEBIT, is_transfer=False,
        status=Transaction.STATUS_COMPLETED,
    ).aggregate(t=Sum("amount"))["t"] or Decimal("0")
    fixos_cur = RecurringTransaction.objects.filter(
        user=user, is_active=True, start_date__lt=next_month_start,
    ).filter(Q(end_date__isnull=True) | Q(end_date__gte=month_start))
    inc_fix = sum(_amount_for_month_local(r, month_start) for r in fixos_cur.filter(type=RecurringTransaction.TYPE_INCOME))
    exp_fix = sum(_amount_for_month_local(r, month_start) for r in fixos_cur.filter(type=RecurringTransaction.TYPE_EXPENSE))
    inc = inc_var + inc_fix
    exp = exp_var + exp_fix
    has_var_txs = inc_var > 0 or exp_var > 0

    # How many distinct months (before the current one) had variable transactions
    var_tx_months_history = Transaction.objects.filter(
        account__user=user, is_transfer=False,
        status=Transaction.STATUS_COMPLETED,
    ).exclude(date__year=year, date__month=month).values("date__year", "date__month").distinct().count()

    if inc > 0:
        rate = float((inc - exp) / inc)
        raw_pts = 25 if rate >= 0.30 else 20 if rate >= 0.20 else 14 if rate >= 0.10 else 8 if rate >= 0 else 0
        if not has_var_txs:
            # Only fixo-based income — very limited signal
            savings_pts = min(raw_pts, 8)
        elif var_tx_months_history == 0:
            # First month recording real transactions — good start, not full credit yet
            savings_pts = min(raw_pts, 15)
        elif var_tx_months_history < 3:
            # Building track record — unlock most of the score
            savings_pts = min(raw_pts, 20)
        else:
            savings_pts = raw_pts
    else:
        savings_pts = 0

    # ── Commitment rate (20pts) ───────────────────────────────────────────────
    # Requires actual variable expense transactions to score beyond 5pts.
    # Without real spending data, the ratio is meaningless (all-fixos = 100% ratio).
    fixos_exp_qs = RecurringTransaction.objects.filter(
        user=user, is_active=True, start_date__lt=next_month_start,
        type=RecurringTransaction.TYPE_EXPENSE,
    ).filter(Q(end_date__isnull=True) | Q(end_date__gte=month_start))
    fixos_total = sum(_amount_for_month_local(r, month_start) for r in fixos_exp_qs)
    total_exp = exp + fixos_total

    # How many distinct past months had variable expense transactions
    var_exp_months_history = Transaction.objects.filter(
        account__user=user, type=Transaction.TYPE_DEBIT, is_transfer=False,
        status=Transaction.STATUS_COMPLETED,
    ).exclude(date__year=year, date__month=month).values("date__year", "date__month").distinct().count()

    if total_exp <= 0:
        commitment_pts = 0
    elif exp_var == 0:
        # No variable expenses yet — partial credit for having fixos documented
        commitment_pts = 3 if fixos_total > 0 else 0
    else:
        cr = float(fixos_total / total_exp)
        # Ideal range: 20–70% fixos (balanced predictability)
        if 0.20 <= cr <= 0.70:
            raw_comm = 20
        elif 0.10 <= cr < 0.20 or 0.70 < cr <= 0.80:
            raw_comm = 14
        elif 0 < cr < 0.10 or 0.80 < cr <= 0.90:
            raw_comm = 8
        elif cr > 0.90:
            raw_comm = 4  # too locked up in fixed commitments
        else:
            raw_comm = 0

        # Gate on historical consistency: ratio only means something with real data over time
        if var_exp_months_history == 0:
            commitment_pts = min(raw_comm, 10)
        elif var_exp_months_history < 3:
            commitment_pts = min(raw_comm, 15)
        else:
            commitment_pts = raw_comm

    # ── Goal progress (10pts) ─────────────────────────────────────────────────
    goals = Goal.objects.filter(user=user, is_completed=False)
    if goals.exists():
        avg = sum(
            min(float(g.current_amount / g.target_amount), 1.0)
            for g in goals if g.target_amount > 0
        ) / goals.count()
        goal_pts = int(avg * 10)
    else:
        goal_pts = 0

    # ── Categorization rate (10pts) ───────────────────────────────────────────
    month_txs = Transaction.objects.filter(
        account__user=user, date__year=year, date__month=month,
        status=Transaction.STATUS_COMPLETED, is_transfer=False,
    )
    total_txs = month_txs.count()
    cat_pts = int((month_txs.filter(category__isnull=False).count() / total_txs) * 10) if total_txs > 0 else 0

    # ── Achievements (20pts) ─────────────────────────────────────────────────
    # Every ~150 achievement points = 1 health point, capped at 20.
    total_ach = compute_total_points(user)
    ach_pts = min(20, int(total_ach / 150))

    score = min(max(setup_pts + savings_pts + commitment_pts + goal_pts + cat_pts + ach_pts, 0), 100)

    if score >= 80:
        label, color = "Excelente", "#00C97A"
    elif score >= 60:
        label, color = "Bom", "#2563EB"
    elif score >= 40:
        label, color = "Regular", "#F59E0B"
    else:
        label, color = "Atenção", "#EF4444"

    ring_offset = round(238.76 * (1 - score / 100), 1)

    return {
        "score":       score,
        "label":       label,
        "color":       color,
        "ring_color":  color,
        "ring_offset": ring_offset,
        "breakdown": [
            {"name": "Configuração",      "pts": setup_pts,      "max": 15},
            {"name": "Taxa de poupança",  "pts": savings_pts,    "max": 25},
            {"name": "Controle de fixos", "pts": commitment_pts, "max": 20},
            {"name": "Metas",             "pts": goal_pts,       "max": 10},
            {"name": "Categorização",     "pts": cat_pts,        "max": 10},
            {"name": "Conquistas",        "pts": ach_pts,        "max": 20},
        ],
    }


# ── Local helpers ─────────────────────────────────────────────────────────────

def _add_months_local(d, n):
    total = d.year * 12 + (d.month - 1) + n
    y, m = divmod(total, 12)
    return date(y, m + 1, 1)


def _amount_for_month_local(r, mo):
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

    if freq == RecurringTransaction.FREQ_MONTHLY:
        return r.amount

    period_map = {
        RecurringTransaction.FREQ_QUARTERLY:  3,
        RecurringTransaction.FREQ_SEMIANNUAL: 6,
        RecurringTransaction.FREQ_ANNUAL:     12,
    }
    period = period_map.get(freq)
    if period is None:
        return r.amount
    ref = r.start_date.replace(day=1)
    mo_offset = (mo.year - ref.year) * 12 + (mo.month - ref.month)
    return r.amount if mo_offset >= 0 and mo_offset % period == 0 else Decimal("0")
