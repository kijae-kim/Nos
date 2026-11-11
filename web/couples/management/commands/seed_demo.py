"""화면과 DB 테스트용 더미 데이터를 넣는다. 개발 환경에서만 쓴다.

    python manage.py seed_demo            # 더미 커플 하나 만들기
    python manage.py seed_demo --reset    # 이전 더미 데이터를 지우고 다시 만들기

계정은 demo1@local.test / demo2@local.test, 비밀번호는 DEMO_PASSWORD 와 같다.
사진은 색 그러데이션 이미지로 만들어 MEDIA_ROOT 에 저장된다.
"""

from datetime import date, time, timedelta
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw

from anniversaries.models import Anniversary
from couples import services
from couples.models import Album, Couple, Event, Photo, Taste

User = get_user_model()
DEMO_DOMAIN = "@local.test"
DEMO_PASSWORD = "demo-pass-1234"

# 일정: (며칠 뒤, 제목 글, 시작, 끝, 장소, 공개, 색)
EVENTS = [
    (-3, "성수 산책 @데이트 #성수", time(13, 0), time(15, 0), "성수동", "shared", "rose"),
    (0, "저녁 장보기 #집", None, None, "", "personal", "sand"),
    (2, "전시 보러 가기 @데이트 #성수", time(14, 0), time(16, 0), "성수 대림창고", "shared", "sky"),
    (5, "바다 회식 #회사", time(19, 0), None, "", "personal", "lav"),
    (9, "영화 예매 오픈 @같이", time(21, 30), None, "", "shared", "lav"),
    (14, "저녁 외식 @데이트 #연남", time(19, 30), time(21, 0), "연남동", "shared", "rose"),
    (17, "본가 방문 #가족", time(11, 0), None, "", "personal", "sky"),
]

# 취향: (작성자 순서, 분류, 제목, 링크, 한마디)
TASTES = [
    (0, "음악", "밤편지", "https://example.com/music/night-letter", "새벽에 들으면 진짜 좋아. 이번 주말에 같이 듣자"),
    (1, "영화", "헤어질 결심", "", "바다 장면 때문에 다시 보고 싶어졌어"),
    (1, "장소", "성수 대림창고", "", "전시 끝나고 같이 들르자. 1층 카페 좋아"),
    (0, "책", "작은 것들의 신", "", "같이 읽고 밤에 얘기해 보자"),
    (0, "영상", "여행 브이로그 모음", "https://example.com/video/trip", ""),
]

# 사진: (앨범 이름 또는 None, 찍은 날 오프셋, 한마디, 그러데이션 색 두 개)
PHOTOS = [
    ("성수동 산책", 0, "전시 앞에서", ((255, 154, 122), (255, 90, 95))),
    ("성수동 산책", 0, "카페 창가", ((143, 227, 236), (42, 69, 245))),
    ("성수동 산책", -2, "", ((196, 235, 203), (62, 155, 119))),
    ("제주 여행", -33, "오름 정상", ((255, 217, 120), (240, 150, 90))),
    ("제주 여행", -34, "바다가 보이는 숙소", ((187, 214, 238), (91, 143, 217))),
    (None, -60, "그냥 찍은 하늘", ((207, 203, 255), (109, 98, 184))),
    (None, -365, "1년 전 오늘", ((43, 42, 143), (20, 27, 61))),
]


def make_image(top, bottom, label):
    img = Image.new("RGB", (900, 900), top)
    draw = ImageDraw.Draw(img)
    for y in range(900):
        t = y / 899
        color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        draw.line([(0, y), (900, y)], fill=color)
    draw.ellipse([560, 140, 760, 340], fill=(255, 217, 120))
    draw.text((40, 40), label, fill=(255, 255, 255))
    buffer = BytesIO()
    img.save(buffer, "JPEG", quality=85)
    return buffer.getvalue()


class Command(BaseCommand):
    help = "화면과 DB 테스트용 더미 커플, 일정, 취향, 사진을 만든다."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="이전 더미 데이터를 지우고 다시 만든다.")

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reset"]:
            self.reset()
        elif User.objects.filter(email__endswith=DEMO_DOMAIN).exists():
            raise CommandError("이미 더미 데이터가 있어요. 다시 만들려면 --reset 을 붙이세요.")

        today = timezone.localdate()
        couple = Couple.objects.create(start_date=today - timedelta(days=464))
        first = User.objects.create_user(f"demo1{DEMO_DOMAIN}", f"demo1{DEMO_DOMAIN}", DEMO_PASSWORD, nickname="하늘", couple=couple)
        second = User.objects.create_user(f"demo2{DEMO_DOMAIN}", f"demo2{DEMO_DOMAIN}", DEMO_PASSWORD, nickname="바다", couple=couple)
        authors = [first, second]

        for offset, text, start, end, place, scope, color in EVENTS:
            services.save_event(
                Event(created_by=authors[offset % 2]),
                couple,
                {
                    "text": text,
                    "date": today + timedelta(days=offset),
                    "start_time": start,
                    "end_time": end,
                    "place": place,
                    "scope": scope,
                    "color": color,
                },
            )

        for author_index, category, title, link, comment in TASTES:
            Taste.objects.create(
                couple=couple, author=authors[author_index], category=category, title=title, link=link, comment=comment,
            )

        albums = {}
        for index, (album_title, offset, caption, (top, bottom)) in enumerate(PHOTOS):
            album = None
            if album_title:
                album, _ = Album.objects.get_or_create(couple=couple, title=album_title)
            photo = Photo(
                couple=couple,
                uploaded_by=authors[index % 2],
                album=album,
                caption=caption,
                taken_on=today + timedelta(days=offset),
            )
            photo.image.save(f"demo_{index}.jpg", ContentFile(make_image(top, bottom, album_title or "사진")), save=False)
            photo.save()

        Anniversary.objects.create(couple=couple, title="바다 생일", date=date(2000, 12, 25), repeat_yearly=True, created_by=first)
        Anniversary.objects.create(couple=couple, title="첫 여행", date=date(2025, 10, 3), created_by=second)

        self.stdout.write(self.style.SUCCESS(
            f"더미 데이터 생성: 계정 {first.email}, {second.email} (비밀번호 {DEMO_PASSWORD})"
        ))

    def reset(self):
        demo_users = User.objects.filter(email__endswith=DEMO_DOMAIN)
        couples = Couple.objects.filter(members__in=demo_users).distinct()
        for photo in Photo.objects.filter(couple__in=couples):
            photo.image.delete(save=False)
        Couple.objects.filter(pk__in=couples).delete()
        demo_users.delete()
        self.stdout.write("이전 더미 데이터를 지웠어요.")
