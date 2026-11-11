from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

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
    path("anniversaries/", include("anniversaries.urls")),
    path("", include("couples.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
