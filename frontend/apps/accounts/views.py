from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from apps.subscriptions.models import Plan, Subscription


@login_required
def plan_selection(request):
    """
    Hub pós-login. Decide para onde o usuário vai:
    1. Já tem assinatura → dashboard
    2. Tem plano pré-selecionado na sessão (veio do pricing) → cria assinatura → dashboard
    3. Sem assinatura e sem pré-seleção → mostra tela de escolha de plano
    """
    if hasattr(request.user, "subscription"):
        return redirect("dashboard")

    pre_selected = request.session.pop("selected_plan", None)
    if pre_selected:
        try:
            plan = Plan.objects.get(slug=pre_selected, is_active=True)
            Subscription.objects.create(user=request.user, plan=plan)
            return redirect("dashboard")
        except Plan.DoesNotExist:
            pass

    if request.method == "POST":
        plan_slug = request.POST.get("plan_slug", "")
        try:
            plan = Plan.objects.get(slug=plan_slug, is_active=True)
            Subscription.objects.create(user=request.user, plan=plan)
            return redirect("dashboard")
        except Plan.DoesNotExist:
            pass

    plans = Plan.objects.filter(is_active=True).order_by("price")
    return render(request, "onboarding/plan.html", {"plans": plans})


def start_with_plan(request):
    """
    Chamado quando o usuário clica em um plano na página de pricing pública.
    Salva o slug na sessão e redireciona ao cadastro/login.
    Se já estiver logado, manda direto ao plan_selection (que consome a sessão).
    """
    plan_slug = request.GET.get("plan", "")
    valid_slugs = list(Plan.objects.filter(is_active=True).values_list("slug", flat=True))
    if plan_slug in valid_slugs:
        request.session["selected_plan"] = plan_slug

    if request.user.is_authenticated:
        return redirect("onboarding_plan")
    return redirect("register")


@login_required
def cancel_registration(request):
    """
    Usuário desistiu de escolher um plano — deleta a conta e redireciona ao início.
    Só aceita POST para evitar cancelamentos acidentais por link.
    """
    if request.method == "POST":
        user = request.user
        logout(request)
        user.delete()
        return redirect("home")
    return redirect("onboarding_plan")
