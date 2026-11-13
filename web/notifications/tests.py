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


from datetime import date, timedelta  # noqa: E402

from anniversaries.models import Anniversary  # noqa: E402

from .schedule import due_for_couple, josa_ieyo  # noqa: E402

TODAY = date(2026, 12, 1)


class ScheduleTests(TestCase):
    def make_couple(self, days_until_500=None, members=2):
        start = TODAY - timedelta(days=499 - days_until_500) if days_until_500 is not None else None
        couple = Couple.objects.create(start_date=start)
        users = [User.objects.create_user(f"u{i}", password="pw", couple=couple) for i in range(members)]
        return couple, users

    def test_today_always_sent(self):
        couple, users = self.make_couple(days_until_500=0)
        due = due_for_couple(couple, TODAY)
        self.assertEqual({d.user for d in due}, set(users))
        self.assertEqual({d.title for d in due}, {"오늘은 500일이에요"})
        self.assertEqual({d.key for d in due}, {"auto:500일:2026-12-01:0"})
        self.assertEqual(due[0].body, "함께한 날을 축하해요")
        self.assertEqual(due[0].url, "/anniversaries/")

    def test_day_before_only_when_on(self):
        couple, (a, b) = self.make_couple(days_until_500=1)
        a.notify_day_before = True
        a.save()
        due = due_for_couple(couple, TODAY)
        self.assertEqual([d.user for d in due], [a])
        self.assertEqual(due[0].title, "내일은 500일이에요")
        self.assertEqual(due[0].body, "12월 2일, 미리 준비해 볼까요?")
        self.assertEqual(due[0].key, "auto:500일:2026-12-02:1")

    def test_week_before_only_when_on(self):
        couple, (a, b) = self.make_couple(days_until_500=7)
        b.notify_week_before = True
        b.save()
        due = due_for_couple(couple, TODAY)
        self.assertEqual([d.user for d in due], [b])
        self.assertEqual(due[0].title, "500일까지 일주일 남았어요")
        self.assertEqual(due[0].body, "12월 8일이에요")

    def test_other_offsets_ignored(self):
        couple, users = self.make_couple()
        for u in users:
            u.notify_day_before = u.notify_week_before = True
            u.save()
        for n in (2, 6, 8):
            Anniversary.objects.create(couple=couple, title=f"{n}일 뒤", date=TODAY + timedelta(days=n))
        self.assertEqual(due_for_couple(couple, TODAY), [])

    def test_custom_yearly_anniversary(self):
        couple, users = self.make_couple()
        a = Anniversary.objects.create(couple=couple, title="바다 생일", date=date(1999, 12, 1), repeat_yearly=True)
        due = due_for_couple(couple, TODAY)
        self.assertEqual({d.title for d in due}, {"오늘은 바다 생일이에요"})
        self.assertEqual({d.key for d in due}, {f"anniv:{a.pk}:2026-12-01:0"})

    def test_single_member_and_no_start_date(self):
        couple, users = self.make_couple(members=1)
        Anniversary.objects.create(couple=couple, title="첫 여행", date=TODAY)
        due = due_for_couple(couple, TODAY)
        self.assertEqual([d.user for d in due], users)

    def test_josa(self):
        self.assertEqual(josa_ieyo("1주년"), "1주년이에요")
        self.assertEqual(josa_ieyo("바다 생일"), "바다 생일이에요")
        self.assertEqual(josa_ieyo("파티"), "파티예요")
        self.assertEqual(josa_ieyo("Anniversary"), "Anniversary이에요")


import base64  # noqa: E402
import io  # noqa: E402
from unittest import mock  # noqa: E402

import requests  # noqa: E402
from django.core.management import call_command  # noqa: E402
from py_vapid import Vapid  # noqa: E402
from pywebpush import WebPushException  # noqa: E402

from . import push  # noqa: E402
from .models import PushSubscription  # noqa: E402


def make_sub(user, n=1):
    return PushSubscription.objects.create(user=user, endpoint=f"https://push.example.com/{user.pk}/{n}", p256dh="p", auth="a")


def gone(status=410):
    return WebPushException("gone", response=mock.Mock(status_code=status))


class PushTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("a", password="pw")

    @mock.patch("notifications.push.webpush")
    def test_send_success(self, webpush):
        sub = make_sub(self.user)
        self.assertTrue(push.send(sub, {"title": "t", "body": "b", "url": "/", "tag": "x"}))
        kwargs = webpush.call_args.kwargs
        self.assertEqual(kwargs["subscription_info"]["endpoint"], sub.endpoint)
        self.assertEqual(kwargs["ttl"], 86400)

    @mock.patch("notifications.push.webpush")
    def test_gone_subscription_deleted_others_still_sent(self, webpush):
        dead, alive = make_sub(self.user, 1), make_sub(self.user, 2)
        webpush.side_effect = lambda **kw: (_ for _ in ()).throw(gone()) if kw["subscription_info"]["endpoint"] == dead.endpoint else None
        self.assertEqual(push.send_to_user(self.user, {"title": "t"}), 1)
        self.assertEqual(list(PushSubscription.objects.all()), [alive])

    @mock.patch("notifications.push.webpush", side_effect=requests.exceptions.ConnectionError())
    def test_network_error_returns_false(self, webpush):
        sub = make_sub(self.user)
        self.assertFalse(push.send(sub, {"title": "t"}))
        self.assertTrue(PushSubscription.objects.filter(pk=sub.pk).exists())


class VapidKeyCommandTests(TestCase):
    def test_make_vapid_keys_output_loads(self):
        buf = io.StringIO()
        call_command("make_vapid_keys", stdout=buf)
        lines = dict(line.split("=", 1) for line in buf.getvalue().splitlines() if "=" in line and not line.startswith("#"))
        Vapid.from_string(lines["VAPID_PRIVATE_KEY"])
        public = base64.urlsafe_b64decode(lines["VAPID_PUBLIC_KEY"] + "==")
        self.assertEqual(len(public), 65)
        self.assertTrue(lines["VAPID_SUBJECT"].startswith("mailto:"))
