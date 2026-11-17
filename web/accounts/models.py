from django.contrib.auth.models import AbstractUser
from django.db import models


# 커플 앱과 같은 6색 (순환 import 를 피해 여기 둔다. couples.models.COLOR_CHOICES 와 같아야 한다)
COLOR_CHOICES = [
    ("sky", "하늘"),
    ("rose", "장미"),
    ("sand", "모래"),
    ("lav", "라벤더"),
    ("sage", "세이지"),
    ("peach", "복숭아"),
]


class User(AbstractUser):
    PALETTE_CHOICES = [("boat", "배"), ("journey", "여정")]
    MODE_CHOICES = [("system", "기기 설정"), ("light", "라이트"), ("dark", "다크")]

    nickname = models.CharField("닉네임", max_length=20, blank=True)
    # 테마와 화면 모드. 계정에 두어 휴대폰을 바꾸거나 새로 설치해도 그대로 따라온다 (static/js/theme.js)
    palette = models.CharField("테마", max_length=10, choices=PALETTE_CHOICES, default="boat")
    mode = models.CharField("화면 모드", max_length=10, choices=MODE_CHOICES, default="system")
    # 기념일 알림. 당일 알림은 항상 보내고, 하루 전·일주일 전은 사람마다 고른다 (notifications 앱)
    notify_day_before = models.BooleanField("하루 전 알림", default=False)
    notify_week_before = models.BooleanField("일주일 전 알림", default=False)
    # 프로필: 내 색(일정 만든 사람 점·아바타 바탕), 이모지, 사진(256px JPEG 바이트, DB 에 둔다)
    color = models.CharField("내 색", max_length=10, choices=COLOR_CHOICES, default="sky")
    emoji = models.CharField("이모지", max_length=16, blank=True)
    avatar = models.BinaryField(null=True, blank=True, editable=False)
    has_avatar = models.BooleanField(default=False, editable=False)  # avatar 를 읽지 않고 알기 위해
    avatar_version = models.PositiveIntegerField(default=0, editable=False)
    couple = models.ForeignKey(
        "couples.Couple",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="members",
    )

    @property
    def display_name(self):
        if self.nickname:
            return self.nickname
        if self.first_name:
            return self.first_name
        if self.email:
            return self.email.split("@")[0]
        return self.username

    @property
    def avatar_url(self):
        if not self.has_avatar:
            return ""
        from django.urls import reverse

        return f"{reverse('avatar', args=[self.pk])}?v={self.avatar_version}"

    @property
    def partner(self):
        if not self.couple_id:
            return None
        return self.couple.members.exclude(pk=self.pk).first()
