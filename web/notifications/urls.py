from django.urls import path

from . import views

urlpatterns = [
    path("", views.notification_settings, name="notifications"),
    path("subscribe/", views.push_subscribe, name="push_subscribe"),
    path("unsubscribe/", views.push_unsubscribe, name="push_unsubscribe"),
    path("test/", views.push_test, name="push_test"),
]
