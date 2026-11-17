"""사진 저장소(R2) 무료 한도를 넘지 않게 막는다.

R2 는 무료 한도(저장 10GB, 쓰기 100만 회/월)를 넘으면 등록한 카드로 청구된다. 지출 상한 설정이 없으므로
앱이 미리 멈춘다. 쓴 용량은 R2 에 묻지 않고(목록 조회도 유료 작업이다) DB 에 적어 둔 파일 크기를 더해 계산한다.
한도는 환경 변수로 바꿀 수 있다 (config/settings.py).
"""
from dataclasses import dataclass

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

GB = 1024 ** 3


def _sum(queryset, field):
    return queryset.aggregate(total=Sum(field))["total"] or 0


def used_bytes(couple=None):
    """올린 사진(작은 사진 포함)과 취향 이미지의 크기 합. couple 을 주면 그 커플 것만."""
    from .models import Photo, Taste

    photos, tastes = Photo.objects.all(), Taste.objects.all()
    if couple is not None:
        photos, tastes = photos.filter(couple=couple), tastes.filter(couple=couple)
    return _sum(photos, "size") + _sum(photos, "thumb_size") + _sum(tastes, "image_size")


def uploads_today(couple):
    """오늘 이 커플이 올린 파일 수 (사진 + 이미지가 있는 취향)."""
    from .models import Photo, Taste

    today = timezone.localdate()
    return (
        Photo.objects.filter(couple=couple, created_at__date=today).count()
        + Taste.objects.filter(couple=couple, created_at__date=today).exclude(image="").exclude(image__isnull=True).count()
    )


def _size_text(n):
    return f"{n / GB:.1f}GB" if n >= GB / 10 else f"{n / 1024 / 1024:.0f}MB"


@dataclass
class Room:
    """올릴 수 있는 남은 양. 화면에 보여 주고, 올릴 때 검사한다."""

    couple_left: int
    total_left: int
    uploads_left: int

    @property
    def bytes_left(self):
        return max(0, min(self.couple_left, self.total_left))

    @property
    def bytes_left_text(self):
        return _size_text(self.bytes_left)


def room_for(couple):
    return Room(
        couple_left=settings.MEDIA_QUOTA_PER_COUPLE_BYTES - used_bytes(couple),
        total_left=settings.MEDIA_QUOTA_TOTAL_BYTES - used_bytes(),
        uploads_left=max(0, settings.MEDIA_UPLOADS_PER_DAY - uploads_today(couple)),
    )


def problem(couple, new_bytes, old_bytes=0):
    """새 파일을 받아도 되면 None, 안 되면 사용자에게 보여 줄 이유."""
    room = room_for(couple)
    if room.uploads_left <= 0:
        return f"오늘은 {settings.MEDIA_UPLOADS_PER_DAY}장까지 올릴 수 있어요. 내일 다시 올려 주세요."
    growth = new_bytes - old_bytes
    if growth > room.couple_left:
        return f"우리 공간의 사진 저장 공간({_size_text(settings.MEDIA_QUOTA_PER_COUPLE_BYTES)})이 가득 찼어요. 안 쓰는 사진을 지우면 다시 올릴 수 있어요."
    if growth > room.total_left:
        return "앱 전체의 사진 저장 공간이 가득 찼어요. 관리자에게 알려 주세요."
    return None
