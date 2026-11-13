from django.contrib import admin

from .models import PushLog, PushSubscription

admin.site.register(PushSubscription)
admin.site.register(PushLog)
