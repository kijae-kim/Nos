import hmac
from datetime import timedelta

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from couples.models import Couple

from .models import PushLog
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
            if PushLog.objects.filter(user=due.user, key=due.key).exists():
                skipped += 1
                continue
            payload = {"title": due.title, "body": due.body, "url": due.url, "tag": due.key}
            # 보내기에 성공한 것만 기록한다
            if send_to_user(due.user, payload):
                PushLog.objects.get_or_create(user=due.user, key=due.key, defaults={"sent_on": today})
                sent += 1
            else:
                failed += 1

    PushLog.objects.filter(sent_on__lt=today - timedelta(days=LOG_DAYS)).delete()
    return JsonResponse({"ok": True, "sent": sent, "skipped": skipped, "failed": failed})
