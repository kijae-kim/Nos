"""메모 탭: 폴더 칩과 메모 목록. 아래 바의 '메모' (2026-11-25, 추억의 메모 칩에서 옮김)."""

from datetime import timedelta
from urllib.parse import urlencode

from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone

from .lines import ensure_default_folders, ordered_folders
from .models import Memo

MEMO_CATEGORY = "메모"
EMPTY_MEMO_AGE = timedelta(hours=1)


def board_url(folder_id=None):
    """메모 탭 주소 (폴더를 고르면 그 폴더)."""
    url = reverse("memos")
    return f"{url}?{urlencode({'folder': folder_id})}" if folder_id else url


def board(request, folder_id):
    """폴더 칩(메모 수)과 메모 목록(최근 고친 순). 빈 메모는 숨기고, 1시간 넘게 빈 채인 것만 지운다
    (상대가 방금 열어 아직 쓰는 중인 새 메모를 지우지 않게)."""
    couple = request.user.couple
    ensure_default_folders(couple)
    folders = list(ordered_folders(couple.memo_folders.annotate(count=Count("memos", filter=~Q(memos__title="")))))
    current = next((f for f in folders if str(f.pk) == str(folder_id)), None)
    memos = Memo.objects.filter(couple=couple).select_related("folder", "updated_by")
    if current:
        memos = memos.filter(folder=current)
        request.session["memo_folder"] = current.pk  # + 가 이 폴더에 새 메모를 연다
    items = list(memos)
    stale = timezone.now() - EMPTY_MEMO_AGE
    old_empty = [m.pk for m in items if m.is_empty and m.updated_at < stale]
    if old_empty:
        Memo.objects.filter(pk__in=old_empty).delete()
    return {"memo_folders": folders, "memo_folder": current, "memo_items": [m for m in items if not m.is_empty]}
