import json
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.finances.models import (
    Account,
    AccountMonthSnapshot,
    Category,
    Goal,
    Investment,
    RecurringTransaction,
    Transaction,
)
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


# ─── LGPD: Exportação de dados ────────────────────────────────────────────────

@login_required
def data_export(request):
    """
    LGPD Art. 18 — Direito à portabilidade.
    Gera um JSON com todos os dados pessoais e financeiros do usuário.
    """
    user = request.user

    def _dec(v):
        return str(v) if v is not None else None

    payload = {
        "exportado_em": timezone.now().isoformat(),
        "versao": "1.0",
        "titular": {
            "id": user.pk,
            "email": user.email,
            "primeiro_nome": user.first_name,
            "ultimo_nome": user.last_name,
            "membro_desde": user.date_joined.isoformat(),
            "ultimo_acesso": user.last_login.isoformat() if user.last_login else None,
        },
        "contas": [
            {
                "id": a.pk,
                "nome": a.name,
                "tipo": a.type,
                "banco": a.bank_name,
                "moeda": a.currency,
                "incluir_no_total": a.include_in_total,
                "ativa": a.is_active,
                "criada_em": a.created_at.isoformat(),
            }
            for a in Account.objects.filter(user=user)
        ],
        "lancamentos": [
            {
                "id": t.pk,
                "conta": t.account.name if t.account else None,
                "tipo": t.type,
                "valor": _dec(t.amount),
                "data": t.date.isoformat(),
                "descricao": t.description,
                "categoria": t.category.name if t.category else None,
                "status": t.status,
                "recorrente": t.is_recurring,
                "transferencia": t.is_transfer,
                "notas": t.notes,
                "criado_em": t.created_at.isoformat(),
            }
            for t in Transaction.objects.filter(account__user=user).select_related("account", "category").order_by("date")
        ],
        "lancamentos_fixos": [
            {
                "id": r.pk,
                "nome": r.name,
                "tipo": r.type,
                "valor": _dec(r.amount),
                "frequencia": r.frequency,
                "inicio": r.start_date.isoformat(),
                "fim": r.end_date.isoformat() if r.end_date else None,
                "conta": r.account.name if r.account else None,
                "categoria": r.category.name if r.category else None,
                "ativo": r.is_active,
            }
            for r in RecurringTransaction.objects.filter(user=user).select_related("account", "category")
        ],
        "metas": [
            {
                "id": g.pk,
                "nome": g.name,
                "descricao": g.description,
                "valor_alvo": _dec(g.target_amount),
                "valor_atual": _dec(g.current_amount),
                "prazo": g.deadline.isoformat() if g.deadline else None,
                "concluida": g.is_completed,
                "criada_em": g.created_at.isoformat(),
            }
            for g in Goal.objects.filter(user=user)
        ],
        "investimentos": [
            {
                "id": i.pk,
                "nome": i.name,
                "ticker": i.ticker,
                "tipo": i.type,
                "quantidade": _dec(i.quantity),
                "preco_compra": _dec(i.purchase_price),
                "preco_atual": _dec(i.current_price),
                "data_compra": i.purchase_date.isoformat() if i.purchase_date else None,
            }
            for i in Investment.objects.filter(user=user)
        ],
        "historico_saldos": [
            {
                "conta": s.account.name,
                "mes": s.month.isoformat(),
                "saldo": _dec(s.balance),
                "notas": s.notes,
            }
            for s in AccountMonthSnapshot.objects.filter(account__user=user).select_related("account").order_by("month")
        ],
    }

    response = HttpResponse(
        json.dumps(payload, ensure_ascii=False, indent=2),
        content_type="application/json; charset=utf-8",
    )
    response["Content-Disposition"] = f'attachment; filename="solve_dados_{user.pk}.json"'
    return response


# ─── LGPD: Exclusão de conta com grace period ─────────────────────────────────

@login_required
@require_POST
def delete_account_request(request):
    """
    LGPD Art. 18 — Direito à eliminação.
    Agenda a exclusão da conta em 30 dias. O usuário pode cancelar antes do prazo.
    """
    profile = request.user.profile
    if not profile.pending_deletion:
        profile.pending_deletion = True
        profile.deletion_scheduled_at = timezone.now() + timedelta(days=30)
        profile.save(update_fields=["pending_deletion", "deletion_scheduled_at"])
        messages.success(
            request,
            "Sua conta está agendada para exclusão em 30 dias. "
            "Você pode cancelar a solicitação a qualquer momento antes desse prazo.",
        )
    return redirect("settings")


@login_required
@require_POST
def cancel_deletion_request(request):
    """Cancela um pedido de exclusão ativo."""
    profile = request.user.profile
    if profile.pending_deletion:
        profile.pending_deletion = False
        profile.deletion_scheduled_at = None
        profile.save(update_fields=["pending_deletion", "deletion_scheduled_at"])
        messages.success(request, "Solicitação de exclusão cancelada. Sua conta está ativa.")
    return redirect("settings")
