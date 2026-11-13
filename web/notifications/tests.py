from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from couples.models import Couple

from .models import PushLog

User = get_user_model()


class ModelTests(TestCase):
    def test_user_notify_defaults_off(self):
        user = User.objects.create_user("a", password="pw", couple=Couple.objects.create())
        self.assertFalse(user.notify_day_before)
        self.assertFalse(user.notify_week_before)

    def test_push_log_unique(self):
        user = User.objects.create_user("a", password="pw")
        PushLog.objects.create(user=user, key="auto:500일:2026-12-01:0", sent_on="2026-12-01")
        with self.assertRaises(IntegrityError):
            PushLog.objects.create(user=user, key="auto:500일:2026-12-01:0", sent_on="2026-12-01")
