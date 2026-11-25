from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView, TemplateView

from accounts import views as account_views
from notifications import views as notification_views

urlpatterns = [
    # 비밀번호 찾기는 메일을 보낼 수 없어 닫는다. 잊었으면 카카오·Google 로 이어 붙인 계정으로 (allauth 보다 먼저)
    path("accounts/password/reset/", RedirectView.as_view(pattern_name="account_login", permanent=False), name="account_reset_password"),
    # allauth 의 "로그인 취소" 화면 대신 안내 문구와 함께 로그인 화면으로 (allauth 보다 먼저 둔다)
    path("accounts/3rdparty/login/cancelled/", account_views.social_login_cancelled, name="socialaccount_login_cancelled"),
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
    path("memos/", include("memos.urls")),
    path("", include("couples.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.ADMIN_ENABLED:
    urlpatterns.insert(0, path("admin/", admin.site.urls))
