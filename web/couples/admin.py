from django.contrib import admin

from .models import Couple


@admin.register(Couple)
class CoupleAdmin(admin.ModelAdmin):
    list_display = ("__str__", "invite_code", "start_date", "created_at")
    readonly_fields = ("invite_code",)
