from django.urls import path

from . import views

urlpatterns = [
    path("appearance/", views.appearance, name="appearance"),
    path("profile/", views.profile, name="profile"),
    path("avatar/<int:pk>.jpg", views.avatar, name="avatar"),
]
