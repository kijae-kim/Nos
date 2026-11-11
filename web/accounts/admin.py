from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "email", "nickname", "couple", "is_staff")
    fieldsets = UserAdmin.fieldsets + (("커플", {"fields": ("nickname", "couple")}),)
