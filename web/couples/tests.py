from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Couple

User = get_user_model()


class CoupleFlowTests(TestCase):
    def setUp(self):
        self.a = User.objects.create_user("a", password="pw")
        self.b = User.objects.create_user("b", password="pw")
        self.c = User.objects.create_user("c", password="pw")

    def test_anonymous_is_sent_to_login(self):
        res = self.client.get(reverse("home"))
        self.assertRedirects(res, "/accounts/login/?next=/", fetch_redirect_response=False)

    def test_user_without_couple_is_sent_to_connect(self):
        self.client.force_login(self.a)
        for name in ("home", "us", "calendar"):
            self.assertRedirects(self.client.get(reverse(name)), reverse("couple_connect"))

    def test_create_then_join(self):
        self.client.force_login(self.a)
        res = self.client.post(reverse("couple_create"), {"start_date": "2024-01-01"})
        self.assertRedirects(res, reverse("home"))
        couple = Couple.objects.get()
        self.assertContains(self.client.get(reverse("home")), couple.invite_code)

        self.client.force_login(self.b)
        res = self.client.post(reverse("couple_join"), {"code": couple.invite_code.lower()})
        self.assertRedirects(res, reverse("home"))
        self.b.refresh_from_db()
        self.assertEqual(self.b.couple, couple)
        self.assertEqual(self.b.partner, self.a)

    def test_cannot_join_full_or_unknown_couple(self):
        couple = Couple.objects.create()
        User.objects.filter(pk__in=[self.a.pk, self.b.pk]).update(couple=couple)
        self.client.force_login(self.c)

        res = self.client.post(reverse("couple_join"), {"code": couple.invite_code})
        self.assertContains(res, "이미 두 사람이 연결된 공간이에요.")
        res = self.client.post(reverse("couple_join"), {"code": "ZZZZZZ"})
        self.assertContains(res, "초대 코드를 찾을 수 없어요.")
        self.c.refresh_from_db()
        self.assertIsNone(self.c.couple)

    def test_leave_deletes_empty_couple(self):
        couple = Couple.objects.create()
        User.objects.filter(pk__in=[self.a.pk, self.b.pk]).update(couple=couple)

        self.client.force_login(self.a)
        self.client.post(reverse("couple_leave"))
        self.assertTrue(Couple.objects.filter(pk=couple.pk).exists())

        self.client.force_login(self.b)
        self.client.post(reverse("couple_leave"))
        self.assertFalse(Couple.objects.filter(pk=couple.pk).exists())

    def test_days_together_counts_start_day_as_day_one(self):
        today = timezone.localdate()
        self.assertEqual(Couple(start_date=today).days_together, 1)
        self.assertEqual(Couple(start_date=today - timedelta(days=99)).days_together, 100)
        self.assertIsNone(Couple().days_together)

    def test_profile_update(self):
        couple = Couple.objects.create()
        User.objects.filter(pk=self.a.pk).update(couple=couple)
        self.client.force_login(self.a)
        res = self.client.post(reverse("us"), {"nickname": "곰", "start_date": "2024-03-01"})
        self.assertRedirects(res, reverse("us"))
        self.a.refresh_from_db()
        couple.refresh_from_db()
        self.assertEqual(self.a.nickname, "곰")
        self.assertEqual(str(couple.start_date), "2024-03-01")

        future = (timezone.localdate() + timedelta(days=1)).isoformat()
        res = self.client.post(reverse("us"), {"nickname": "곰", "start_date": future})
        self.assertContains(res, "오늘 이후의 날짜는 선택할 수 없어요.")
