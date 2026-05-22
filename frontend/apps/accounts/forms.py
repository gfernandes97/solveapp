from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone


class LoginForm(AuthenticationForm):
    username = forms.EmailField(
        label="E-mail",
        widget=forms.EmailInput(attrs={"placeholder": "voce@email.com", "autocomplete": "email"}),
    )
    password = forms.CharField(
        label="Senha",
        widget=forms.PasswordInput(attrs={"placeholder": "••••••••"}),
    )


class RegisterForm(UserCreationForm):
    first_name = forms.CharField(
        label="Nome completo",
        widget=forms.TextInput(attrs={"placeholder": "Seu nome"}),
    )
    email = forms.EmailField(
        label="E-mail",
        widget=forms.EmailInput(attrs={"placeholder": "voce@email.com"}),
    )
    password1 = forms.CharField(
        label="Senha",
        widget=forms.PasswordInput(attrs={"placeholder": "Mínimo 8 caracteres"}),
    )
    password2 = forms.CharField(
        label="Confirmar senha",
        widget=forms.PasswordInput(attrs={"placeholder": "Repita a senha"}),
    )

    class Meta:
        model = User
        fields = ("first_name", "email", "password1", "password2")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data["email"]
        user.email = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["first_name"]
        if commit:
            user.save()
        return user


class LGPDSignupForm(forms.Form):
    """
    Formulário complementar ao signup do allauth (ACCOUNT_SIGNUP_FORM_CLASS).
    Adiciona checkbox de consentimento explícito exigido pelo Art. 8º da LGPD.
    O timestamp é gravado pelo sinal user_signed_up em signals.py.
    """

    lgpd_consent = forms.BooleanField(
        required=True,
        label="Li e aceito os Termos de Uso e a Política de Privacidade",
        error_messages={
            "required": "Você precisa aceitar os Termos de Uso e a Política de Privacidade para criar uma conta."
        },
    )

    def signup(self, request, user):
        pass


