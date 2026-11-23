import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from couples.models import Couple

from .models import Memo, MemoFolder

User = get_user_model()


def L(*items):
    """줄 목록 만들기: 문자열은 글 줄, ('☐', 글) / ('☑', 글) 은 체크 줄."""
    out = []
    for it in items:
        if isinstance(it, tuple):
            out.append({"t": "check", "on": it[0] == "☑", "s": it[1]})
        else:
            out.append({"t": "text", "on": False, "s": it})
    return out


class MemoTests(TestCase):
    def setUp(self):
        self.couple = Couple.objects.create()
        self.a = User.objects.create_user("a", password="pw", couple=self.couple, nickname="하늘")
        self.b = User.objects.create_user("b", password="pw", couple=self.couple, nickname="바다")
        self.client.force_login(self.a)

    def save(self, memo, lines, version=None):
        return self.client.post(reverse("memo_save", args=[memo.pk]),
                                json.dumps({"lines": lines, "version": memo.version if version is None else version}),
                                content_type="application/json")

    def new_memo(self, folder=None):
        url = reverse("memo_new") + (f"?folder={folder.pk}" if folder else "")
        res = self.client.get(url)
        memo = Memo.objects.latest("pk")
        self.assertRedirects(res, reverse("memo_edit", args=[memo.pk]))
        return memo

    def test_default_folders(self):
        res = self.client.get(reverse("memos"))
        self.assertEqual(list(MemoFolder.objects.filter(couple=self.couple).values_list("name", flat=True)), ["버킷리스트", "여행계획"])
        self.assertContains(res, "버킷리스트")
        self.client.get(reverse("memos"))
        self.assertEqual(MemoFolder.objects.count(), 2)  # 두 번 만들지 않음

    def test_folder_create_duplicate_and_delete_rules(self):
        self.client.get(reverse("memos"))
        self.client.post(reverse("memo_folder_create"), {"name": "데이트"})
        self.assertContains(self.client.post(reverse("memo_folder_create"), {"name": "데이트"}), "이미 있는 폴더 이름이에요.")
        bucket = MemoFolder.objects.get(name="버킷리스트")
        self.new_memo(bucket)
        memo = Memo.objects.get()
        self.save(memo, L("오로라 보기"))
        res = self.client.post(reverse("memo_folder_delete", args=[bucket.pk]), follow=True)
        self.assertContains(res, "메모를 옮기거나 지운 뒤에 지울 수 있어요.")
        self.assertTrue(MemoFolder.objects.filter(pk=bucket.pk).exists())
        empty = MemoFolder.objects.get(name="데이트")
        self.client.post(reverse("memo_folder_delete", args=[empty.pk]))
        self.assertFalse(MemoFolder.objects.filter(pk=empty.pk).exists())

    def test_save_sets_title_preview_and_version(self):
        memo = self.new_memo()
        res = self.save(memo, L("", "제주 여행", ("☐", "숙소 예약"), ("☑", "비행기")))
        self.assertEqual(res.json()["ok"], True)
        self.assertEqual(res.json()["version"], 1)
        memo.refresh_from_db()
        self.assertEqual((memo.title, memo.preview, memo.version, memo.updated_by), ("제주 여행", "☐ 숙소 예약", 1, self.a))
        self.assertEqual(memo.lines[2], {"t": "check", "on": False, "s": "숙소 예약"})

    def test_conflict_409_keeps_server_copy(self):
        memo = self.new_memo()
        self.save(memo, L("먼저 쓴 글"))
        self.client.force_login(self.b)
        res = self.save(memo, L("옛 버전에서 쓴 글"), version=0)
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["lines"], L("먼저 쓴 글"))
        self.assertEqual(res.json()["version"], 1)
        memo.refresh_from_db()
        self.assertEqual(memo.title, "먼저 쓴 글")

    def test_bad_lines_400(self):
        memo = self.new_memo()
        for bad in ([{"t": "html", "on": False, "s": "x"}], [{"t": "text", "on": "yes", "s": "x"}],
                    [{"t": "text", "on": False, "s": "x" * 1001}], "lines", [{"t": "text"}],
                    [{"t": "text", "on": False, "s": "가" * 1000}] * 21):
            res = self.save(memo, bad)
            self.assertEqual(res.status_code, 400, bad if not isinstance(bad, list) or len(bad) < 3 else "too long")
        res = self.client.post(reverse("memo_save", args=[memo.pk]), "x", content_type="application/json")
        self.assertEqual(res.status_code, 400)

    def test_folder_list_and_empty_cleanup(self):
        bucket = self.client.get(reverse("memos")) and MemoFolder.objects.get(name="버킷리스트")
        full = self.new_memo(bucket)
        self.save(full, L("오로라", "아이슬란드에서"))
        empty = self.new_memo(bucket)
        res = self.client.get(reverse("memo_folder", args=[bucket.pk]))
        self.assertContains(res, "오로라")
        self.assertContains(res, "아이슬란드에서")
        self.assertContains(res, "메모 1개")  # 글 없는 메모는 목록에 안 보임
        Memo.objects.filter(pk=empty.pk).update(updated_at=timezone.now() - timedelta(hours=2))
        self.client.get(reverse("memo_folder", args=[bucket.pk]))
        self.assertFalse(Memo.objects.filter(pk=empty.pk).exists())  # 오래 빈 메모는 정리

    def test_move_and_delete(self):
        self.client.get(reverse("memos"))
        bucket, trip = MemoFolder.objects.get(name="버킷리스트"), MemoFolder.objects.get(name="여행계획")
        memo = self.new_memo(bucket)
        self.save(memo, L("제주"))
        self.client.post(reverse("memo_move", args=[memo.pk]), {"folder": trip.pk})
        memo.refresh_from_db()
        self.assertEqual(memo.folder, trip)
        self.client.post(reverse("memo_delete", args=[memo.pk]))
        self.assertFalse(Memo.objects.filter(pk=memo.pk).exists())

    def test_other_couple_404(self):
        memo = self.new_memo()
        self.save(memo, L("우리 메모"))
        other = Couple.objects.create()
        stranger = User.objects.create_user("c", password="pw", couple=other)
        self.client.force_login(stranger)
        for name in ("memo_edit", "memo_delete"):
            method = self.client.get if name == "memo_edit" else self.client.post
            self.assertEqual(method(reverse(name, args=[memo.pk])).status_code, 404, name)
        self.assertEqual(self.save(memo, L("가로채기")).status_code, 404)
        self.assertEqual(self.client.get(reverse("memo_folder", args=[memo.folder.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("memos")), "우리 메모")

    def test_edit_page_has_initial_json(self):
        memo = self.new_memo()
        self.save(memo, L("제목", ("☐", "할 일")))
        page = self.client.get(reverse("memo_edit", args=[memo.pk]))
        self.assertContains(page, 'id="memo-data"')
        self.assertContains(page, "memo-editor.js")

    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("memos")).status_code, 302)


class MemoEditorPageTests(TestCase):
    setUp = MemoTests.setUp

    def test_editor_page_assets(self):
        self.client.get(reverse("memos"))
        res = self.client.get(reverse("memo_new"))
        page = self.client.get(res["Location"])
        self.assertContains(page, "data-memo-editor")
        self.assertContains(page, "data-make-check")
        self.assertContains(page, 'id="i-check-circle"')
        from pathlib import Path

        js = (Path(__file__).resolve().parent.parent / "static/js/memo-editor.js").read_text()
        for needle in ("beforeinput", "text/plain", "keepalive", "409"):
            self.assertIn(needle, js)


class MemoHomeTests(TestCase):
    setUp = MemoTests.setUp
    save = MemoTests.save
    new_memo = MemoTests.new_memo

    def test_home_shows_recent_memos(self):
        m = self.new_memo()
        self.save(m, L("오로라 보기"))
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("오로라 보기", html)
        self.assertIn(reverse("memo_edit", args=[m.pk]), html)
        self.assertIn(reverse("memos"), html)

    def test_quick_menu_has_memo_and_remembers_folder(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn(f'href="{reverse("memo_new")}"', html)
        self.assertEqual(html.count('class="quick"'), 6)
        self.client.get(reverse("memos"))
        trip = MemoFolder.objects.get(name="여행계획")
        self.client.get(reverse("memo_folder", args=[trip.pk]))
        self.client.get(reverse("memo_new"))
        self.assertEqual(Memo.objects.latest("pk").folder, trip)

    def test_empty_home_card(self):
        self.assertContains(self.client.get(reverse("home")), "버킷리스트나 여행 계획을 적어 볼까요?")


class MemoReviewFixTests(TestCase):
    """최종 검토에서 나온 것 (글 잃지 않기)."""

    setUp = MemoTests.setUp
    save = MemoTests.save
    new_memo = MemoTests.new_memo

    def js(self):
        from pathlib import Path

        return (Path(__file__).resolve().parent.parent / "static/js/memo-editor.js").read_text()

    def test_cleanup_keeps_fresh_empty_memo(self):
        """상대가 방금 연 빈 메모는 목록을 열어도 지우지 않는다 (1시간 넘은 빈 메모만)."""
        fresh = self.new_memo()
        old = Memo.objects.create(couple=self.couple, folder=fresh.folder, lines=[], created_by=self.b)
        Memo.objects.filter(pk=old.pk).update(updated_at=timezone.now() - timedelta(hours=2))
        self.client.force_login(self.b)
        self.client.get(reverse("memo_folder", args=[fresh.folder.pk]))
        self.assertTrue(Memo.objects.filter(pk=fresh.pk).exists())
        self.assertFalse(Memo.objects.filter(pk=old.pk).exists())

    def test_edit_and_list_not_cached(self):
        memo = self.new_memo()
        for url in (reverse("memo_edit", args=[memo.pk]), reverse("memo_folder", args=[memo.folder.pk])):
            self.assertIn("no-cache", self.client.get(url)["Cache-Control"], url)

    def test_editor_guards(self):
        js = self.js()
        self.assertIn("localStorage", js)  # 떠날 때·저장 중 끊겨도 내 글을 기기에 남김
        self.assertIn("compositionend", js)  # 한글 입력 중에는 다시 그리지 않음
        self.assertIn("deleteContents", js)  # 고른 글 위에 붙여 넣기·엔터
        self.assertIn("메모가 지워졌어요", js)  # 404
        self.assertIn("var mineNow = serialize()", js)  # 충돌 때 저장 중에 친 글까지


class MemoMinorTests(TestCase):
    """메모 작은 것들."""

    setUp = MemoTests.setUp
    save = MemoTests.save
    new_memo = MemoTests.new_memo

    def js(self):
        from pathlib import Path

        return (Path(__file__).resolve().parent.parent / "static/js/memo-editor.js").read_text()

    def test_new_memo_reuses_my_fresh_empty_memo(self):
        a = self.new_memo()
        self.client.get(reverse("memo_new"))  # 두 번 누름
        self.assertEqual(Memo.objects.count(), 1)
        self.save(a, L("글"))
        self.client.get(reverse("memo_new"))
        self.assertEqual(Memo.objects.count(), 2)

    def test_folder_counts_skip_empty_and_order(self):
        self.client.get(reverse("memos"))
        self.client.post(reverse("memo_folder_create"), {"name": "가나다"})
        self.new_memo()  # 빈 메모
        res = self.client.get(reverse("memos"))
        names = [f.name for f in res.context["folders"]]
        self.assertEqual(names, ["버킷리스트", "여행계획", "가나다"])  # 기본 두 개 먼저, 그다음 이름 순
        self.assertEqual([f.count for f in res.context["folders"]], [0, 0, 0])

    def test_default_folders_race_safe(self):
        from .lines import ensure_default_folders
        from .models import MemoFolder

        MemoFolder.objects.create(couple=self.couple, name="버킷리스트")  # 상대가 먼저 하나 만든 상태
        ensure_default_folders(self.couple)
        self.assertEqual(sorted(MemoFolder.objects.values_list("name", flat=True)), ["버킷리스트", "여행계획"])

    def test_save_rejects_bool_version_and_returns_updated(self):
        m = self.new_memo()
        self.assertEqual(self.client.post(reverse("memo_save", args=[m.pk]), json.dumps({"lines": L("x"), "version": True}),
                                          content_type="application/json").status_code, 400)
        res = self.save(m, L("x"))
        self.assertIn("updated", res.json())

    def test_too_long_message(self):
        m = self.new_memo()
        res = self.save(m, [{"t": "text", "on": False, "s": "가" * 1000}] * 21)
        self.assertEqual(res.json()["error"], "메모가 너무 길어요. 2만 자까지 쓸 수 있어요.")

    def test_editor_minor_bits(self):
        js = self.js()
        self.assertIn("touchend", js)  # 체크 동그라미를 터치로
        self.assertIn('e.key === "Enter" && (e.metaKey || e.ctrlKey)', js)  # 키보드로 체크
        self.assertIn("setTimeout(saveNow, 5000)", js)  # 실패하면 다시
        self.assertIn("60000", js)  # 떠날 때 큰 글은 기기에만
        self.assertIn("data-conflict-close", js)
        from pathlib import Path

        css = (Path(__file__).resolve().parent.parent / "static/css/app.css").read_text()
        self.assertIn("white-space: pre-wrap", css.split(".memo-editor {")[1].split("}")[0])


class CalendarLeftoverTests(TestCase):
    setUp = MemoTests.setUp

    def test_full_form_takes_all_day(self):
        page = self.client.get(reverse("event_create") + "?date=2026-12-01&all_day=on")
        self.assertTrue(page.context["form"].initial["all_day"])

    def test_popup_passes_all_day(self):
        from pathlib import Path

        js = (Path(__file__).resolve().parent.parent / "static/js/calendar-popup.js").read_text()
        self.assertIn("&all_day=on", js)
        views = (Path(__file__).resolve().parent.parent / "couples/views.py").read_text()
        self.assertNotIn("day_events = upcoming", views)


class MemoPreDeployTests(TestCase):
    setUp = MemoTests.setUp
    save = MemoTests.save
    new_memo = MemoTests.new_memo

    def js(self):
        from pathlib import Path

        return (Path(__file__).resolve().parent.parent / "static/js/memo-editor.js").read_text()

    def test_folder_with_only_empty_memos_can_be_deleted(self):
        self.client.get(reverse("memos"))
        self.client.post(reverse("memo_folder_create"), {"name": "데이트"})
        folder = MemoFolder.objects.get(name="데이트")
        self.new_memo(folder)  # 쓰다 만 빈 메모
        self.client.post(reverse("memo_folder_delete", args=[folder.pk]))
        self.assertFalse(MemoFolder.objects.filter(pk=folder.pk).exists())

    def test_editor_compares_lines_not_json_key_order_and_ignores_swipes(self):
        js = self.js()
        self.assertIn("function sameLines", js)
        self.assertNotIn("JSON.stringify(draft.lines) === JSON.stringify(data.lines)", js)
        self.assertIn("touchstart", js)

    def test_new_memo_fallback_folder_is_default_first(self):
        self.client.get(reverse("memos"))
        MemoFolder.objects.create(couple=self.couple, name="가가")
        self.new_memo()
        self.assertEqual(Memo.objects.latest("pk").folder.name, "버킷리스트")


class MemoShortcutScriptTests(TestCase):
    def test_editor_has_dash_and_todo_shortcuts(self):
        from pathlib import Path

        js = (Path(__file__).resolve().parent.parent / "static/js/memo-editor.js").read_text()
        self.assertIn('var SHORTCUTS = ["- ", "/todo "]', js)
        self.assertIn("shortcut()", js)


class MemoNotifyTests(TestCase):
    """메모를 고치고 떠나면 상대에게 알림 (같은 메모 30분에 한 번)."""

    setUp = MemoTests.setUp

    def memo(self, **kw):
        folder, _ = MemoFolder.objects.get_or_create(couple=self.couple, name="여행계획")
        lines = [{"t": "text", "on": False, "s": "부산 여행"}]
        defaults = dict(couple=self.couple, folder=folder, lines=lines, title="부산 여행", version=1, created_by=self.a, updated_by=self.a)
        defaults.update(kw)
        return Memo.objects.create(**defaults)

    def notify(self, memo):
        from unittest import mock

        with mock.patch("memos.notify.send_to_user", return_value=1) as sent:
            res = self.client.post(reverse("memo_notify", args=[memo.pk]))
        return res, sent

    def test_partner_gets_one_push_with_title_and_link(self):
        memo = self.memo()
        res, sent = self.notify(memo)
        self.assertEqual(res.status_code, 204)
        sent.assert_called_once()
        user, payload = sent.call_args.args
        self.assertEqual(user, self.b)
        self.assertEqual(payload["title"], "하늘님이 메모를 고쳤어요")
        self.assertEqual(payload["body"], "여행계획 · 부산 여행")
        self.assertEqual(payload["url"], reverse("memo_edit", args=[memo.pk]))
        memo.refresh_from_db()
        self.assertIsNotNone(memo.notified_at)

    def test_second_within_30_minutes_is_skipped_then_sent_after(self):
        memo = self.memo(notified_at=timezone.now() - timedelta(minutes=10))
        _, sent = self.notify(memo)
        sent.assert_not_called()
        Memo.objects.filter(pk=memo.pk).update(notified_at=timezone.now() - timedelta(minutes=31))
        _, sent = self.notify(memo)
        sent.assert_called_once()

    def test_not_sent_when_partner_turned_off_or_i_did_not_edit_or_empty(self):
        User.objects.filter(pk=self.b.pk).update(notify_memo=False)
        _, sent = self.notify(self.memo())
        sent.assert_not_called()
        User.objects.filter(pk=self.b.pk).update(notify_memo=True)
        _, sent = self.notify(self.memo(updated_by=self.b))  # 상대가 고친 메모를 내가 열기만 함
        sent.assert_not_called()
        _, sent = self.notify(self.memo(title="", lines=[]))
        sent.assert_not_called()

    def test_push_error_does_not_break(self):
        from unittest import mock

        memo = self.memo()
        with mock.patch("memos.notify.send_to_user", side_effect=RuntimeError("boom")):
            res = self.client.post(reverse("memo_notify", args=[memo.pk]))
        self.assertEqual(res.status_code, 204)

    def test_other_couple_404_and_get_not_allowed(self):
        memo = self.memo()
        self.assertEqual(self.client.get(reverse("memo_notify", args=[memo.pk])).status_code, 405)
        other = Couple.objects.create()
        stranger = User.objects.create_user("z", password="pw", couple=other)
        self.client.force_login(stranger)
        self.assertEqual(self.client.post(reverse("memo_notify", args=[memo.pk])).status_code, 404)

    def test_default_on_and_editor_calls_notify(self):
        self.assertTrue(User.objects.create_user("n", password="pw").notify_memo)
        html = self.client.get(reverse("memo_edit", args=[self.memo().pk])).content.decode()
        self.assertIn("data-notify-url", html)
