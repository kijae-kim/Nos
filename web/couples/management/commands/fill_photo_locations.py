from django.core.management.base import BaseCommand

from couples.geo import gps_from_image
from couples.models import Photo
from couples.places import link_photo


class Command(BaseCommand):
    help = (
        "위치가 비어 있는 사진의 저장 파일을 하나씩 열어 촬영 위치를 채워요. "
        "줄여서 저장된 사진은 위치가 이미 지워져 건너뛰어요. 저장소 목록 조회(LIST)는 하지 않아요."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="저장하지 않고 몇 장 채워질지만 봐요.")

    def handle(self, *args, dry_run=False, **options):
        found = checked = 0
        for photo in Photo.objects.filter(latitude__isnull=True).order_by("pk").iterator():
            checked += 1
            try:
                with photo.image.open("rb") as f:
                    coords = gps_from_image(f)
            except Exception:  # 저장소에 파일이 없거나 열 수 없는 사진 (R2 는 boto 오류로 온다)
                continue
            if not coords:
                continue
            found += 1
            if not dry_run:
                photo.latitude, photo.longitude = coords
                photo.save(update_fields=["latitude", "longitude"])
                link_photo(photo)  # 위치가 생겼으니 가까운 장소에 잇는다
        prefix = "(시험) " if dry_run else ""
        self.stdout.write(f"{prefix}위치를 찾은 사진 {found}장 / 살펴본 사진 {checked}장")
