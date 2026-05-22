from django import forms
from allauth.socialaccount.forms import SignupForm as SocialSignupForm


class SocialLGPDSignupForm(SocialSignupForm):
    """
    Substitui o formulário de confirmação do allauth para social accounts
    (SOCIALACCOUNT_FORMS = {'signup': ...}).
    Isolado de forms.py para evitar circular import com ACCOUNT_SIGNUP_FORM_CLASS.
    O timestamp de consentimento é gravado pelo sinal user_signed_up em signals.py.
    """

    lgpd_consent = forms.BooleanField(
        required=True,
        label="Li e aceito os Termos de Uso e a Política de Privacidade",
        error_messages={
            "required": "Você precisa aceitar os Termos de Uso e a Política de Privacidade para criar uma conta."
        },
    )
