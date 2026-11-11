from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("us/", views.us, name="us"),
    path("couple/connect/", views.connect, name="couple_connect"),
    path("couple/create/", views.create, name="couple_create"),
    path("couple/join/", views.join, name="couple_join"),
    path("couple/leave/", views.leave, name="couple_leave"),
    # 아직 만들지 않은 탭
    path("calendar/", views.coming_soon, {"title": "캘린더"}, name="calendar"),
    path("tastes/", views.coming_soon, {"title": "취향"}, name="tastes"),
    path("albums/", views.coming_soon, {"title": "앨범"}, name="albums"),
]
