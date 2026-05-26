from django.contrib import admin
from django.contrib.auth.models import User
from auditlog.registry import auditlog

from .models import UserProfile

auditlog.register(User, serialize_data=True)
auditlog.register(UserProfile, serialize_data=True)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "onboarding_step", "onboarding_completed", "phone", "created_at")
    list_filter = ("onboarding_completed", "onboarding_step")
    search_fields = ("user__email",)
    raw_id_fields = ("user",)
