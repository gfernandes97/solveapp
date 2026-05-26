from django.contrib import messages
from django.shortcuts import redirect

_DASHBOARD_PREFIX = "/dashboard/"
_SETTINGS_URL = "/dashboard/settings/"


class SubscriptionCheckMiddleware:
    """
    Bloqueia acesso ao dashboard em dois casos:
    1. Usuário sem assinatura ativa → /onboarding/plan/
    2. Usuário com exclusão agendada → /dashboard/settings/ (pode cancelar lá)
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and request.path.startswith(_DASHBOARD_PREFIX):
            # Bloqueia usuários sem assinatura
            if not hasattr(request.user, "subscription"):
                return redirect("/onboarding/plan/")

            # Bloqueia usuários com exclusão agendada (exceto a própria tela de configurações)
            profile = getattr(request.user, "profile", None)
            if (
                profile
                and profile.pending_deletion
                and not request.path.startswith(_SETTINGS_URL)
            ):
                messages.warning(
                    request,
                    "Sua conta está com exclusão agendada. "
                    "Cancele a solicitação para voltar a usar o Solve.",
                )
                return redirect(_SETTINGS_URL)

        return self.get_response(request)
