from django.contrib import admin

from .models import Anniversary


@admin.register(Anniversary)
class AnniversaryAdmin(admin.ModelAdmin):
    list_display = ("title", "date", "repeat_yearly", "couple")
