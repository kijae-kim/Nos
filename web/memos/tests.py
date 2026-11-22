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
        self.assertFalse(Memo.objects.filter(pk=empty.pk).exists())  # 글 없는 메모는 정리

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
