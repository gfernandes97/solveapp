from django.urls import path

from . import views

urlpatterns = [
    path("plan/", views.plan_selection, name="onboarding_plan"),
    path("start/", views.start_with_plan, name="onboarding_start"),
    path("cancel/", views.cancel_registration, name="onboarding_cancel"),
]
