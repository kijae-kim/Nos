import secrets

from django.db import models

from .storage import photo_upload_to, taste_upload_to
from django.utils import timezone

# 헷갈리는 글자(0/O, 1/I)를 뺀 초대 코드용 문자
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 6


def generate_invite_code():
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


class Couple(models.Model):
    MAX_MEMBERS = 2

    invite_code = models.CharField(max_length=CODE_LENGTH, unique=True, default=generate_invite_code, editable=False)
    start_date = models.DateField("사귀기 시작한 날", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        names = " ♥ ".join(m.display_name for m in self.members.all())
        return names or f"Couple {self.pk}"

    @property
    def is_full(self):
        return self.members.count() >= self.MAX_MEMBERS

    @property
    def days_together(self):
        """사귄 날을 1일째로 세는 D+day. 시작일이 없거나 미래면 None."""
        if not self.start_date:
            return None
        days = (timezone.localdate() - self.start_date).days + 1
        return days if days >= 1 else None


# 일정 색과 이름표 색에 함께 쓰는 팔레트 이름 (CSS 토큰 이름과 같다)
COLOR_CHOICES = [
    ("sky", "하늘"),
    ("rose", "장미"),
    ("sand", "모래"),
    ("lav", "라벤더"),
    ("sage", "세이지"),
    ("peach", "복숭아"),
    ("coral", "코랄"),
    ("blue", "파랑"),
    ("mint", "민트"),
    ("lime", "라임"),
    ("mauve", "모브"),
    ("stone", "돌"),
]


class Label(models.Model):
    """@카테고리와 #태그. 일정을 만들 때 쓰면 그때 만들어진다."""

    CATEGORY = "category"
    TAG = "tag"
    KIND_CHOICES = [(CATEGORY, "카테고리"), (TAG, "태그")]

    couple = models.ForeignKey(Couple, on_delete=models.CASCADE, related_name="labels")
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    name = models.CharField(max_length=20)
    color = models.CharField(max_length=10, choices=COLOR_CHOICES, default="sky")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["couple", "kind", "name"], name="unique_label_per_couple")]
        ordering = ["kind", "name"]

    def __str__(self):
        prefix = "@" if self.kind == self.CATEGORY else "#"
        return f"{prefix}{self.name}"

    @property
    def token(self):
        return str(self)


class EventQuerySet(models.QuerySet):
    def visible_to(self, user):
        """우리 커플의 모든 일정. 개인 일정도 두 사람 모두 본다 (서로의 일정을 파악하려는 캘린더, 2026-11-25).
        '개인' 은 함께 하는 일정이 아니라 한 사람의 일정이라는 뜻이다. 다른 커플 것은 보이지 않는다."""
        if not user.couple_id:
            return self.none()
        return self.filter(couple=user.couple_id)

    def overlapping(self, start, end):
        """[start, end] 기간에 하루라도 걸치는 일정 (여러 날 일정 포함)."""
        return self.filter(date__lte=end).filter(
            models.Q(end_date__gte=start) | models.Q(end_date__isnull=True, date__gte=start)
        )

    def not_past(self, today):
        """끝나는 날이 today 이후인 일정 (진행 중인 여러 날 일정 포함)."""
        return self.filter(models.Q(end_date__gte=today) | models.Q(end_date__isnull=True, date__gte=today))


class Event(models.Model):
    SHARED = "shared"
    PERSONAL = "personal"
    SCOPE_CHOICES = [(SHARED, "공통"), (PERSONAL, "개인")]

    couple = models.ForeignKey(Couple, on_delete=models.CASCADE, related_name="events")
    created_by = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="events")
    scope = models.CharField(max_length=10, choices=SCOPE_CHOICES, default=SHARED)
    title = models.CharField("일정", max_length=100)
    date = models.DateField("날짜")
    # 여러 날 일정의 끝나는 날 (하루 종일만). 하루 일정은 비운다
    end_date = models.DateField("끝나는 날", null=True, blank=True)
    start_time = models.TimeField("시작", null=True, blank=True)
    end_time = models.TimeField("끝", null=True, blank=True)
    place = models.CharField("장소", max_length=100, blank=True)
    memo = models.TextField("메모", blank=True)
    color = models.CharField(max_length=10, choices=COLOR_CHOICES, default="sky")
    labels = models.ManyToManyField(Label, blank=True, related_name="events")
    created_at = models.DateTimeField(auto_now_add=True)

    objects = EventQuerySet.as_manager()

    class Meta:
        ordering = ["date", "start_time", "pk"]

    def __str__(self):
        return self.title

    @property
    def last_date(self):
        return self.end_date or self.date

    @property
    def is_multi_day(self):
        return self.end_date is not None and self.end_date > self.date

    @property
    def span_days(self):
        return (self.last_date - self.date).days + 1

    @property
    def is_past(self):
        """지난 일정: 끝나는 날이 오늘보다 전. 읽기 전용이고 지우기만 된다."""
        from django.utils import timezone

        return self.last_date < timezone.localdate()

    @property
    def categories(self):
        return [l for l in self.labels.all() if l.kind == Label.CATEGORY]

    @property
    def tags(self):
        return [l for l in self.labels.all() if l.kind == Label.TAG]


class Taste(models.Model):
    CATEGORIES = ["음악", "영화", "영상", "책", "장소"]
    PLACE = "장소"  # 기록(지도)에 보이는 장소 글. 나머지는 순간
    MOMENT_TAGS = ["영화", "음악", "영상", "책"]  # 순간 태그 (화면 순서)
    CATEGORY_COLORS = {"음악": "rose", "영화": "sky", "영상": "sand", "책": "sage", "장소": "peach"}

    couple = models.ForeignKey(Couple, on_delete=models.CASCADE, related_name="tastes")
    author = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="tastes")
    category = models.CharField(max_length=10, choices=[(c, c) for c in CATEGORIES])
    title = models.CharField("제목", max_length=100)
    link = models.URLField("링크", blank=True)
    comment = models.TextField("한마디", blank=True)
    image = models.ImageField("사진", upload_to=taste_upload_to, blank=True, null=True)
    # 저장 공간 한도 계산용 (couples/quota.py). 이미지가 없으면 0
    image_size = models.PositiveIntegerField(default=0, editable=False)
    # 링크 미리보기 (couples/linkpreview.py). 저장할 때 한 번 가져와 둔다. 썸네일은 원래 사이트의 주소다
    preview_title = models.CharField(max_length=200, blank=True, editable=False)
    preview_image = models.URLField(max_length=500, blank=True, editable=False)
    preview_site = models.CharField(max_length=60, blank=True, editable=False)
    # 장소 글의 위치 (기록 지도, couples/places.py). 장소 글이 아니면 비어 있다
    latitude = models.FloatField("위도", null=True, blank=True)
    longitude = models.FloatField("경도", null=True, blank=True)
    address = models.CharField("주소", max_length=200, blank=True)
    place_url = models.URLField("장소 페이지", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return self.title

    @property
    def color(self):
        return self.CATEGORY_COLORS.get(self.category, "lav")

    @property
    def is_place(self):
        return self.category == self.PLACE

    @property
    def has_location(self):
        return self.latitude is not None and self.longitude is not None

    @property
    def embed(self):
        """(재생 주소, 높이). 유튜브·스포티파이 링크면 화면에서 바로 재생한다."""
        from .linkpreview import embed_for

        return embed_for(self.link)

    @property
    def embed_url(self):
        return self.embed[0]

    @property
    def embed_height(self):
        return self.embed[1]

    def refresh_preview(self):
        from .linkpreview import get_preview

        p = get_preview(self.link) if self.link else None
        self.preview_title = p.title if p else ""
        self.preview_image = p.image if p else ""
        self.preview_site = p.site if p else ""


class TasteLike(models.Model):
    """취향 좋아요. 한 사람이 한 취향에 한 번."""

    taste = models.ForeignKey(Taste, on_delete=models.CASCADE, related_name="likes")
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="taste_likes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["taste", "user"], name="unique_taste_like")]


class TasteComment(models.Model):
    """취향 댓글. 지우기는 쓴 사람만 할 수 있다."""

    MAX_LENGTH = 300

    taste = models.ForeignKey(Taste, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="taste_comments")
    text = models.TextField("댓글", max_length=MAX_LENGTH)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]

    def __str__(self):
        return self.text[:30]


def new_feed_token():
    return secrets.token_urlsafe(32)


class CalendarFeed(models.Model):
    """캘린더 앱 구독 주소. 사람마다 하나.

    캘린더 앱은 로그인을 못 하므로 주소 자체가 열쇠다. 길고 추측할 수 없는 값을 쓰고,
    새로 만들면 예전 주소는 바로 막힌다. 개인 일정은 각자 켰을 때만 넣는다.
    """

    user = models.OneToOneField("accounts.User", on_delete=models.CASCADE, related_name="calendar_feed")
    token = models.CharField(max_length=64, unique=True, default=new_feed_token, editable=False)
    include_personal = models.BooleanField("내 개인 일정도 넣기", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} 구독"

    def reset_token(self):
        self.token = new_feed_token()
        self.save(update_fields=["token"])


class Album(models.Model):
    couple = models.ForeignKey(Couple, on_delete=models.CASCADE, related_name="albums")
    title = models.CharField("앨범 이름", max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [models.UniqueConstraint(fields=["couple", "title"], name="unique_album_title_per_couple")]

    def __str__(self):
        return self.title


class Photo(models.Model):
    couple = models.ForeignKey(Couple, on_delete=models.CASCADE, related_name="photos")
    album = models.ForeignKey(Album, on_delete=models.SET_NULL, null=True, blank=True, related_name="photos")
    uploaded_by = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField("사진", upload_to=photo_upload_to)
    # 저장 공간 한도 계산용 (couples/quota.py)
    size = models.PositiveIntegerField(default=0, editable=False)
    caption = models.TextField("한마디", blank=True)
    taken_on = models.DateField("찍은 날", null=True, blank=True)
    # 촬영 위치 (couples/geo.py). 커플 두 사람만 본다. 둘 다 있거나 둘 다 없다.
    latitude = models.FloatField("위도", null=True, blank=True)
    longitude = models.FloatField("경도", null=True, blank=True)
    # 이 사진을 찍은 장소 (couples/places.py). 자동이면 찍은 위치 200m 안 가장 가까운 장소
    place = models.ForeignKey(
        "Taste", on_delete=models.SET_NULL, null=True, blank=True, related_name="place_photos", limit_choices_to={"category": "장소"}
    )
    # 사용자가 장소를 직접 정했으면 True: 자동 연결이 다시 바꾸지 않는다
    # 작은 사진(긴 변 320px). 이름은 원본 옆 "-thumb.jpg" (couples/thumbs.py)
    thumb = models.ImageField(blank=True, max_length=200, editable=False)
    thumb_size = models.PositiveIntegerField(default=0, editable=False)
    place_manual = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-taken_on", "-created_at", "-pk"]

    def __str__(self):
        return self.caption or f"사진 {self.pk}"

    @property
    def thumb_url(self):
        """작은 사진 주소. 없으면(만들지 못한 사진) 원본."""
        return self.thumb.url if self.thumb else self.image.url

    @property
    def has_location(self):
        return self.latitude is not None and self.longitude is not None

    @property
    def shot_date(self):
        return self.taken_on or self.created_at.date()


class RegionMark(models.Model):
    """색칠 지도에서 직접 칠하거나 지운 지역. 표시가 없으면 장소·사진 위치로 자동 판정한다 (static/js/coloring-map.js)."""

    LEVELS = [("sigungu", "시·군·구"), ("dong", "동")]
    STATES = [("on", "칠함"), ("off", "지움")]

    couple = models.ForeignKey(Couple, on_delete=models.CASCADE, related_name="region_marks")
    # sigungu: KOSTAT 2018 시·군·구 코드, dong: KOSTAT 2013 서울 동 코드
    level = models.CharField(max_length=10, choices=LEVELS)
    code = models.CharField(max_length=10)
    state = models.CharField(max_length=3, choices=STATES)
    updated_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["couple", "level", "code"], name="unique_region_mark")]

    def __str__(self):
        return f"{self.level}:{self.code}={self.state}"


class WishList(models.Model):
    """가고 싶은 곳 목록 (여행·맛집·카페·○○ 데이트…). 두 사람이 함께 만들고 쓴다."""

    couple = models.ForeignKey(Couple, on_delete=models.CASCADE, related_name="wish_lists")
    name = models.CharField("목록 이름", max_length=20)
    color = models.CharField("색", max_length=10, choices=COLOR_CHOICES, default="peach")
    created_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["couple", "name"], name="unique_wish_list_name")]

    def __str__(self):
        return self.name


class WishPlace(models.Model):
    """가고 싶은 곳. 다녀오면 기록 장소(Taste 장소)를 만들고 여기에는 다녀옴으로 남는다 (커플이 함께 본다)."""

    couple = models.ForeignKey(Couple, on_delete=models.CASCADE, related_name="wish_places")
    name = models.CharField("이름", max_length=100)
    latitude = models.FloatField("위도")
    longitude = models.FloatField("경도")
    address = models.CharField("주소", max_length=200, blank=True)
    place_url = models.URLField("장소 페이지", blank=True)
    link = models.URLField("링크", blank=True)
    memo = models.CharField("한 줄 메모", max_length=300, blank=True)
    lists = models.ManyToManyField(WishList, blank=True, related_name="places")
    created_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    visited_at = models.DateTimeField(null=True, blank=True)
    visited_place = models.ForeignKey("Taste", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = [models.F("visited_at").desc(nulls_first=True), "-created_at", "-pk"]

    def __str__(self):
        return self.name

    @property
    def is_visited(self):
        return self.visited_at is not None

    @property
    def color(self):
        first = sorted(self.lists.all(), key=lambda l: l.name)
        return first[0].color if first else "peach"
