from django.conf import settings
from django.db import models


class Anniversary(models.Model):
    """직접 등록하는 기념일. 100일 단위·주년은 저장하지 않고 사귄 날에서 계산한다."""

    couple = models.ForeignKey("couples.Couple", on_delete=models.CASCADE, related_name="anniversaries")
    title = models.CharField("이름", max_length=40)
    date = models.DateField("날짜")
    repeat_yearly = models.BooleanField("매년 반복", default=False, help_text="생일처럼 해마다 돌아오는 날이면 켜 주세요.")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date"]

    def __str__(self):
        return self.title
