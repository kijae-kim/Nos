from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("us/", views.us, name="us"),
    path("couple/connect/", views.connect, name="couple_connect"),
    path("couple/create/", views.create, name="couple_create"),
    path("couple/join/", views.join, name="couple_join"),
    path("couple/leave/", views.leave, name="couple_leave"),
    # 캘린더
    path("calendar/", views.calendar, name="calendar"),
    path("calendar/events/new/", views.event_create, name="event_create"),
    path("calendar/events/<int:pk>/", views.event_update, name="event_update"),
    path("calendar/events/<int:pk>/delete/", views.event_delete, name="event_delete"),
    path("calendar/subscribe/", views.calendar_subscribe, name="calendar_subscribe"),
    path("calendar/feed/<str:token>.ics", views.calendar_feed, name="calendar_feed"),
    # 취향
    path("tastes/", views.taste, name="tastes"),
    path("tastes/new/", views.taste_create, name="taste_create"),
    path("tastes/preview/", views.taste_link_preview, name="taste_link_preview"),
    path("tastes/places/search/", views.place_search, name="place_search"),
    path("tastes/places/data/", views.place_map_data, name="place_map_data"),
    path("tastes/regions/data/", views.region_data, name="region_data"),
    path("tastes/regions/mark/", views.region_mark, name="region_mark"),
    path("tastes/places/photo-choices/", views.place_photo_choices, name="place_photo_choices"),
    path("tastes/<int:pk>/", views.taste_detail, name="taste_detail"),
    path("tastes/<int:pk>/edit/", views.taste_update, name="taste_update"),
    path("tastes/<int:pk>/photos/", views.place_photos_edit, name="place_photos_edit"),
    path("tastes/<int:pk>/delete/", views.taste_delete, name="taste_delete"),
    path("tastes/<int:pk>/like/", views.taste_like, name="taste_like"),
    path("tastes/<int:pk>/comments/", views.taste_comment_create, name="taste_comment_create"),
    path("tastes/comments/<int:pk>/delete/", views.taste_comment_delete, name="taste_comment_delete"),
    # 앨범
    path("albums/", views.album, name="albums"),
    path("albums/<int:pk>/", views.album_detail, name="album_detail"),
    path("albums/<int:pk>/delete/", views.album_delete, name="album_delete"),
    path("albums/photos/new/", views.photo_create, name="photo_create"),
    path("albums/photos/<int:pk>/", views.photo_detail, name="photo_detail"),
    path("albums/photos/<int:pk>/edit/", views.photo_update, name="photo_update"),
    path("albums/photos/<int:pk>/delete/", views.photo_delete, name="photo_delete"),
]
