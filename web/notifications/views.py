import hmac
import json
from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from couples.models import Couple

from .models import PushLog, PushSubscription
from .push import send_to_user
from .schedule import due_for_couple

LOG_DAYS = 60  # 보낸 기록을 남겨 두는 기간


def _cron_authorized(request):
    secret = settings.CRON_SECRET
    if not secret:
        return False
    given = request.headers.get("Authorization", "")
    return hmac.compare_digest(given.encode(), f"Bearer {secret}".encode())


@require_GET
def cron_anniversaries(request):
    """Vercel Cron 이 하루 한 번(UTC 00시 = 한국 9시대) 부른다. 오늘 보낼 기념일 알림을 보낸다."""
    if not _cron_authorized(request):
        return JsonResponse({"ok": False}, status=401)
    if not settings.WEBPUSH_ENABLED:
        return JsonResponse({"ok": False, "reason": "vapid"}, status=503)

    today = timezone.localdate()
    sent = skipped = failed = 0
    couples = Couple.objects.filter(members__isnull=False).distinct().prefetch_related("members", "anniversaries")
    for couple in couples:
        for due in due_for_couple(couple, today):
            # 보내기 전에 기록 자리를 먼저 잡는다. Cron 이 거의 동시에 두 번 와도 한쪽만 보낸다 (unique 제약).
            try:
                with transaction.atomic():
                    log, created = PushLog.objects.get_or_create(
                        user=due.user, key=due.key, defaults={"sent_on": today}
                    )
            except IntegrityError:
                created = False
            if not created:
                skipped += 1
                continue
            payload = {"title": due.title, "body": due.body, "url": due.url, "tag": due.key}
            if send_to_user(due.user, payload):
                sent += 1
            else:
                # 보내기에 실패하면 기록을 지운다. 성공한 것만 남긴다.
                log.delete()
                failed += 1

    PushLog.objects.filter(sent_on__lt=today - timedelta(days=LOG_DAYS)).delete()
    return JsonResponse({"ok": True, "sent": sent, "skipped": skipped, "failed": failed})


# ---------- 우리 › 알림 ----------

TEST_PAYLOAD = {
    "title": "알림이 잘 와요",
    "body": "기념일이 다가오면 이렇게 알려 드릴게요",
    "url": "/anniversaries/",
    "tag": "test",
}


def webpush_required(view):
    """열쇠(VAPID)가 없는 서버에서는 알림 화면과 주소를 없는 것처럼 둔다."""

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not settings.WEBPUSH_ENABLED:
            raise Http404
        return view(request, *args, **kwargs)

    return wrapped


def _json_body(request):
    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


@webpush_required
@login_required
def notification_settings(request):
    user = request.user
    if request.method == "POST":
        user.notify_day_before = request.POST.get("notify_day_before") == "on"
        user.notify_week_before = request.POST.get("notify_week_before") == "on"
        user.save(update_fields=["notify_day_before", "notify_week_before"])
        messages.success(request, "알림 설정을 저장했어요.")
        return redirect("notifications")
    return render(request, "notifications/settings.html", {"VAPID_PUBLIC_KEY": settings.VAPID_PUBLIC_KEY})


@webpush_required
@login_required
@require_POST
def push_subscribe(request):
    """이 기기의 구독 정보를 저장한다. 같은 기기를 다른 사람이 쓰면 주인을 바꾼다."""
    data = _json_body(request) or {}
    endpoint = data.get("endpoint")
    keys = data.get("keys") if isinstance(data.get("keys"), dict) else {}
    p256dh, auth = keys.get("p256dh"), keys.get("auth")
    valid = (
        isinstance(endpoint, str)
        and endpoint.startswith("https://")
        and len(endpoint) <= 500
        and isinstance(p256dh, str) and 0 < len(p256dh) <= 200
        and isinstance(auth, str) and 0 < len(auth) <= 100
    )
    if not valid:
        return JsonResponse({"ok": False}, status=400)
    PushSubscription.objects.update_or_create(
        endpoint=endpoint, defaults={"user": request.user, "p256dh": p256dh, "auth": auth}
    )
    return JsonResponse({"ok": True})


@webpush_required
@login_required
@require_POST
def push_unsubscribe(request):
    data = _json_body(request) or {}
    endpoint = data.get("endpoint")
    if isinstance(endpoint, str):
        request.user.push_subscriptions.filter(endpoint=endpoint).delete()
    return JsonResponse({"ok": True})


@webpush_required
@login_required
@require_POST
def push_test(request):
    return JsonResponse({"ok": True, "sent": send_to_user(request.user, TEST_PAYLOAD)})
