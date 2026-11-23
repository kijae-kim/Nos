from django.urls import path

from . import views

urlpatterns = [
    path("", views.memos, name="memos"),
    path("folders/new/", views.folder_create, name="memo_folder_create"),
    path("folders/<int:pk>/edit/", views.folder_update, name="memo_folder_update"),
    path("folders/<int:pk>/delete/", views.folder_delete, name="memo_folder_delete"),
    path("f/<int:pk>/", views.folder, name="memo_folder"),
    path("new/", views.memo_new, name="memo_new"),
    path("<int:pk>/", views.memo_edit, name="memo_edit"),
    path("<int:pk>/save/", views.memo_save, name="memo_save"),
    path("<int:pk>/notify/", views.memo_notify, name="memo_notify"),
    path("<int:pk>/move/", views.memo_move, name="memo_move"),
    path("<int:pk>/delete/", views.memo_delete, name="memo_delete"),
]
