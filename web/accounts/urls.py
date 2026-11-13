from django.urls import path

from . import views

urlpatterns = [
    path("appearance/", views.appearance, name="appearance"),
]
