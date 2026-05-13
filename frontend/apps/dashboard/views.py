from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def overview(request):
    wallet = '<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z"/></svg>'
    up     = '<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"/></svg>'
    down   = '<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 17H5m0 0v-8m0 8l8-8 4 4 6-6"/></svg>'
    target = '<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>'
    cards = [
        {"label": "Saldo total",     "value": "R$ 0,00", "icon": wallet},
        {"label": "Receitas do mês", "value": "R$ 0,00", "icon": up},
        {"label": "Gastos do mês",   "value": "R$ 0,00", "icon": down},
        {"label": "Metas ativas",    "value": "0",        "icon": target},
    ]
    return render(request, "dashboard/overview.html", {"cards": cards, "skeleton": range(5)})


@login_required
def transactions(request):
    return render(request, "dashboard/transactions.html")


@login_required
def investments(request):
    return render(request, "dashboard/investments.html")


@login_required
def goals(request):
    return render(request, "dashboard/goals.html")


@login_required
def settings(request):
    return render(request, "dashboard/settings.html")
