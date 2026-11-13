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


from django.test import override_settings  # noqa: E402
from django.urls import reverse  # noqa: E402

from .models import PushLog as Log  # noqa: E402


@override_settings(CRON_SECRET="s3cret", WEBPUSH_ENABLED=True)
@mock.patch("notifications.views.timezone.localdate", return_value=TODAY)
class CronTests(TestCase):
    def setUp(self):
        self.couple = Couple.objects.create(start_date=TODAY - timedelta(days=499))
        self.users = [User.objects.create_user(f"c{i}", password="pw", couple=self.couple) for i in range(2)]
        self.url = reverse("cron_anniversaries")

    def call(self, secret="s3cret"):
        headers = {"HTTP_AUTHORIZATION": f"Bearer {secret}"} if secret is not None else {}
        return self.client.get(self.url, **headers)

    @mock.patch("notifications.views.send_to_user")
    def test_rejects_without_secret(self, send, _):
        self.assertEqual(self.call(secret=None).status_code, 401)
        send.assert_not_called()

    @mock.patch("notifications.views.send_to_user")
    def test_rejects_wrong_secret(self, send, _):
        self.assertEqual(self.call(secret="nope").status_code, 401)
        send.assert_not_called()

    @mock.patch("notifications.views.send_to_user")
    def test_rejects_when_secret_unset(self, send, _):
        with override_settings(CRON_SECRET=""):
            self.assertEqual(self.call(secret="").status_code, 401)
        send.assert_not_called()

    def test_503_without_vapid(self, _):
        with override_settings(WEBPUSH_ENABLED=False):
            self.assertEqual(self.call().status_code, 503)

    @mock.patch("notifications.views.send_to_user", return_value=1)
    def test_sends_and_logs(self, send, _):
        data = self.call().json()
        self.assertEqual((data["sent"], data["skipped"], data["failed"]), (2, 0, 0))
        self.assertEqual(Log.objects.count(), 2)
        payload = send.call_args.args[1]
        self.assertEqual(payload["title"], "오늘은 500일이에요")
        self.assertEqual(payload["url"], "/anniversaries/")

    @mock.patch("notifications.views.send_to_user", return_value=1)
    def test_second_call_same_day_sends_nothing(self, send, _):
        self.call()
        data = self.call().json()
        self.assertEqual((data["sent"], data["skipped"]), (0, 2))
        self.assertEqual(send.call_count, 2)

    @mock.patch("notifications.views.send_to_user", return_value=0)
    def test_failed_send_not_logged(self, send, _):
        data = self.call().json()
        self.assertEqual(data["failed"], 2)
        self.assertFalse(Log.objects.exists())

    @mock.patch("notifications.views.send_to_user", return_value=1)
    def test_old_logs_pruned(self, send, _):
        u = self.users[0]
        Log.objects.create(user=u, key="old", sent_on=TODAY - timedelta(days=61))
        Log.objects.create(user=u, key="recent", sent_on=TODAY - timedelta(days=59))
        self.call()
        self.assertEqual(set(Log.objects.filter(key__in=["old", "recent"]).values_list("key", flat=True)), {"recent"})


import json as _json  # noqa: E402

VAPID_ON = dict(WEBPUSH_ENABLED=True, VAPID_PUBLIC_KEY="pub")


class SettingsViewTests(TestCase):
    def setUp(self):
        self.couple = Couple.objects.create()
        self.me = User.objects.create_user("me", password="pw", couple=self.couple)
        self.partner = User.objects.create_user("you", password="pw", couple=self.couple)
        self.client.force_login(self.me)

    def post_json(self, name, data):
        return self.client.post(reverse(name), _json.dumps(data), content_type="application/json")

    def sub_data(self, endpoint="https://push.example.com/abc"):
        return {"endpoint": endpoint, "keys": {"p256dh": "p", "auth": "a"}}

    @override_settings(WEBPUSH_ENABLED=False)
    def test_menu_hidden_without_vapid(self):
        self.assertNotContains(self.client.get(reverse("us")), reverse("notifications"))

    @override_settings(**VAPID_ON)
    def test_menu_shown_with_vapid(self):
        self.assertContains(self.client.get(reverse("us")), reverse("notifications"))

    @override_settings(WEBPUSH_ENABLED=False)
    def test_pages_404_without_vapid(self):
        self.assertEqual(self.client.get(reverse("notifications")).status_code, 404)
        for name in ("push_subscribe", "push_unsubscribe", "push_test"):
            self.assertEqual(self.post_json(name, {}).status_code, 404, name)

    @override_settings(**VAPID_ON)
    def test_page_shows_public_key_and_states(self):
        res = self.client.get(reverse("notifications"))
        self.assertContains(res, 'data-public-key="pub"')
        self.assertContains(res, "기념일 당일에는 항상 알려 드려요")
        for state in ("on", "off", "unsupported", "ios-install", "denied"):
            self.assertContains(res, f'data-push-state="{state}"')

    @override_settings(**VAPID_ON)
    def test_save_toggles(self):
        res = self.client.post(reverse("notifications"), {"notify_week_before": "on"})
        self.assertRedirects(res, reverse("notifications"))
        self.me.refresh_from_db()
        self.assertEqual((self.me.notify_day_before, self.me.notify_week_before), (False, True))

    @override_settings(**VAPID_ON)
    def test_subscribe_creates_and_moves_owner(self):
        self.assertEqual(self.post_json("push_subscribe", self.sub_data()).json(), {"ok": True})
        self.client.force_login(self.partner)
        self.post_json("push_subscribe", self.sub_data())
        self.assertEqual(PushSubscription.objects.get().user, self.partner)

    @override_settings(**VAPID_ON)
    def test_subscribe_rejects_bad_payload(self):
        bad = [
            self.sub_data("http://push.example.com/abc"),
            {"endpoint": "https://push.example.com/abc"},
            self.sub_data("https://push.example.com/" + "x" * 500),
        ]
        for data in bad:
            self.assertEqual(self.post_json("push_subscribe", data).status_code, 400)
        res = self.client.post(reverse("push_subscribe"), "not json", content_type="application/json")
        self.assertEqual(res.status_code, 400)
        self.assertFalse(PushSubscription.objects.exists())

    @override_settings(**VAPID_ON)
    def test_unsubscribe_only_mine(self):
        theirs = make_sub(self.partner)
        mine = make_sub(self.me)
        self.post_json("push_unsubscribe", {"endpoint": theirs.endpoint})
        self.post_json("push_unsubscribe", {"endpoint": mine.endpoint})
        self.assertEqual(list(PushSubscription.objects.all()), [theirs])

    @override_settings(**VAPID_ON)
    @mock.patch("notifications.views.send_to_user", return_value=2)
    def test_push_test_calls_send(self, send):
        self.assertEqual(self.post_json("push_test", {}).json(), {"ok": True, "sent": 2})
        user, payload = send.call_args.args
        self.assertEqual(user, self.me)
        self.assertEqual(payload["title"], "알림이 잘 와요")

    @override_settings(**VAPID_ON)
    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("notifications")).status_code, 302)
