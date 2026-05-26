from apps.dashboard.achievements import ACHIEVEMENTS


def achievement_toasts(request):
    """Pop pending achievement slugs from session and resolve to full data for toast display."""
    slugs = request.session.pop("_achievements", [])
    if not slugs:
        return {"achievement_toasts": []}
    toasts = [ACHIEVEMENTS[s] | {"slug": s} for s in slugs if s in ACHIEVEMENTS]
    return {"achievement_toasts": toasts}
