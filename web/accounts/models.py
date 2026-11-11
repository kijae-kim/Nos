from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    nickname = models.CharField("닉네임", max_length=20, blank=True)
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
