import django, os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.finances.models import UserAchievement
from apps.dashboard.achievements import ACHIEVEMENTS, _compute_metric, _tlevel
from django.contrib.auth import get_user_model

User = get_user_model()
user = User.objects.get(username="gustavo")
uas = {ua.slug: ua for ua in UserAchievement.objects.filter(user=user)}

total = 0
print(f"{'Conquista':<28} {'Nível':>8} {'Métrica':>10} {'Pts':>6}  Obs")
print("-" * 70)
for slug, data in ACHIEVEMENTS.items():
    ua = uas.get(slug)
    level = ua.level if ua else 0
    best  = ua.best_level if ua else 0
    metric = _compute_metric(slug, user)
    pts = data["tier_pts"][level - 1] if level > 0 else 0
    total += pts
    tier = ["", "Bronze", "Prata", "Ouro", "Platina"][level]
    obs = ""
    if data["viva"] and best > level:
        obs = f"viva regrediu (best={best})"
    elif not data["viva"] and level > 0:
        live = _tlevel(metric, data["thresholds"])
        if live < level:
            obs = f"marco preservado (live={live})"
    print(f"{data['name']:<28} {tier:>8} {metric:>10} {pts:>6}  {obs}")

print("-" * 70)
print(f"{'TOTAL':<28} {'':>8} {'':>10} {total:>6}")
