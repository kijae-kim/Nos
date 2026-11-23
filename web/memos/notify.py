"""메모를 고치고 쓰기 화면을 떠나면 상대에게 웹 푸시 (같은 메모는 30분에 한 번)."""

import logging
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from notifications.push import send_to_user

logger = logging.getLogger(__name__)

GAP = timedelta(minutes=30)


def notify_partner(memo, editor) -> bool:
    """보냈으면 True. 내가 마지막으로 고친 글 있는 메모만, 상대가 메모 알림을 켰을 때만."""
    partner = editor.partner
    if not partner or not partner.notify_memo or memo.updated_by_id != editor.pk or not memo.title:
        return False
    now = timezone.now()
    if memo.notified_at and now - memo.notified_at < GAP:
        return False
    # 먼저 시각을 적어 두어 두 요청이 겹쳐도 한 번만 보낸다
    type(memo).objects.filter(pk=memo.pk).update(notified_at=now)
    payload = {
        "title": f"{editor.display_name}님이 메모를 고쳤어요",
        "body": f"{memo.folder.name} · {memo.title}",
        "url": reverse("memo_edit", args=[memo.pk]),
        "tag": f"memo-{memo.pk}",
    }
    try:
        return bool(send_to_user(partner, payload))
    except Exception:  # 알림 실패가 메모 쓰기를 막으면 안 된다
        logger.exception("메모 알림 보내기 실패")
        return False
