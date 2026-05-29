from apps.dashboard.achievements import ACHIEVEMENTS, TIER_NAMES, TIER_COLORS


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
