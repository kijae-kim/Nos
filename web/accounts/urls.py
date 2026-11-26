from django.urls import path

from . import views

urlpatterns = [
    path("appearance/", views.appearance, name="appearance"),
    path("profile/", views.profile, name="profile"),
    path("avatar/<int:pk>.jpg", views.avatar, name="avatar"),
    path("guide/", views.guide, name="guide"),
    path("news/", views.news, name="news"),
    path("tutorial/done/", views.tutorial_done, name="tutorial_done"),
    path("news/seen/", views.news_seen, name="news_seen"),
]
