from django.conf import settings
from django.db import models


class MemoFolder(models.Model):
    """메모 폴더 (버킷리스트·여행계획 + 직접 만든 것). 커플이 함께 쓴다."""

    couple = models.ForeignKey("couples.Couple", on_delete=models.CASCADE, related_name="memo_folders")
    name = models.CharField("폴더 이름", max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]  # 화면에서는 lines.ordered_folders 로 기본 두 개 먼저
        constraints = [models.UniqueConstraint(fields=["couple", "name"], name="unique_memo_folder")]

    def __str__(self):
        return self.name


class Memo(models.Model):
    """메모 한 장. 내용은 줄 목록 [{"t": "text"|"check", "on": bool, "s": 글}] (memos/lines.py)."""

    couple = models.ForeignKey("couples.Couple", on_delete=models.CASCADE, related_name="memos")
    folder = models.ForeignKey(MemoFolder, on_delete=models.PROTECT, related_name="memos")
    lines = models.JSONField(default=list)
    title = models.CharField(max_length=100, blank=True)
    preview = models.CharField(max_length=120, blank=True)
    version = models.PositiveIntegerField(default=0)  # 동시에 고칠 때 덮어쓰지 않게
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notified_at = models.DateTimeField(null=True, blank=True)  # 상대에게 마지막으로 알린 때 (30분에 한 번)

    class Meta:
        ordering = ["-updated_at", "-pk"]

    def __str__(self):
        return self.title or "새 메모"

    @property
    def is_empty(self):
        return not any(line.get("s", "").strip() for line in self.lines)
