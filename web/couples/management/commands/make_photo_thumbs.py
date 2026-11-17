from django.conf import settings
from django.core.management.base import BaseCommand

from couples import quota
from couples.models import Couple, Photo
from couples.thumbs import attach_thumb


class Command(BaseCommand):
    help = (
        "작은 사진(320px)이 없는 사진의 원본을 하나씩 열어(R2 GET) 작은 사진을 만들어요. "
        "저장소 목록 조회(LIST)는 하지 않아요. 운영은 ENV_FILE=.env.neon 을 붙여요."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="만들지 않고 몇 장인지만 봐요.")
        parser.add_argument("--limit", type=int, default=0, help="이번에 만들 최대 장수 (0 = 모두)")

    def handle(self, *args, dry_run=False, limit=0, **options):
        from django.core.files.storage import default_storage
        from django.db.models import Q

        # 어느 저장소에 쓰는지 먼저 알려 준다 (운영 R2 가 아니면 원본을 못 찾아 모두 실패한다)
        self.stdout.write(f"저장소: {type(default_storage).__name__}")
        heic = Q(image__iendswith=".heic") | Q(image__iendswith=".heif")
        skipped = Photo.objects.filter(thumb="").filter(heic).count()
        if skipped:
            self.stdout.write(f"HEIC {skipped}장은 건너뛰어요 (서버가 열 수 없어요. 화면은 원본을 써요)")
        todo = Photo.objects.filter(thumb="").exclude(heic).order_by("pk")
        if limit:
            todo = todo[:limit]
        if dry_run:
            self.stdout.write(f"작은 사진이 없는 사진 {todo.count()}장")
            return
        made = failed = 0
        for photo in todo.iterator():
            if attach_thumb(photo):
                made += 1
            else:
                failed += 1
        self.stdout.write(f"만든 {made}장 · 못 만든 {failed}장")
        # 작은 사진도 용량에 들어가므로 커플별 사용량을 알려 준다 (한도를 넘으면 그 커플은 더 올릴 수 없다)
        for couple in Couple.objects.all():
            used = quota.used_bytes(couple)
            line = f"커플 {couple.pk}: {quota._size_text(used)} / {quota._size_text(settings.MEDIA_QUOTA_PER_COUPLE_BYTES)}"
            if quota.room_for(couple).couple_left < 0:
                line += " — 한도를 넘었어요"
            self.stdout.write(line)
