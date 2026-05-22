from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("pricing/", views.pricing, name="pricing"),
    path("privacidade/", views.privacy, name="privacy"),
    path("termos/", views.terms, name="terms"),
]
