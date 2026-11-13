from django.conf import settings
from django.db import models


class PushSubscription(models.Model):
    """알림을 받을 기기(브라우저) 하나. 브라우저가 만든 구독 정보를 그대로 저장한다."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_subscriptions")
    endpoint = models.CharField(max_length=500, unique=True)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} · {self.endpoint[:40]}"


class PushLog(models.Model):
    """보낸 알림 기록. Cron 이 같은 날 두 번 불려도 같은 알림을 다시 보내지 않게 한다."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    key = models.CharField(max_length=120)
    sent_on = models.DateField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "key"], name="unique_push_log")]

    def __str__(self):
        return self.key
