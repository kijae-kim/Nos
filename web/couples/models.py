import secrets

from django.db import models
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
