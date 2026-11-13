from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

from notifications import views as notification_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path(
        "manifest.webmanifest",
        TemplateView.as_view(template_name="manifest.webmanifest", content_type="application/manifest+json"),
        name="manifest",
    ),
    path(
        "sw.js",
        TemplateView.as_view(template_name="sw.js", content_type="application/javascript"),
        name="service_worker",
    ),
    path("me/notifications/", include("notifications.urls")),
    path("me/", include("accounts.urls")),
    path("cron/anniversaries/", notification_views.cron_anniversaries, name="cron_anniversaries"),
    path("anniversaries/", include("anniversaries.urls")),
    path("", include("couples.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
