from django.shortcuts import redirect

_EXEMPT = ("/accounts/", "/onboarding/", "/admin/", "/static/", "/media/", "/pricing/")


class SubscriptionCheckMiddleware:
    """
    Usuários autenticados sem assinatura ativa não podem acessar o dashboard.
    São redirecionados para /onboarding/plan/ onde escolhem um plano.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and request.path.startswith("/dashboard/"):
            if not hasattr(request.user, "subscription"):
                return redirect("/onboarding/plan/")
        return self.get_response(request)
