from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="anniversary_index"),
    path("new/", views.create, name="anniversary_create"),
    path("<int:pk>/", views.update, name="anniversary_update"),
    path("<int:pk>/delete/", views.delete, name="anniversary_delete"),
]
