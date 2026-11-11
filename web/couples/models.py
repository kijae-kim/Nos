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
        """공통 일정은 두 사람 모두, 개인 일정은 만든 사람만 본다."""
        return self.filter(
            models.Q(couple=user.couple_id, scope=Event.SHARED)
            | models.Q(couple=user.couple_id, scope=Event.PERSONAL, created_by=user)
        )


class Event(models.Model):
    SHARED = "shared"
    PERSONAL = "personal"
    SCOPE_CHOICES = [(SHARED, "공통"), (PERSONAL, "개인")]

    couple = models.ForeignKey(Couple, on_delete=models.CASCADE, related_name="events")
    created_by = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="events")
    scope = models.CharField(max_length=10, choices=SCOPE_CHOICES, default=SHARED)
    title = models.CharField("일정", max_length=100)
    date = models.DateField("날짜")
    start_time = models.TimeField("시작", null=True, blank=True)
    end_time = models.TimeField("끝", null=True, blank=True)
    place = models.CharField("장소", max_length=100, blank=True)
    color = models.CharField(max_length=10, choices=COLOR_CHOICES, default="sky")
    labels = models.ManyToManyField(Label, blank=True, related_name="events")
    created_at = models.DateTimeField(auto_now_add=True)

    objects = EventQuerySet.as_manager()

    class Meta:
        ordering = ["date", "start_time", "pk"]

    def __str__(self):
        return self.title

    @property
    def categories(self):
        return [l for l in self.labels.all() if l.kind == Label.CATEGORY]

    @property
    def tags(self):
        return [l for l in self.labels.all() if l.kind == Label.TAG]


class Taste(models.Model):
    CATEGORIES = ["음악", "영화", "영상", "책", "장소"]
    CATEGORY_COLORS = {"음악": "rose", "영화": "sky", "영상": "sand", "책": "sage", "장소": "peach"}

    couple = models.ForeignKey(Couple, on_delete=models.CASCADE, related_name="tastes")
    author = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="tastes")
    category = models.CharField(max_length=10, choices=[(c, c) for c in CATEGORIES])
    title = models.CharField("제목", max_length=100)
    link = models.URLField("링크", blank=True)
    comment = models.TextField("한마디", blank=True)
    image = models.ImageField("사진", upload_to=taste_upload_to, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return self.title

    @property
    def color(self):
        return self.CATEGORY_COLORS.get(self.category, "lav")


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
    caption = models.TextField("한마디", blank=True)
    taken_on = models.DateField("찍은 날", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-taken_on", "-created_at", "-pk"]

    def __str__(self):
        return self.caption or f"사진 {self.pk}"

    @property
    def shot_date(self):
        return self.taken_on or self.created_at.date()
