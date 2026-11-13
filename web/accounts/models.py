from django.contrib.auth.models import AbstractUser
from django.db import models


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
    def partner(self):
        if not self.couple_id:
            return None
        return self.couple.members.exclude(pk=self.pk).first()
