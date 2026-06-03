from apps.dashboard.achievements import ACHIEVEMENTS, TIER_NAMES, TIER_COLORS


def _all_accounts_have_snapshot(user, Account, AccountMonthSnapshot):
    """True quando todas as contas patrimoniais ativas têm ao menos 2 snapshots.
    Exclui cartões de crédito (fatura ≠ patrimônio) e contas inativas."""
    from django.db.models import Count
    qs = Account.objects.filter(user=user, is_active=True).exclude(type="credit")
    total = qs.count()
    if total == 0:
        return True  # no active non-credit accounts → nothing to register, step is vacuously satisfied
    with_2_snaps = (
        qs.annotate(snap_count=Count("monthly_snapshots"))
        .filter(snap_count__gte=2)
        .count()
    )
    return with_2_snaps == total


def sol_state(request):
    """Flags para o assistente Sol detectar o que o usuário já completou."""
    if not request.user.is_authenticated:
        return {}
    from apps.finances.models import (
        Account, AccountMonthSnapshot, Goal, Investment, InvestmentTransaction,
        RecurringTransaction, Transaction,
    )
    user = request.user
    return {
        "sol_has_accounts":     Account.objects.filter(user=user, is_active=True).exists(),
        "sol_has_snapshots":    _all_accounts_have_snapshot(user, Account, AccountMonthSnapshot),
        "sol_has_transactions": Transaction.objects.filter(account__user=user, is_transfer=False).exists(),
        "sol_has_recurring":    RecurringTransaction.objects.filter(user=user, is_active=True).exists(),
        "sol_has_goals":        Goal.objects.filter(user=user).exists(),
        # Only true when the user has actually recorded a BUY boleta — orphaned Investment
        # objects without transaction history don't count as "connected" investments.
        "sol_has_investments":  InvestmentTransaction.objects.filter(
            user=user, type=InvestmentTransaction.TYPE_BUY
        ).exists(),
    }


def achievement_toasts(request):
    """Pop pending achievement notifications from session and resolve to toast data."""
    pending = request.session.pop("_achievements", [])
    if not pending:
        return {"achievement_toasts": []}

    toasts = []
    for item in pending:
        # item is {"slug": ..., "level": ...}
        slug  = item.get("slug") if isinstance(item, dict) else item
        level = item.get("level", 1) if isinstance(item, dict) else 1
        data  = ACHIEVEMENTS.get(slug)
        if not data:
            continue
        pts = data["tier_pts"][level - 1] if level > 0 else 0
        toasts.append({
            "slug":        slug,
            "name":        data["name"],
            "icon":        data["icon"],
            "level":       level,
            "level_name":  TIER_NAMES[level - 1] if level > 0 else "",
            "level_color": TIER_COLORS[level - 1] if level > 0 else "#64748B",
            "points":      pts,
        })
    return {"achievement_toasts": toasts}
