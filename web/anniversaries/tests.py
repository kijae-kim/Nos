from datetime import date

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from couples.models import Couple

from . import services
from .models import Anniversary

User = get_user_model()


class MilestoneTests(SimpleTestCase):
    def titles(self, start, today):
        return {i.title: i for i in services.auto_milestones(start, today)}

    def test_hundred_days_counts_start_as_day_one(self):
        items = self.titles(date(2026, 1, 1), date(2026, 1, 2))
        self.assertEqual(items["100일"].date, date(2026, 4, 10))
        self.assertEqual(items["100일"].days_left, 98)
        self.assertIn("200일", items)
        self.assertIn("300일", items)

    def test_milestone_on_the_day_is_today(self):
        items = self.titles(date(2026, 1, 1), date(2026, 4, 10))
        self.assertEqual(items["100일"].dday, "오늘")

    def test_passed_milestones_are_skipped(self):
        items = self.titles(date(2026, 1, 1), date(2026, 4, 11))
        self.assertNotIn("100일", items)
        self.assertEqual(items["200일"].dday, "D-99")

    def test_yearly(self):
        items = self.titles(date(2024, 8, 4), date(2026, 11, 11))
        self.assertEqual(items["3주년"].date, date(2027, 8, 4))
        self.assertEqual(items["4주년"].date, date(2028, 8, 4))
        self.assertNotIn("2주년", items)

    def test_yearly_on_the_day_and_leap_day(self):
        self.assertEqual(self.titles(date(2025, 11, 11), date(2026, 11, 11))["1주년"].dday, "오늘")
        self.assertEqual(self.titles(date(2024, 2, 29), date(2024, 3, 1))["1주년"].date, date(2025, 2, 28))

    def test_no_start_date(self):
        self.assertEqual(services.auto_milestones(None, date(2026, 1, 1)), [])

    def test_next_occurrence(self):
        today = date(2026, 11, 11)
        self.assertEqual(services.next_occurrence(date(1999, 12, 25), today), date(2026, 12, 25))
        self.assertEqual(services.next_occurrence(date(1999, 3, 1), today), date(2027, 3, 1))
        self.assertEqual(services.next_occurrence(date(1999, 11, 11), today), today)


class AnniversaryViewTests(TestCase):
    def setUp(self):
        self.couple = Couple.objects.create(start_date=date(2025, 1, 1))
        self.other = Couple.objects.create()
        self.user = User.objects.create_user("a", password="pw", couple=self.couple)
        self.stranger = User.objects.create_user("x", password="pw", couple=self.other)
        self.client.force_login(self.user)

    def test_build_splits_upcoming_and_past(self):
        today = date(2026, 11, 11)
        Anniversary.objects.create(couple=self.couple, title="생일", date=date(1999, 12, 25), repeat_yearly=True)
        Anniversary.objects.create(couple=self.couple, title="첫 여행", date=date(2025, 5, 5))
        upcoming, past = services.build(self.couple, today)
        self.assertEqual([i.title for i in past], ["첫 여행"])
        self.assertEqual(past[0].dday, "D+555")
        self.assertIn("생일", [i.title for i in upcoming])
        self.assertEqual(upcoming, sorted(upcoming, key=lambda i: i.date))

    def test_create_update_delete(self):
        res = self.client.post(reverse("anniversary_create"), {"title": "생일", "date": "1999-12-25", "repeat_yearly": "on"})
        self.assertRedirects(res, reverse("anniversary_index"))
        a = Anniversary.objects.get()
        self.assertEqual((a.couple, a.created_by, a.repeat_yearly), (self.couple, self.user, True))

        self.client.post(reverse("anniversary_update", args=[a.pk]), {"title": "내 생일", "date": "1999-12-25"})
        a.refresh_from_db()
        self.assertEqual((a.title, a.repeat_yearly), ("내 생일", False))

        self.assertContains(self.client.get(reverse("anniversary_index")), "내 생일")
        self.assertContains(self.client.get(reverse("home")), "주년")

        self.client.post(reverse("anniversary_delete", args=[a.pk]))
        self.assertFalse(Anniversary.objects.exists())

    def test_other_couple_cannot_touch(self):
        a = Anniversary.objects.create(couple=self.couple, title="둘만의 비밀", date=date(1999, 12, 25))
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.get(reverse("anniversary_update", args=[a.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("anniversary_delete", args=[a.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("anniversary_index")), "둘만의 비밀")
        self.assertTrue(Anniversary.objects.filter(pk=a.pk).exists())
