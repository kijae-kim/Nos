import os
import tempfile
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import services
from .models import Album, CalendarFeed, Couple, Event, Label, Photo, Taste, TasteComment, TasteLike

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


class ScreenTests(TestCase):
    """캘린더·취향·앨범을 실제 데이터로 만들고 고칠 수 있는지 확인한다."""

    def setUp(self):
        self.couple = Couple.objects.create(start_date=timezone.localdate() - timedelta(days=99))
        self.a = User.objects.create_user("a", password="pw", couple=self.couple, nickname="하늘")
        self.b = User.objects.create_user("b", password="pw", couple=self.couple, nickname="바다")
        self.client.force_login(self.a)

    def event_form(self, **overrides):
        data = {
            "text": "전시 보러 가기 @데이트 #성수",
            "date": timezone.localdate().isoformat(),
            "start_time": "14:00",
            "end_time": "16:00",
            "place": "성수",
            "scope": "shared",
            "color": "sky",
        }
        data.update(overrides)
        return data

    def test_split_text_separates_title_categories_and_tags(self):
        title, labels = services.split_text("전시 보러 가기 @데이트 #성수 #혼자")
        self.assertEqual(title, "전시 보러 가기")
        self.assertEqual(labels, [(Label.CATEGORY, "데이트"), (Label.TAG, "성수"), (Label.TAG, "혼자")])

    def test_creating_event_makes_labels_and_reuses_them(self):
        self.client.post(reverse("event_create"), self.event_form())
        self.client.post(reverse("event_create"), self.event_form(text="저녁 @데이트"))
        self.assertEqual(Label.objects.filter(couple=self.couple, name="데이트").count(), 1)
        event = Event.objects.get(title="전시 보러 가기")
        self.assertEqual({str(l) for l in event.labels.all()}, {"@데이트", "#성수"})

    def test_label_only_text_is_rejected(self):
        response = self.client.post(reverse("event_create"), self.event_form(text="@데이트"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Event.objects.exists())

    def test_edit_event_keeps_labels_in_text_and_updates_fields(self):
        self.client.post(reverse("event_create"), self.event_form())
        event = Event.objects.get()
        response = self.client.get(reverse("event_update", args=[event.pk]))
        self.assertIn("@데이트", response.context["form"].initial["text"])
        self.client.post(reverse("event_update", args=[event.pk]), self.event_form(text="성수 산책 #산책", place="서울숲"))
        event.refresh_from_db()
        self.assertEqual(event.title, "성수 산책")
        self.assertEqual(event.place, "서울숲")
        self.assertEqual([str(l) for l in event.labels.all()], ["#산책"])

    def test_personal_event_is_visible_only_to_its_owner(self):
        self.client.post(reverse("event_create"), self.event_form(text="혼자 운동", scope="personal"))
        event = Event.objects.get()
        self.client.force_login(self.b)
        self.assertEqual(self.client.get(reverse("event_update", args=[event.pk])).status_code, 404)
        response = self.client.get(reverse("calendar"))
        self.assertNotIn(event, list(response.context["upcoming"]))

    def test_partner_can_edit_and_delete_shared_event(self):
        self.client.post(reverse("event_create"), self.event_form())
        event = Event.objects.get()
        self.client.force_login(self.b)
        self.client.post(reverse("event_update", args=[event.pk]), self.event_form(text="바뀐 일정"))
        event.refresh_from_db()
        self.assertEqual(event.title, "바뀐 일정")
        self.client.post(reverse("event_delete", args=[event.pk]))
        self.assertFalse(Event.objects.exists())

    def test_calendar_month_and_selected_day(self):
        response = self.client.get(reverse("calendar"), {"month": "2026-11", "day": "2026-11-14"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["first"].month, 11)
        self.assertEqual(response.context["selected"].day, 14)

    def test_calendar_bad_month_falls_back_to_this_month(self):
        response = self.client.get(reverse("calendar"), {"month": "bad", "day": "bad"})
        self.assertEqual(response.context["first"].month, timezone.localdate().month)
        self.assertEqual(response.context["selected"], timezone.localdate())

    @patch("couples.linkpreview.fetch", side_effect=OSError("테스트에서는 인터넷에 나가지 않는다"))
    def test_taste_create_detail_edit_delete(self, _fetch):
        response = self.client.post(reverse("taste_create"), {"category": "영화", "title": "헤어질 결심", "link": "https://example.com/film", "comment": "바다 장면"})
        taste = Taste.objects.get()
        self.assertRedirects(response, reverse("taste_detail", args=[taste.pk]))
        self.assertContains(self.client.get(reverse("taste_detail", args=[taste.pk])), "바다 장면")
        self.client.post(reverse("taste_update", args=[taste.pk]), {"category": "책", "title": "작은 것들의 신", "link": "", "comment": ""})
        taste.refresh_from_db()
        self.assertEqual((taste.category, taste.title), ("책", "작은 것들의 신"))
        self.client.post(reverse("taste_delete", args=[taste.pk]))
        self.assertFalse(Taste.objects.exists())

    def test_taste_filters_by_category_and_author(self):
        Taste.objects.create(couple=self.couple, author=self.a, category="영화", title="영화A")
        Taste.objects.create(couple=self.couple, author=self.b, category="영화", title="영화B")
        Taste.objects.create(couple=self.couple, author=self.b, category="음악", title="음악B")
        response = self.client.get(reverse("tastes"), {"cat": "영화", "who": str(self.b.pk)})
        self.assertEqual([t.title for t in response.context["tastes"]], ["영화B"])

    def image_file(self):
        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        buffer = BytesIO()
        Image.new("RGB", (4, 4), (200, 80, 90)).save(buffer, "PNG")
        return SimpleUploadedFile("photo.png", buffer.getvalue(), content_type="image/png")

    def test_photo_upload_shows_the_image_and_creates_album(self):
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(
                reverse("photo_create"),
                {"image": self.image_file(), "new_album": "성수동 산책", "taken_on": "2026-11-08", "caption": "전시 앞"},
            )
            photo = Photo.objects.get()
            self.assertRedirects(response, reverse("photo_detail", args=[photo.pk]))
            self.assertEqual(photo.album.title, "성수동 산책")
            self.assertEqual(photo.uploaded_by, self.a)
            page = self.client.get(reverse("photo_detail", args=[photo.pk]))
            self.assertContains(page, photo.image.url)
            self.assertContains(page, "전시 앞")

    def test_photo_edit_changes_caption_and_album(self):
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            self.client.post(reverse("photo_create"), {"image": self.image_file(), "caption": "처음"})
            photo = Photo.objects.get()
            album = Album.objects.create(couple=self.couple, title="제주 여행")
            self.client.post(reverse("photo_update", args=[photo.pk]), {"album": album.pk, "caption": "고친 한마디", "taken_on": ""})
            photo.refresh_from_db()
            self.assertEqual((photo.album, photo.caption), (album, "고친 한마디"))

    def test_deleting_album_keeps_photos(self):
        album = Album.objects.create(couple=self.couple, title="첫 캠핑")
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            self.client.post(reverse("photo_create"), {"image": self.image_file(), "album": album.pk})
            self.client.post(reverse("album_delete", args=[album.pk]))
        self.assertEqual(Photo.objects.count(), 1)
        self.assertIsNone(Photo.objects.get().album)

    def test_album_pages_render(self):
        self.assertEqual(self.client.get(reverse("albums")).status_code, 200)
        album = Album.objects.create(couple=self.couple, title="첫 캠핑")
        self.assertEqual(self.client.get(reverse("album_detail", args=[album.pk])).status_code, 200)


class HomeDataTests(TestCase):
    def setUp(self):
        self.couple = Couple.objects.create(start_date=timezone.localdate() - timedelta(days=99))
        self.a = User.objects.create_user("a", password="pw", couple=self.couple, nickname="하늘")
        self.b = User.objects.create_user("b", password="pw", couple=self.couple, nickname="바다")
        self.client.force_login(self.a)

    def add_event(self, user, title, scope):
        return services.save_event(
            Event(created_by=user),
            self.couple,
            {"text": title, "date": timezone.localdate() + timedelta(days=2), "start_time": None, "end_time": None, "place": "", "scope": scope, "color": "sky"},
        )

    def test_home_lists_shared_and_own_personal_events_only(self):
        shared = self.add_event(self.a, "공통 데이트", Event.SHARED)
        mine = self.add_event(self.a, "내 운동", Event.PERSONAL)
        partners = self.add_event(self.b, "바다의 개인 약속", Event.PERSONAL)
        response = self.client.get(reverse("home"))
        events = list(response.context["events"])
        self.assertIn(shared, events)
        self.assertIn(mine, events)
        self.assertNotIn(partners, events)

    def test_home_shows_recent_tastes_and_photos(self):
        Taste.objects.create(couple=self.couple, author=self.b, category="영화", title="헤어질 결심")
        Photo.objects.create(couple=self.couple, uploaded_by=self.b, image="photos/x.png")
        response = self.client.get(reverse("home"))
        self.assertContains(response, "헤어질 결심")
        self.assertEqual(len(response.context["photos"]), 1)

    def test_home_empty_state_links_to_create_pages(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, reverse("event_create"))
        self.assertContains(response, reverse("taste_create"))
        self.assertContains(response, reverse("photo_create"))


class TastePhotoTests(TestCase):
    def setUp(self):
        self.couple = Couple.objects.create()
        self.user = User.objects.create_user("a", password="pw", couple=self.couple)
        self.client.force_login(self.user)
        self.media = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media)
        self.override.enable()

    def tearDown(self):
        self.override.disable()

    def image_file(self):
        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        buffer = BytesIO()
        Image.new("RGB", (4, 4), (90, 140, 220)).save(buffer, "PNG")
        return SimpleUploadedFile("cover.png", buffer.getvalue(), content_type="image/png")

    def test_taste_can_be_created_with_a_photo(self):
        response = self.client.post(
            reverse("taste_create"),
            {"category": "음악", "title": "밤편지", "link": "", "comment": "", "image": self.image_file()},
        )
        taste = Taste.objects.get()
        self.assertRedirects(response, reverse("taste_detail", args=[taste.pk]))
        self.assertTrue(taste.image.name)
        self.assertContains(self.client.get(reverse("taste_detail", args=[taste.pk])), taste.image.url)

    def test_taste_without_photo_still_saves(self):
        self.client.post(reverse("taste_create"), {"category": "책", "title": "작은 것들의 신", "link": "", "comment": ""})
        self.assertFalse(Taste.objects.get().image)

    def test_clear_image_removes_the_photo(self):
        taste = Taste.objects.create(couple=self.couple, author=self.user, category="영화", title="헤어질 결심", image=self.image_file())
        self.client.post(
            reverse("taste_update", args=[taste.pk]),
            {"category": "영화", "title": "헤어질 결심", "link": "", "comment": "", "clear_image": "on"},
        )
        taste.refresh_from_db()
        self.assertFalse(taste.image)

    def test_forms_render_drop_zone(self):
        self.assertContains(self.client.get(reverse("taste_create")), 'data-dropzone')
        self.assertContains(self.client.get(reverse("photo_create")), 'data-batch-zone')  # 새로 올리기는 여러 장 칸


class UploadStorageTests(TestCase):
    def setUp(self):
        self.couple = Couple.objects.create()
        self.user = User.objects.create_user("a", password="pw", couple=self.couple)
        self.client.force_login(self.user)
        self.media = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media)
        self.override.enable()

    def tearDown(self):
        self.override.disable()

    def png(self, name="내 사진.png", size=4):
        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        buffer = BytesIO()
        Image.new("RGB", (size, size), (90, 140, 220)).save(buffer, "PNG")
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")

    def test_file_name_is_random_and_kept_per_couple(self):
        self.client.post(reverse("photo_create"), {"image": self.png()})
        photo = Photo.objects.get()
        self.assertTrue(photo.image.name.startswith(f"photos/{self.couple.pk}/"))
        self.assertNotIn("내 사진", photo.image.name)
        self.assertTrue(photo.image.name.endswith(".png"))

    def test_too_large_image_is_rejected(self):
        with patch("couples.storage.MAX_IMAGE_BYTES", 10):
            response = self.client.post(reverse("photo_create"), {"image": self.png()})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Photo.objects.exists())
        self.assertContains(response, "4MB 이하")

    def test_replacing_photo_deletes_the_old_file(self):
        self.client.post(reverse("photo_create"), {"image": self.png()})
        photo = Photo.objects.get()
        old_path = photo.image.path
        self.client.post(reverse("photo_update", args=[photo.pk]), {"image": self.png("two.png", size=6), "caption": ""})
        photo.refresh_from_db()
        self.assertFalse(os.path.exists(old_path))
        self.assertTrue(os.path.exists(photo.image.path))

    def test_removing_taste_photo_deletes_the_file(self):
        taste = Taste.objects.create(couple=self.couple, author=self.user, category="음악", title="밤편지")
        taste.image.save("cover.png", self.png(), save=True)
        old_path = taste.image.path
        self.client.post(reverse("taste_update", args=[taste.pk]), {"category": "음악", "title": "밤편지", "link": "", "comment": "", "clear_image": "on"})
        self.assertFalse(os.path.exists(old_path))


def _png(name="photo.png", color=(200, 80, 90), size=4):
    from io import BytesIO

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (size, size), color).save(buffer, "PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


class BatchUploadAndQuotaTests(TestCase):
    """여러 장 올리기(한 장씩 JSON 요청)와 R2 무료 한도를 지키는 저장 공간·횟수 제한."""

    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        override = override_settings(MEDIA_ROOT=self.media.name)
        override.enable()
        self.addCleanup(override.disable)
        self.couple = Couple.objects.create()
        self.other = Couple.objects.create()
        self.a = User.objects.create_user("a", password="pw", couple=self.couple)
        self.client.force_login(self.a)

    def post_photo(self, **data):
        data.setdefault("image", _png())
        return self.client.post(reverse("photo_create"), data, HTTP_ACCEPT="application/json")

    def test_json_upload_records_size_and_returns_album(self):
        response = self.post_photo(new_album="제주", taken_on="2026-10-03")
        body = response.json()
        self.assertTrue(body["ok"])
        photo = Photo.objects.get(pk=body["id"])
        self.assertGreater(photo.size, 0)
        self.assertEqual(photo.size, photo.image.size)
        self.assertEqual(body["album"], photo.album_id)

    def test_following_photos_go_into_the_same_new_album(self):
        first = self.post_photo(new_album="제주").json()
        second = self.post_photo(album=str(first["album"])).json()
        third = self.post_photo(new_album="제주").json()  # 이름으로 다시 보내도 같은 앨범
        self.assertEqual({first["album"], second["album"], third["album"]}, {first["album"]})
        self.assertEqual(Album.objects.filter(couple=self.couple).count(), 1)

    def test_json_error_when_no_image(self):
        response = self.client.post(reverse("photo_create"), {}, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])
        self.assertTrue(response.json()["error"])

    def test_html_form_still_works_without_script(self):
        response = self.client.post(reverse("photo_create"), {"image": _png()})
        photo = Photo.objects.get()
        self.assertRedirects(response, reverse("photo_detail", args=[photo.pk]))

    def test_per_couple_storage_limit(self):
        Photo.objects.create(couple=self.couple, uploaded_by=self.a, image="x.png", size=1000)
        with override_settings(MEDIA_QUOTA_PER_COUPLE_BYTES=1000 + 10):
            body = self.post_photo().json()
        self.assertFalse(body["ok"])
        self.assertIn("가득", body["error"])
        self.assertEqual(Photo.objects.count(), 1)

    def test_total_storage_limit_counts_every_couple(self):
        b = User.objects.create_user("b", password="pw", couple=self.other)
        Photo.objects.create(couple=self.other, uploaded_by=b, image="x.png", size=5000)
        with override_settings(MEDIA_QUOTA_TOTAL_BYTES=5000 + 10):
            body = self.post_photo().json()
        self.assertFalse(body["ok"])
        self.assertIn("앱 전체", body["error"])

    def test_daily_upload_limit(self):
        with override_settings(MEDIA_UPLOADS_PER_DAY=2):
            self.assertTrue(self.post_photo().json()["ok"])
            self.assertTrue(self.post_photo().json()["ok"])
            body = self.post_photo().json()
        self.assertFalse(body["ok"])
        self.assertIn("오늘은 2장", body["error"])

    def test_deleting_photos_frees_space(self):
        from . import quota

        body = self.post_photo().json()
        used = quota.used_bytes(self.couple)
        self.assertGreater(used, 0)
        self.client.post(reverse("photo_delete", args=[body["id"]]))
        self.assertEqual(quota.used_bytes(self.couple), 0)

    def test_taste_image_counts_toward_storage(self):
        from . import quota

        self.client.post(reverse("taste_create"), {"category": "영화", "title": "패터슨", "image": _png()})
        taste = Taste.objects.get()
        self.assertEqual(taste.image_size, taste.image.size)
        self.assertEqual(quota.used_bytes(self.couple), taste.image_size)
        self.client.post(reverse("taste_update", args=[taste.pk]), {"category": "영화", "title": "패터슨", "clear_image": "on"})
        taste.refresh_from_db()
        self.assertEqual(taste.image_size, 0)

    def test_taste_image_respects_storage_limit(self):
        with override_settings(MEDIA_QUOTA_PER_COUPLE_BYTES=10):
            response = self.client.post(reverse("taste_create"), {"category": "영화", "title": "패터슨", "image": _png()})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Taste.objects.exists())

    def test_upload_page_shows_room_left_and_album_notice(self):
        page = self.client.get(reverse("photo_create"))
        self.assertContains(page, "남은 공간")
        self.assertContains(page, "multiple")
        self.assertContains(page, "data-batch-upload")
        self.assertContains(self.client.get(reverse("albums") + "?uploaded=3"), "사진 3장을 올렸어요")


class DrivePickerButtonTests(TestCase):
    """드라이브에서 가져오기 버튼은 Google 설정이 모두 있을 때만 보인다."""

    def setUp(self):
        self.couple = Couple.objects.create()
        self.client.force_login(User.objects.create_user("a", password="pw", couple=self.couple))

    def test_hidden_without_settings(self):
        with override_settings(DRIVE_PICKER=None):
            self.assertNotContains(self.client.get(reverse("photo_create")), "data-drive-picker")

    def test_shown_with_settings_and_hidden_in_app_browsers(self):
        config = {"client_id": "cid.apps.googleusercontent.com", "api_key": "test-key", "app_id": "123456"}
        with override_settings(DRIVE_PICKER=config):
            page = self.client.get(reverse("photo_create"))
        self.assertContains(page, "Google 드라이브에서 가져오기")
        self.assertContains(page, 'data-client-id="cid.apps.googleusercontent.com"')
        self.assertContains(page, 'data-app-id="123456"')
        self.assertContains(page, "data-drive-picker data-needs-browser")

    def test_not_on_edit_page(self):
        config = {"client_id": "c", "api_key": "k", "app_id": "1"}
        photo = Photo.objects.create(couple=self.couple, uploaded_by=self.couple.members.first(), image="x.png")
        with override_settings(DRIVE_PICKER=config):
            self.assertNotContains(self.client.get(reverse("photo_update", args=[photo.pk])), "data-drive-picker")


class PolishTests(TestCase):
    """1단계 다듬기: 이름표 모아 보기, 만든 사람, 하단 탭 글자, 안내 문구, 확인 창 문구."""

    def setUp(self):
        self.couple = Couple.objects.create(start_date=timezone.localdate() - timedelta(days=99))
        self.a = User.objects.create_user("a", password="pw", couple=self.couple, nickname="하늘")
        self.b = User.objects.create_user("b", password="pw", couple=self.couple, nickname="바다")
        self.client.force_login(self.a)

    def add_event(self, user, text, days, scope=Event.SHARED):
        return services.save_event(
            Event(created_by=user),
            self.couple,
            {"text": text, "date": timezone.localdate() + timedelta(days=days), "start_time": None, "end_time": None, "place": "", "scope": scope, "color": "sky"},
        )

    def test_label_filter_lists_upcoming_then_past(self):
        soon = self.add_event(self.a, "바다 보러 @여행", 3)
        later = self.add_event(self.b, "제주 @여행 #비행기", 40)
        past = self.add_event(self.a, "강릉 @여행", -30)
        other = self.add_event(self.a, "영화 @데이트", 2)
        label = Label.objects.get(couple=self.couple, name="여행")
        response = self.client.get(reverse("calendar"), {"label": label.pk})
        self.assertEqual(response.context["label"], label)
        self.assertEqual(response.context["label_upcoming"], [soon, later])
        self.assertEqual(response.context["label_past"], [past])
        self.assertContains(response, "@여행 일정")
        self.assertIn(other.labels.first(), list(response.context["labels"]))

    def test_label_filter_hides_partners_personal_events(self):
        self.add_event(self.b, "바다 혼자 @운동", 1, Event.PERSONAL)
        mine = self.add_event(self.a, "같이 @운동", 2)
        label = Label.objects.get(couple=self.couple, name="운동")
        response = self.client.get(reverse("calendar"), {"label": label.pk})
        self.assertEqual(response.context["label_upcoming"], [mine])

    def test_other_couples_label_is_ignored(self):
        other = Couple.objects.create()
        stranger = User.objects.create_user("c", password="pw", couple=other)
        services.save_event(Event(created_by=stranger), other, {"text": "비밀 @여행", "date": timezone.localdate(), "start_time": None, "end_time": None, "place": "", "scope": Event.SHARED, "color": "sky"})
        label = Label.objects.get(couple=other)
        response = self.client.get(reverse("calendar"), {"label": label.pk})
        self.assertIsNone(response.context["label"])
        self.assertNotContains(response, "비밀")
        self.assertEqual(self.client.get(reverse("calendar"), {"label": "x"}).status_code, 200)

    def test_label_chips_link_to_filter(self):
        self.add_event(self.a, "바다 @여행", 1)
        label = Label.objects.get(couple=self.couple, name="여행")
        response = self.client.get(reverse("calendar"))
        self.assertContains(response, f'href="{reverse("calendar")}?label={label.pk}"')

    def test_event_shows_who_made_it(self):
        self.add_event(self.a, "내가 만든 일정", 1)
        self.add_event(self.b, "바다가 만든 일정", 2)
        response = self.client.get(reverse("home"))
        self.assertContains(response, 'title="내가 만든 일정"')
        self.assertContains(response, 'title="바다님이 만든 일정"')

    def test_tabbar_has_text_and_flash_notice(self):
        response = self.client.get(reverse("home"))
        for text in ["홈", "캘린더", "추억", "앨범"]:
            self.assertContains(response, f"<span>{text}</span>")
        from django.contrib.messages import get_messages  # noqa: F401
        response = self.client.post(reverse("event_create"), {"text": "확인용", "date": timezone.localdate().isoformat(), "scope": "shared", "color": "sky"}, follow=True)
        if list(response.context["messages"]):
            self.assertContains(response, 'class="notice flash"')

    def test_leave_confirm_has_own_button_label(self):
        response = self.client.get(reverse("us"))
        self.assertContains(response, 'data-confirm-ok="연결 끊기"')


class TasteLikeCommentTests(TestCase):
    """취향 좋아요·댓글."""

    def setUp(self):
        self.couple = Couple.objects.create()
        self.a = User.objects.create_user("a", password="pw", couple=self.couple, nickname="하늘")
        self.b = User.objects.create_user("b", password="pw", couple=self.couple, nickname="바다")
        self.taste = Taste.objects.create(couple=self.couple, author=self.b, category="음악", title="밤편지")
        self.client.force_login(self.a)

    def like(self, **extra):
        return self.client.post(reverse("taste_like", args=[self.taste.pk]), **extra)

    def test_like_toggles(self):
        self.assertRedirects(self.like(), reverse("taste_detail", args=[self.taste.pk]))
        self.assertEqual(self.taste.likes.count(), 1)
        self.like()
        self.assertEqual(self.taste.likes.count(), 0)

    def test_like_json_says_who_likes(self):
        data = self.like(HTTP_ACCEPT="application/json").json()
        self.assertEqual(data, {"liked": True, "count": 1, "text": "내가 좋아해요"})
        TasteLike.objects.create(taste=self.taste, user=self.b)
        data = self.like(HTTP_ACCEPT="application/json").json()
        self.assertEqual(data, {"liked": False, "count": 1, "text": "바다님이 좋아해요"})
        data = self.like(HTTP_ACCEPT="application/json").json()
        self.assertEqual(data["text"], "둘 다 좋아해요")

    def test_detail_shows_like_state(self):
        TasteLike.objects.create(taste=self.taste, user=self.b)
        response = self.client.get(reverse("taste_detail", args=[self.taste.pk]))
        self.assertFalse(response.context["liked"])
        self.assertContains(response, "바다님이 좋아해요")

    def test_comment_create_and_show(self):
        response = self.client.post(reverse("taste_comment_create", args=[self.taste.pk]), {"text": "  이 노래 좋다  "})
        self.assertRedirects(response, reverse("taste_detail", args=[self.taste.pk]) + "#comments", fetch_redirect_response=False)
        comment = self.taste.comments.get()
        self.assertEqual((comment.text, comment.author), ("이 노래 좋다", self.a))
        response = self.client.get(reverse("taste_detail", args=[self.taste.pk]))
        self.assertContains(response, "이 노래 좋다")
        self.assertContains(response, reverse("taste_comment_delete", args=[comment.pk]))

    def test_empty_or_long_comment_is_rejected(self):
        url = reverse("taste_comment_create", args=[self.taste.pk])
        self.assertEqual(self.client.post(url, {"text": "   "}).status_code, 400)
        response = self.client.post(url, {"text": "가" * 301})
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "300자까지", status_code=400)
        self.assertFalse(self.taste.comments.exists())

    def test_only_author_can_delete_comment(self):
        theirs = TasteComment.objects.create(taste=self.taste, author=self.b, text="바다 댓글")
        mine = TasteComment.objects.create(taste=self.taste, author=self.a, text="내 댓글")
        response = self.client.get(reverse("taste_detail", args=[self.taste.pk]))
        self.assertNotContains(response, reverse("taste_comment_delete", args=[theirs.pk]))
        self.assertEqual(self.client.post(reverse("taste_comment_delete", args=[theirs.pk])).status_code, 404)
        self.client.post(reverse("taste_comment_delete", args=[mine.pk]))
        self.assertEqual(list(self.taste.comments.all()), [theirs])

    def test_other_couple_cannot_like_or_comment(self):
        other = Couple.objects.create()
        stranger = User.objects.create_user("c", password="pw", couple=other)
        self.client.force_login(stranger)
        self.assertEqual(self.like().status_code, 404)
        self.assertEqual(self.client.post(reverse("taste_comment_create", args=[self.taste.pk]), {"text": "안녕"}).status_code, 404)
        self.assertFalse(self.taste.likes.exists() or self.taste.comments.exists())

    def test_like_and_comment_need_post(self):
        self.assertEqual(self.client.get(reverse("taste_like", args=[self.taste.pk])).status_code, 405)

    def test_feed_counts(self):
        TasteLike.objects.create(taste=self.taste, user=self.a)
        TasteLike.objects.create(taste=self.taste, user=self.b)
        TasteComment.objects.create(taste=self.taste, author=self.b, text="하나")
        quiet = Taste.objects.create(couple=self.couple, author=self.a, category="영화", title="조용한 취향")
        response = self.client.get(reverse("tastes"))
        tastes = {t.pk: t for t in response.context["tastes"]}
        self.assertEqual((tastes[self.taste.pk].like_count, tastes[self.taste.pk].comment_count, tastes[self.taste.pk].liked), (2, 1, True))
        self.assertEqual((tastes[quiet.pk].like_count, tastes[quiet.pk].comment_count, tastes[quiet.pk].liked), (0, 0, False))
        self.assertContains(response, 'aria-label="좋아요 2"')

    def test_deleting_taste_removes_likes_and_comments(self):
        TasteLike.objects.create(taste=self.taste, user=self.a)
        TasteComment.objects.create(taste=self.taste, author=self.a, text="지워질 댓글")
        self.client.post(reverse("taste_delete", args=[self.taste.pk]))
        self.assertFalse(TasteLike.objects.exists() or TasteComment.objects.exists())


class CalendarFeedTests(TestCase):
    """캘린더 앱 구독(ICS)."""

    def setUp(self):
        from datetime import time
        self.time = time
        self.couple = Couple.objects.create(start_date=timezone.localdate() - timedelta(days=150))
        self.a = User.objects.create_user("a", password="pw", couple=self.couple, nickname="하늘")
        self.b = User.objects.create_user("b", password="pw", couple=self.couple, nickname="바다")
        self.client.force_login(self.a)

    def add(self, user, text, days=1, scope=Event.SHARED, start=None, end=None, place=""):
        return services.save_event(
            Event(created_by=user),
            self.couple,
            {"text": text, "date": timezone.localdate() + timedelta(days=days), "start_time": start, "end_time": end, "place": place, "scope": scope, "color": "sky"},
        )

    def feed_text(self, user=None):
        feed, _ = CalendarFeed.objects.get_or_create(user=user or self.a)
        self.client.logout()  # 캘린더 앱은 로그인하지 않는다
        response = self.client.get(reverse("calendar_feed", args=[feed.token]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/calendar; charset=utf-8")
        return response.content.decode("utf-8")

    def test_page_creates_feed_and_links(self):
        response = self.client.get(reverse("calendar_subscribe"))
        feed = CalendarFeed.objects.get(user=self.a)
        self.assertGreaterEqual(len(feed.token), 40)
        self.assertContains(response, f"webcal://testserver/calendar/feed/{feed.token}.ics")
        self.assertContains(response, "calendar.google.com/calendar/render?cid=webcal")
        self.assertFalse(feed.include_personal)
        self.assertContains(self.client.get(reverse("us")), reverse("calendar_subscribe"))

    def test_shared_only_by_default(self):
        self.add(self.a, "같이 저녁 @데이트", place="성수, 2층")
        self.add(self.a, "내 운동", scope=Event.PERSONAL)
        self.add(self.b, "바다 개인 약속", scope=Event.PERSONAL)
        text = self.feed_text()
        self.assertIn("SUMMARY:같이 저녁", text)
        self.assertIn("LOCATION:성수\, 2층", text)
        self.assertIn("@데이트", text)
        self.assertNotIn("내 운동", text)
        self.assertNotIn("바다 개인 약속", text)

    def test_include_personal_adds_only_my_personal(self):
        self.client.post(reverse("calendar_subscribe"), {"action": "personal", "include_personal": "on"})
        self.assertTrue(CalendarFeed.objects.get(user=self.a).include_personal)
        self.add(self.a, "내 운동", scope=Event.PERSONAL)
        self.add(self.b, "바다 개인 약속", scope=Event.PERSONAL)
        text = self.feed_text()
        self.assertIn("SUMMARY:내 운동 (개인)", text)
        self.assertIn("CLASS:PRIVATE", text)
        self.assertNotIn("바다 개인 약속", text)
        # 끄면 다시 공통만
        self.client.force_login(self.a)
        self.client.post(reverse("calendar_subscribe"), {"action": "personal"})
        self.assertNotIn("내 운동", self.feed_text())

    def test_times_all_day_and_overnight(self):
        t = self.time
        self.add(self.a, "하루 종일 일정", days=3)
        self.add(self.a, "저녁", days=3, start=t(19, 0), end=t(21, 30))
        self.add(self.a, "밤샘", days=3, start=t(22, 0), end=t(1, 0))
        self.add(self.a, "끝 없음", days=3, start=t(9, 0))
        d = timezone.localdate() + timedelta(days=3)
        nxt = d + timedelta(days=1)
        text = self.feed_text()
        self.assertIn(f"DTSTART;VALUE=DATE:{d:%Y%m%d}\r\nDTEND;VALUE=DATE:{nxt:%Y%m%d}", text)
        self.assertIn(f"DTSTART:{d:%Y%m%d}T100000Z\r\nDTEND:{d:%Y%m%d}T123000Z", text)  # 서울 19시 = UTC 10시
        self.assertIn(f"DTSTART:{d:%Y%m%d}T130000Z\r\nDTEND:{d:%Y%m%d}T160000Z", text)  # 22시 ~ 다음 날 1시
        self.assertIn(f"DTSTART:{d:%Y%m%d}T000000Z\r\nDTEND:{d:%Y%m%d}T010000Z", text)  # 끝이 없으면 1시간

    def test_anniversaries_included(self):
        from anniversaries.models import Anniversary
        Anniversary.objects.create(couple=self.couple, title="바다 생일", date=timezone.localdate() - timedelta(days=3000), repeat_yearly=True)
        text = self.feed_text()
        self.assertIn("SUMMARY:바다 생일\r\nTRANSP:TRANSPARENT\r\nRRULE:FREQ=YEARLY", text)
        self.assertIn("SUMMARY:우리 200일", text)

    def test_format_crlf_and_folding(self):
        self.add(self.a, "아주 긴 제목 " * 12)
        text = self.feed_text()
        self.assertTrue(text.startswith("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"))
        self.assertTrue(text.endswith("END:VCALENDAR\r\n"))
        self.assertNotIn("\n", text.replace("\r\n", ""))
        for line in text.split("\r\n"):
            self.assertLessEqual(len(line.encode("utf-8")), 75)
        unfolded = text.replace("\r\n ", "")
        self.assertIn("SUMMARY:" + ("아주 긴 제목 " * 12).strip(), unfolded)

    def test_reset_token_blocks_old_url(self):
        feed = CalendarFeed.objects.create(user=self.a)
        old = feed.token
        self.client.post(reverse("calendar_subscribe"), {"action": "reset"})
        feed.refresh_from_db()
        self.assertNotEqual(feed.token, old)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("calendar_feed", args=[old])).status_code, 404)
        self.assertEqual(self.client.get(reverse("calendar_feed", args=[feed.token])).status_code, 200)

    def test_unknown_token_is_404(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("calendar_feed", args=["nope"])).status_code, 404)

    def test_after_leaving_couple_feed_is_empty(self):
        self.add(self.a, "같이 저녁")
        feed = CalendarFeed.objects.create(user=self.a)
        self.a.couple = None
        self.a.save()
        self.client.logout()
        text = self.client.get(reverse("calendar_feed", args=[feed.token])).content.decode()
        self.assertNotIn("BEGIN:VEVENT", text)

    def test_other_couples_events_never_in_feed(self):
        other = Couple.objects.create()
        stranger = User.objects.create_user("c", password="pw", couple=other)
        services.save_event(Event(created_by=stranger), other, {"text": "남의 일정", "date": timezone.localdate(), "start_time": None, "end_time": None, "place": "", "scope": Event.SHARED, "color": "sky"})
        self.assertNotIn("남의 일정", self.feed_text())


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "linkpreview-tests"}})
class LinkPreviewTests(TestCase):
    """취향 링크 미리보기. 인터넷에는 나가지 않고 fetch 를 가짜로 바꾼다."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.couple = Couple.objects.create()
        self.a = User.objects.create_user("a", password="pw", couple=self.couple, nickname="하늘")
        self.client.force_login(self.a)

    def test_embed_urls(self):
        from .linkpreview import embed_for
        yt = "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"
        for url in [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10",
            "https://youtu.be/dQw4w9WgXcQ?si=abc",
            "https://m.youtube.com/shorts/dQw4w9WgXcQ",
            "https://music.youtube.com/watch?v=dQw4w9WgXcQ",
        ]:
            self.assertEqual(embed_for(url), (yt, 0), url)
        self.assertEqual(
            embed_for("https://open.spotify.com/intl-ko/track/4uLU6hMCjMI75M1A2tKUQC?si=x"),
            ("https://open.spotify.com/embed/track/4uLU6hMCjMI75M1A2tKUQC", 152),
        )
        self.assertEqual(embed_for("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M")[1], 352)
        for url in ["https://www.youtube.com/watch?v=bad", "https://evil.com/watch?v=dQw4w9WgXcQ",
                    "https://open.spotify.com/user/x", "", "javascript:alert(1)"]:
            self.assertEqual(embed_for(url), ("", 0), url)

    def test_guess_category(self):
        from .linkpreview import guess_category
        self.assertEqual(guess_category("https://open.spotify.com/track/x"), "음악")
        self.assertEqual(guess_category("https://music.youtube.com/watch?v=x"), "음악")
        self.assertEqual(guess_category("https://youtu.be/x"), "영상")
        self.assertEqual(guess_category("https://www.netflix.com/title/1"), "영화")
        self.assertEqual(guess_category("https://naver.me/abc"), "장소")
        self.assertEqual(guess_category("https://example.com"), "")

    def test_blocks_private_addresses(self):
        from .linkpreview import UnsafeURL, check_public
        for url in ["http://127.0.0.1/", "http://localhost/", "http://10.0.0.5/", "http://169.254.169.254/latest/meta-data/",
                    "http://[::1]/", "ftp://example.com/", "http://user:pw@example.com/", "http://example.com:8080/"]:
            with self.assertRaises(UnsafeURL, msg=url):
                check_public(url)

    def test_redirect_to_private_address_is_blocked(self):
        from urllib.error import HTTPError
        from . import linkpreview

        calls = []

        def fake_check(url):
            if "127.0.0.1" in url:
                raise linkpreview.UnsafeURL("내부 주소")

        def fake_open(request, timeout):
            calls.append(request.full_url)
            raise HTTPError(request.full_url, 302, "Found", {"Location": "http://127.0.0.1/admin"}, None)

        with patch.object(linkpreview, "check_public", side_effect=fake_check), \
                patch.object(linkpreview._opener, "open", side_effect=fake_open):
            self.assertTrue(linkpreview.get_preview("https://short.example/x").empty)
        self.assertEqual(calls, ["https://short.example/x"])  # 넘겨준 내부 주소로는 요청하지 않았다

    def test_open_graph_page(self):
        html = (
            '<html><head><meta charset="utf-8"><title>예비 제목</title>'
            '<meta property="og:title" content="성수 카페 &amp; 서점">'
            '<meta property="og:image" content="/img/cover.jpg">'
            '<meta property="og:site_name" content="네이버 지도"></head><body></body></html>'
        ).encode("utf-8")
        with patch("couples.linkpreview.fetch", return_value=("https://map.naver.com/p/1", "text/html; charset=utf-8", html)):
            p = self.client.get(reverse("taste_link_preview"), {"url": "https://map.naver.com/p/1"}).json()
        self.assertEqual(
            (p["ok"], p["title"], p["image"], p["site"], p["category"]),
            (True, "성수 카페 & 서점", "https://map.naver.com/img/cover.jpg", "네이버 지도", "장소"),
        )

    def test_title_fallback_and_http_image_dropped(self):
        from .linkpreview import get_preview
        html = "<html><head><title>  그냥   제목 </title><meta property='og:image' content='http://plain.example/a.jpg'></head></html>".encode("euc-kr")
        with patch("couples.linkpreview.fetch", return_value=("https://www.example.co.kr/a", "text/html; charset=euc-kr", html)):
            p = get_preview("https://www.example.co.kr/a")
        self.assertEqual((p.title, p.image, p.site), ("그냥 제목", "", "example.co.kr"))

    def test_youtube_uses_oembed(self):
        body = b'{"title": "Hype Boy", "author_name": "HYBE LABELS", "thumbnail_url": "https://i.ytimg.com/vi/x/hqdefault.jpg"}'
        with patch("couples.linkpreview.fetch", return_value=("", "application/json", body)) as fetch:
            p = self.client.get(reverse("taste_link_preview"), {"url": "https://youtu.be/dQw4w9WgXcQ"}).json()
        self.assertIn("https://www.youtube.com/oembed?url=", fetch.call_args[0][0])
        self.assertEqual(
            (p["title"], p["site"], p["category"], p["embed"]),
            ("Hype Boy · HYBE LABELS", "YouTube", "영상", "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"),
        )

    def test_failure_returns_empty_and_saves_taste(self):
        with patch("couples.linkpreview.fetch", side_effect=OSError("down")):
            p = self.client.get(reverse("taste_link_preview"), {"url": "https://example.com/x"}).json()
            self.assertFalse(p["ok"])
            response = self.client.post(reverse("taste_create"), {"category": "영화", "title": "직접 쓴 제목", "link": "https://example.com/x", "comment": ""})
        taste = Taste.objects.get()
        self.assertRedirects(response, reverse("taste_detail", args=[taste.pk]))
        self.assertEqual((taste.title, taste.preview_title), ("직접 쓴 제목", ""))

    def test_saving_stores_preview_once(self):
        html = b'<html><head><meta property="og:title" content="Film"><meta property="og:image" content="https://cdn.example/p.jpg"></head></html>'
        with patch("couples.linkpreview.fetch", return_value=("https://example.com/f", "text/html", html)) as fetch:
            self.client.post(reverse("taste_create"), {"category": "영화", "title": "헤어질 결심", "link": "https://example.com/f", "comment": ""})
            taste = Taste.objects.get()
            self.assertEqual((taste.preview_title, taste.preview_image), ("Film", "https://cdn.example/p.jpg"))
            # 링크를 안 바꾸고 고치면 다시 가져오지 않는다
            self.client.post(reverse("taste_update", args=[taste.pk]), {"category": "영화", "title": "헤어질 결심", "link": "https://example.com/f", "comment": "좋았어"})
            self.assertEqual(fetch.call_count, 1)
            # 링크를 지우면 미리보기도 지운다
            self.client.post(reverse("taste_update", args=[taste.pk]), {"category": "영화", "title": "헤어질 결심", "link": "", "comment": ""})
        taste.refresh_from_db()
        self.assertEqual((taste.preview_title, taste.preview_image), ("", ""))

    def test_feed_and_detail_show_preview(self):
        taste = Taste.objects.create(
            couple=self.couple, author=self.a, category="음악", title="밤편지",
            link="https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC",
            preview_title="밤편지 · 아이유", preview_image="https://i.scdn.co/image/x", preview_site="Spotify",
        )
        feed = self.client.get(reverse("tastes"))
        self.assertContains(feed, 'src="https://i.scdn.co/image/x"')
        self.assertContains(feed, 'referrerpolicy="no-referrer"')
        detail = self.client.get(reverse("taste_detail", args=[taste.pk]))
        self.assertContains(detail, 'src="https://open.spotify.com/embed/track/4uLU6hMCjMI75M1A2tKUQC"')
        self.assertContains(detail, "밤편지 · 아이유")

    def test_preview_needs_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("taste_link_preview"), {"url": "https://example.com"}).status_code, 302)


class EventMemoAndAlbumTabTests(TestCase):
    """일정 메모, 앨범 첫 화면(전체 사진)."""

    setUp = ScreenTests.setUp
    event_form = ScreenTests.event_form

    def test_event_memo_saved_shown_and_editable(self):
        memo = "예약 번호 1234\n우산 챙기기"
        self.client.post(reverse("event_create"), self.event_form(memo=memo))
        event = Event.objects.get()
        self.assertEqual(event.memo, memo)
        calendar = self.client.get(reverse("calendar"))
        self.assertContains(calendar, "예약 번호 1234")
        edit = self.client.get(reverse("event_update", args=[event.pk]))
        self.assertContains(edit, "예약 번호 1234")
        self.client.post(reverse("event_update", args=[event.pk]), self.event_form(memo=""))
        event.refresh_from_db()
        self.assertEqual(event.memo, "")

    def test_past_event_is_read_only_but_deletable(self):
        """지난 일정(오늘보다 전)은 보기만, 지우기는 된다."""
        yesterday = timezone.localdate() - timedelta(days=1)
        event = Event.objects.create(couple=self.couple, created_by=self.a, title="지난 전시", date=yesterday)
        url = reverse("event_update", args=[event.pk])
        page = self.client.get(url)
        self.assertContains(page, "지난 일정은 고칠 수 없어요")
        self.assertContains(page, "<fieldset disabled")
        self.assertNotContains(page, '<button type="submit" class="btn primary">')
        res = self.client.post(url, self.event_form(text="바꾼 이름", date=timezone.localdate().isoformat()))
        event.refresh_from_db()
        self.assertEqual((event.title, event.date), ("지난 전시", yesterday))
        self.assertEqual(res.status_code, 302)
        self.client.post(reverse("event_delete", args=[event.pk]))
        self.assertFalse(Event.objects.exists())

    def test_today_event_still_editable(self):
        event = Event.objects.create(couple=self.couple, created_by=self.a, title="오늘 일정", date=timezone.localdate())
        page = self.client.get(reverse("event_update", args=[event.pk]))
        self.assertNotContains(page, "지난 일정은 고칠 수 없어요")
        self.client.post(reverse("event_update", args=[event.pk]), self.event_form(text="바꾼 오늘 일정"))
        event.refresh_from_db()
        self.assertEqual(event.title, "바꾼 오늘 일정")

    def test_event_memo_too_long_rejected(self):
        res = self.client.post(reverse("event_create"), self.event_form(memo="가" * 1001))
        self.assertEqual(res.status_code, 200)
        self.assertFalse(Event.objects.exists())

    def test_event_memo_in_calendar_feed(self):
        from .ics import build_calendar
        from .models import CalendarFeed

        self.client.post(reverse("event_create"), self.event_form(memo="우산 챙기기"))
        feed = CalendarFeed.objects.create(user=self.a)
        self.assertIn("우산 챙기기", build_calendar(feed))

    def test_album_opens_on_all_photos(self):
        html = self.client.get(reverse("albums")).content.decode()
        self.assertIn('<section class="view on" id="album-photos">', html)
        self.assertIn('<section class="view" id="album-albums">', html)
        self.assertLess(html.index('data-target="album-photos"'), html.index('data-target="album-albums"'))


class LoginRequiredTests(TestCase):
    """로그인하지 않고 열면 오류 대신 로그인 화면으로."""

    def test_album_redirects_to_login(self):
        res = self.client.get(reverse("albums"))
        self.assertEqual(res.status_code, 302)
        self.assertIn(reverse("account_login"), res["Location"])


def gps_jpeg(name="gps.jpg", with_gps=True, size=8):
    """성수(37°32'40.2"N, 127°03'21.6"E = 37.5445, 127.056) 촬영 위치가 든 시험용 JPEG."""
    from io import BytesIO

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image
    from PIL.TiffImagePlugin import IFDRational as R

    exif = Image.Exif()
    if with_gps:
        exif[0x8825] = {1: "N", 2: (R(37), R(32), R(402, 10)), 3: "E", 4: (R(127), R(3), R(216, 10))}
    buffer = BytesIO()
    Image.new("RGB", (size, size), (200, 120, 90)).save(buffer, "JPEG", exif=exif)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


class PhotoLocationTests(TestCase):
    """사진 촬영 위치 저장 (couples/geo.py)."""

    setUp = UploadStorageTests.setUp
    tearDown = UploadStorageTests.tearDown
    png = UploadStorageTests.png

    def test_clean_coords(self):
        from .geo import clean_coords

        self.assertEqual(clean_coords("37.5", "127.0"), (37.5, 127.0))
        for bad in [(91, 0), ("37.5", ""), (0, 0), ("abc", "1"), (None, None), ("37", "181")]:
            self.assertIsNone(clean_coords(*bad), bad)

    def test_gps_from_jpeg(self):
        from .geo import gps_from_image

        lat, lng = gps_from_image(gps_jpeg())
        self.assertAlmostEqual(lat, 37.5445, places=4)
        self.assertAlmostEqual(lng, 127.056, places=4)

    def test_gps_from_broken_or_png(self):
        from io import BytesIO

        from .geo import gps_from_image

        self.assertIsNone(gps_from_image(self.png()))
        self.assertIsNone(gps_from_image(BytesIO(b"")))
        self.assertIsNone(gps_from_image(BytesIO(b"not an image")))
        self.assertIsNone(gps_from_image(gps_jpeg(with_gps=False)))

    def upload(self, image, **extra):
        self.client.post(reverse("photo_create"), {"image": image, **extra})
        return Photo.objects.latest("pk")

    def test_upload_uses_form_coords_first(self):
        photo = self.upload(gps_jpeg(), latitude="35.1", longitude="129.0")
        self.assertEqual((photo.latitude, photo.longitude), (35.1, 129.0))
        self.assertTrue(photo.has_location)

    def test_upload_falls_back_to_exif(self):
        photo = self.upload(gps_jpeg())
        self.assertAlmostEqual(photo.latitude, 37.5445, places=4)
        self.assertAlmostEqual(photo.longitude, 127.056, places=4)

    def test_upload_bad_form_coords_fall_back_to_exif(self):
        photo = self.upload(gps_jpeg(), latitude="0", longitude="0")
        self.assertAlmostEqual(photo.latitude, 37.5445, places=4)

    def test_upload_without_location_succeeds(self):
        photo = self.upload(self.png())
        self.assertIsNone(photo.latitude)
        self.assertIsNone(photo.longitude)
        self.assertFalse(photo.has_location)

    def test_edit_without_new_file_keeps_location(self):
        photo = self.upload(gps_jpeg())
        self.client.post(reverse("photo_update", args=[photo.pk]), {"caption": "한마디만", "latitude": "", "longitude": ""})
        photo.refresh_from_db()
        self.assertEqual(photo.caption, "한마디만")
        self.assertAlmostEqual(photo.latitude, 37.5445, places=4)


class FillLocationsCommandTests(TestCase):
    """이미 올린 사진의 위치 채우기 (fill_photo_locations)."""

    setUp = UploadStorageTests.setUp
    tearDown = UploadStorageTests.tearDown
    png = UploadStorageTests.png

    def make(self, image, **fields):
        return Photo.objects.create(couple=self.couple, uploaded_by=self.user, image=image, **fields)

    def run_command(self, *args):
        import io

        from django.core.management import call_command

        out = io.StringIO()
        call_command("fill_photo_locations", *args, stdout=out)
        return out.getvalue().strip().splitlines()[-1]

    def test_dry_run_and_fill(self):
        gps = self.make(gps_jpeg())
        plain = self.make(self.png())
        known = self.make(gps_jpeg(name="known.jpg"), latitude=35.0, longitude=129.0)

        self.assertEqual(self.run_command("--dry-run"), "(시험) 위치를 찾은 사진 1장 / 살펴본 사진 2장")
        gps.refresh_from_db()
        self.assertIsNone(gps.latitude)

        self.assertEqual(self.run_command(), "위치를 찾은 사진 1장 / 살펴본 사진 2장")
        gps.refresh_from_db(); plain.refresh_from_db(); known.refresh_from_db()
        self.assertAlmostEqual(gps.latitude, 37.5445, places=4)
        self.assertIsNone(plain.latitude)
        self.assertEqual((known.latitude, known.longitude), (35.0, 129.0))

    def test_missing_file_is_skipped(self):
        photo = self.make(gps_jpeg())
        photo.image.storage.delete(photo.image.name)
        self.assertEqual(self.run_command(), "위치를 찾은 사진 0장 / 살펴본 사진 1장")


class PlaceLinkTests(TestCase):
    """장소 위치와 사진 자동 연결 (couples/places.py). 찍은 위치 기준 200m 안 가장 가까운 장소."""

    setUp = UploadStorageTests.setUp
    tearDown = UploadStorageTests.tearDown
    png = UploadStorageTests.png

    def place(self, lat, lng, couple=None, title="장소"):
        return Taste.objects.create(
            couple=couple or self.couple, author=self.user, category=Taste.PLACE, title=title, latitude=lat, longitude=lng
        )

    def photo(self, lat=None, lng=None, **fields):
        return Photo.objects.create(couple=self.couple, uploaded_by=self.user, image=self.png(), latitude=lat, longitude=lng, **fields)

    def test_distance(self):
        from .places import distance_m

        self.assertAlmostEqual(distance_m(37.5445, 127.056, 37.5445, 127.0583), 203, delta=2)

    def test_nearest_and_ties(self):
        from .places import nearest_place

        a = self.place(37.5445, 127.056, title="A")
        b = self.place(37.5455, 127.056, title="B")
        self.assertEqual(nearest_place(self.couple, 37.5450, 127.056), a)  # 거리 같음 → 먼저 만든 것
        self.assertEqual(nearest_place(self.couple, 37.5460, 127.056), b)
        self.assertIsNone(nearest_place(self.couple, 37.5445, 127.060))  # 약 350m

    def test_ignores_other_couple_and_moments(self):
        from .places import nearest_place

        other = Couple.objects.create()
        stranger = User.objects.create_user("z", password="pw", couple=other)
        Taste.objects.create(couple=other, author=stranger, category=Taste.PLACE, title="남의 곳", latitude=37.5445, longitude=127.056)
        Taste.objects.create(couple=self.couple, author=self.user, category="음악", title="노래", latitude=37.5445, longitude=127.056)
        self.assertIsNone(nearest_place(self.couple, 37.5445, 127.056))

    def test_relink_keeps_manual_and_handles_delete(self):
        from .places import relink

        a = self.place(37.5445, 127.056, title="A")
        auto = self.photo(37.5446, 127.056)
        manual = self.photo(37.5446, 127.056, place=None, place_manual=True)
        self.assertEqual(relink(self.couple), 1)
        auto.refresh_from_db(); manual.refresh_from_db()
        self.assertEqual(auto.place, a)
        self.assertIsNone(manual.place)

        b = self.place(37.5450, 127.056, title="B")  # 약 44m 떨어진 새 장소
        a.delete()
        relink(self.couple)
        auto.refresh_from_db(); manual.refresh_from_db()
        self.assertEqual(auto.place, b)
        self.assertTrue(manual.place_manual)
        self.assertIsNone(manual.place)

        b.delete()
        relink(self.couple)
        auto.refresh_from_db()
        self.assertIsNone(auto.place)

    def test_upload_links_to_place(self):
        seongsu = self.place(37.5445, 127.056, title="성수")
        self.client.post(reverse("photo_create"), {"image": gps_jpeg()})
        self.assertEqual(Photo.objects.latest("pk").place, seongsu)


from unittest import mock  # noqa: E402


@override_settings(KAKAO_CLIENT_ID="rest-key", CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "place-search-tests"}})
class PlaceSearchTests(TestCase):
    """장소 검색: 카카오 먼저, 3개 미만이면 OpenStreetMap(Nominatim) 을 뒤에."""

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.couple = Couple.objects.create()
        self.user = User.objects.create_user("s", password="pw", couple=self.couple)
        self.client.force_login(self.user)

    def kakao(self, n):
        docs = [{"place_name": f"카페{i}", "road_address_name": f"서울 성동구 {i}", "address_name": "", "y": "37.5", "x": "127.0", "place_url": f"https://place.map.kakao.com/{i}"} for i in range(n)]
        return {"documents": docs}

    OSM = [{"name": "Tour Eiffel", "display_name": "Tour Eiffel, Paris, France", "lat": "48.858", "lon": "2.294"}]

    def fake(self, kakao_n=0, kakao_error=False, osm_error=False):
        calls = []

        def http_json(url, headers=None):
            calls.append(url)
            if "dapi.kakao.com" in url:
                if kakao_error:
                    raise OSError("down")
                self.assertEqual(headers.get("Authorization"), "KakaoAK rest-key")
                return self.kakao(kakao_n)
            if osm_error:
                raise OSError("down")
            return self.OSM

        return calls, http_json

    def search(self, q, **kw):
        from . import placesearch

        calls, fake = self.fake(**kw)
        with mock.patch.object(placesearch, "_http_json", side_effect=fake):
            return placesearch.search(q), calls

    def test_enough_kakao_results_only(self):
        results, calls = self.search("성수 카페", kakao_n=4)
        self.assertEqual([r["source"] for r in results], ["kakao"] * 4)
        self.assertEqual(results[0], {"name": "카페0", "address": "서울 성동구 0", "lat": 37.5, "lng": 127.0, "url": "https://place.map.kakao.com/0", "source": "kakao"})
        self.assertEqual(len(calls), 1)

    def test_few_kakao_then_osm(self):
        results, _ = self.search("에펠탑", kakao_n=1)
        self.assertEqual([r["source"] for r in results], ["kakao", "osm"])
        self.assertEqual(results[1]["name"], "Tour Eiffel")
        self.assertEqual((results[1]["lat"], results[1]["lng"]), (48.858, 2.294))

    def test_errors_give_empty(self):
        results, _ = self.search("에펠탑", kakao_error=True)
        self.assertEqual([r["source"] for r in results], ["osm"])
        from django.core.cache import cache

        cache.clear()
        results, _ = self.search("아무곳", kakao_error=True, osm_error=True)
        self.assertEqual(results, [])

    def test_no_kakao_key_skips_kakao(self):
        with override_settings(KAKAO_CLIENT_ID=""):
            results, calls = self.search("에펠탑")
        self.assertTrue(all("dapi.kakao.com" not in c for c in calls))
        self.assertEqual(len(results), 1)

    def test_osm_cached(self):
        _, first = self.search("에펠탑", kakao_n=0)
        _, second = self.search("에펠탑", kakao_n=0)
        self.assertEqual(sum("nominatim" in c for c in first), 1)
        self.assertEqual(sum("nominatim" in c for c in second), 0)

    def test_bad_query(self):
        self.assertEqual(self.search("가" * 61)[0], [])
        self.assertEqual(self.search("   ")[0], [])

    def test_endpoint(self):
        from . import placesearch

        with mock.patch.object(placesearch, "search", return_value=[{"name": "x"}]) as s:
            res = self.client.get(reverse("place_search"), {"q": " 성수 "})
        self.assertEqual(res.json(), {"results": [{"name": "x"}]})
        s.assert_called_once_with(" 성수 ")
        self.client.logout()
        self.assertEqual(self.client.get(reverse("place_search"), {"q": "a"}).status_code, 302)


class MomentPlaceFormTests(TestCase):
    """순간 쓰기(태그 하나)와 장소 기록하기(위치)."""

    setUp = UploadStorageTests.setUp
    tearDown = UploadStorageTests.tearDown
    png = UploadStorageTests.png

    def test_moment_form_has_tags_not_place(self):
        html = self.client.get(reverse("taste_create")).content.decode()
        for tag in Taste.MOMENT_TAGS:
            self.assertIn(f'value="{tag}"', html)
        self.assertNotIn('value="장소"', html)
        self.assertNotIn("data-place-picker", html)

    def test_moment_needs_tag(self):
        res = self.client.post(reverse("taste_create"), {"title": "노래"})
        self.assertContains(res, "태그를 하나 골라 주세요.")
        res = self.client.post(reverse("taste_create"), {"title": "곳", "category": "장소"})
        self.assertFalse(Taste.objects.exists())

    def test_place_create_saves_location(self):
        res = self.client.post(
            reverse("taste_create") + "?kind=place",
            {"title": "대림창고", "latitude": "37.5418", "longitude": "127.0565", "address": "서울 성동구 성수이로 78", "place_url": "https://place.map.kakao.com/1"},
        )
        place = Taste.objects.get()
        self.assertRedirects(res, reverse("taste_detail", args=[place.pk]))
        self.assertEqual((place.category, place.latitude, place.longitude, place.address), ("장소", 37.5418, 127.0565, "서울 성동구 성수이로 78"))

    def test_place_zero_coords_is_no_location(self):
        self.client.post(reverse("taste_create") + "?kind=place", {"title": "어딘가", "latitude": "0", "longitude": "0"})
        self.assertFalse(Taste.objects.get().has_location)

    def test_place_form_page_has_picker(self):
        self.assertContains(self.client.get(reverse("taste_create") + "?kind=place"), "data-place-picker")

    def test_from_photo_links_my_photo_only(self):
        mine = Photo.objects.create(couple=self.couple, uploaded_by=self.user, image=self.png(), latitude=37.5, longitude=127.0)
        other = Couple.objects.create()
        stranger = User.objects.create_user("z", password="pw", couple=other)
        theirs = Photo.objects.create(couple=other, uploaded_by=stranger, image=self.png(), latitude=37.5, longitude=127.0)
        self.client.post(reverse("taste_create") + "?kind=place", {"title": "a", "latitude": "37.5", "longitude": "127.0", "from_photo": str(theirs.pk)})
        theirs.refresh_from_db()
        self.assertIsNone(theirs.place)
        self.client.post(reverse("taste_create") + "?kind=place", {"title": "b", "latitude": "37.5", "longitude": "127.0", "from_photo": str(mine.pk)})
        mine.refresh_from_db()
        self.assertEqual(mine.place.title, "b")
        self.assertTrue(mine.place_manual)

    def test_edit_uses_matching_form(self):
        place = Taste.objects.create(couple=self.couple, author=self.user, category="장소", title="곳")
        moment = Taste.objects.create(couple=self.couple, author=self.user, category="음악", title="노래")
        self.assertContains(self.client.get(reverse("taste_update", args=[place.pk])), "data-place-picker")
        html = self.client.get(reverse("taste_update", args=[moment.pk])).content.decode()
        self.assertIn('value="음악"', html)
        self.assertNotIn("data-place-picker", html)
        # 장소 글을 고쳐도 분류는 장소 그대로
        self.client.post(reverse("taste_update", args=[place.pk]), {"title": "곳2", "category": "음악"})
        place.refresh_from_db()
        self.assertEqual((place.title, place.category), ("곳2", "장소"))

    def test_place_save_links_nearby_photos(self):
        photo = Photo.objects.create(couple=self.couple, uploaded_by=self.user, image=self.png(), latitude=37.5419, longitude=127.0566)
        self.client.post(reverse("taste_create") + "?kind=place", {"title": "대림창고", "latitude": "37.5418", "longitude": "127.0565"})
        photo.refresh_from_db()
        self.assertEqual(photo.place.title, "대림창고")
        self.assertFalse(photo.place_manual)

    def test_place_delete_unlinks(self):
        place = Taste.objects.create(couple=self.couple, author=self.user, category="장소", title="곳", latitude=37.5, longitude=127.0)
        photo = Photo.objects.create(couple=self.couple, uploaded_by=self.user, image=self.png(), latitude=37.5, longitude=127.0, place=place)
        self.client.post(reverse("taste_delete", args=[place.pk]))
        photo.refresh_from_db()
        self.assertIsNone(photo.place)


class MemoriesScreenTests(TestCase):
    """추억 화면(순간·기록), 이름 바꾸기, 앨범 지도 정리."""

    setUp = UploadStorageTests.setUp
    tearDown = UploadStorageTests.tearDown
    png = UploadStorageTests.png

    def make(self, category, title, **fields):
        return Taste.objects.create(couple=self.couple, author=self.user, category=category, title=title, **fields)

    def test_moment_tab_default_hides_places(self):
        self.make("음악", "밤편지")
        self.make("장소", "대림창고", latitude=37.54, longitude=127.05)
        html = self.client.get(reverse("tastes")).content.decode()
        self.assertIn("밤편지", html)
        self.assertNotIn("대림창고", html)
        for chip in ["전체", *Taste.MOMENT_TAGS]:
            self.assertIn(f">{chip}<", html)
        self.assertIn("순간 남기기", html)

    def test_record_tab_lists_places(self):
        self.make("음악", "밤편지")
        place = self.make("장소", "대림창고", latitude=37.54, longitude=127.05)
        self.make("장소", "옛날 곳")  # 위치 없음
        Photo.objects.create(couple=self.couple, uploaded_by=self.user, image=self.png(), place=place)
        html = self.client.get(reverse("tastes") + "?tab=record").content.decode()
        self.assertIn("대림창고", html)
        self.assertIn("옛날 곳", html)
        self.assertIn("위치 넣기", html)
        self.assertIn("data-record-map", html)
        self.assertIn("사진 1장", html)
        self.assertNotIn("밤편지", html)
        self.assertIn(reverse("taste_create") + "?kind=place", html)

    def test_place_map_data(self):
        mine = self.make("장소", "대림창고", latitude=37.54, longitude=127.05, address="성수")
        self.make("장소", "옛날 곳")
        other = Couple.objects.create()
        stranger = User.objects.create_user("z", password="pw", couple=other)
        Taste.objects.create(couple=other, author=stranger, category="장소", title="남의 곳", latitude=1, longitude=1)
        data = self.client.get(reverse("place_map_data")).json()["places"]
        self.assertEqual([p["id"] for p in data], [mine.pk])
        self.assertEqual(set(data[0]), {"id", "name", "lat", "lng", "photos", "url", "address"})
        self.client.logout()
        self.assertEqual(self.client.get(reverse("place_map_data")).status_code, 302)

    def test_old_album_map_redirects(self):
        res = self.client.get(reverse("albums") + "?view=map&focus=37.5,127.0")
        self.assertRedirects(res, reverse("tastes") + "?tab=record&focus=37.5,127.0", fetch_redirect_response=False)
        self.assertEqual(self.client.get("/albums/map/data/").status_code, 404)
        html = self.client.get(reverse("albums")).content.decode()
        self.assertNotIn("album-map", html)
        self.assertNotIn("js/map.js", html)

    def test_names_and_quick_menu(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertIn("<span>추억</span>", html)
        self.assertNotIn("<span>취향</span>", html)
        self.assertIn("최근 남긴 추억", html)
        self.assertIn(">순간</a>", html)
        self.assertIn(">기록</a>", html)

    def test_moment_likes_kept(self):
        song = self.make("음악", "밤편지")
        TasteLike.objects.create(taste=song, user=self.user)
        self.assertContains(self.client.get(reverse("tastes")), 'aria-label="좋아요 1"')

    def test_photo_detail_place_and_map_links(self):
        place = self.make("장소", "대림창고", latitude=37.54, longitude=127.05)
        linked = Photo.objects.create(couple=self.couple, uploaded_by=self.user, image=self.png(), latitude=37.54, longitude=127.05, place=place)
        located = Photo.objects.create(couple=self.couple, uploaded_by=self.user, image=self.png(), latitude=35.1, longitude=129.0)
        plain = Photo.objects.create(couple=self.couple, uploaded_by=self.user, image=self.png())
        self.assertContains(self.client.get(reverse("photo_detail", args=[linked.pk])), reverse("taste_detail", args=[place.pk]))
        self.assertContains(self.client.get(reverse("photo_detail", args=[located.pk])), "tab=record&amp;focus=35.1,129.0")
        self.assertContains(self.client.get(reverse("photo_detail", args=[plain.pk])), "위치 없음")


class PlacePhotoTests(TestCase):
    """장소 화면의 사진 모음·고르기, 사진 고치기의 장소 칸, 사진에서 위치 가져오기 목록."""

    setUp = UploadStorageTests.setUp
    tearDown = UploadStorageTests.tearDown
    png = UploadStorageTests.png

    def place(self, title="대림창고", **fields):
        return Taste.objects.create(couple=self.couple, author=self.user, category="장소", title=title, latitude=37.5418, longitude=127.0565, **fields)

    def photo(self, couple=None, user=None, **fields):
        return Photo.objects.create(couple=couple or self.couple, uploaded_by=user or self.user, image=self.png(), **fields)

    def stranger_photo(self):
        other = Couple.objects.create()
        stranger = User.objects.create_user("z", password="pw", couple=other)
        return self.photo(couple=other, user=stranger, latitude=37.5, longitude=127.0)

    def test_place_detail_shows_linked_photos(self):
        place = self.place()
        linked = self.photo(place=place)
        self.photo()
        html = self.client.get(reverse("taste_detail", args=[place.pk])).content.decode()
        self.assertIn("이곳에서 찍은 사진", html)
        self.assertIn(reverse("photo_detail", args=[linked.pk]), html)
        self.assertEqual(html.count('class="tile"'), 1)
        self.assertIn("data-mini-map", html)
        self.assertIn(reverse("place_photos_edit", args=[place.pk]), html)

    def test_pick_photos_attach_and_detach(self):
        place = self.place()
        keep = self.photo(place=place)
        drop = self.photo(place=place)
        add = self.photo()
        theirs = self.stranger_photo()
        res = self.client.post(reverse("place_photos_edit", args=[place.pk]), {"photos": [keep.pk, add.pk, theirs.pk]})
        self.assertRedirects(res, reverse("taste_detail", args=[place.pk]))
        for p in (keep, drop, add, theirs):
            p.refresh_from_db()
        self.assertEqual((keep.place, add.place, drop.place, theirs.place), (place, place, None, None))
        self.assertTrue(keep.place_manual and add.place_manual and drop.place_manual)
        self.assertFalse(theirs.place_manual)

    def test_pick_photos_page_lists_my_photos(self):
        place = self.place()
        mine = self.photo(place=place)
        self.stranger_photo()
        html = self.client.get(reverse("place_photos_edit", args=[place.pk])).content.decode()
        self.assertIn(f'value="{mine.pk}" checked', html)
        self.assertEqual(html.count('name="photos"'), 1)

    def test_moment_has_no_photo_picker(self):
        song = Taste.objects.create(couple=self.couple, author=self.user, category="음악", title="노래")
        self.assertEqual(self.client.get(reverse("place_photos_edit", args=[song.pk])).status_code, 404)

    def edit(self, photo, choice):
        return self.client.post(reverse("photo_update", args=[photo.pk]), {"caption": "", "place_choice": choice})

    def test_photo_place_choice(self):
        place = self.place()
        photo = self.photo(latitude=37.5419, longitude=127.0566)
        self.edit(photo, "none")
        photo.refresh_from_db()
        self.assertEqual((photo.place, photo.place_manual), (None, True))
        self.edit(photo, str(place.pk))
        photo.refresh_from_db()
        self.assertEqual((photo.place, photo.place_manual), (place, True))
        self.edit(photo, "auto")
        photo.refresh_from_db()
        self.assertEqual((photo.place, photo.place_manual), (place, False))  # 200m 안이라 자동으로 다시 붙음

    def test_photo_place_choice_rejects_other_couple(self):
        other = Couple.objects.create()
        stranger = User.objects.create_user("y", password="pw", couple=other)
        theirs = Taste.objects.create(couple=other, author=stranger, category="장소", title="남의 곳")
        photo = self.photo()
        res = self.edit(photo, str(theirs.pk))
        self.assertEqual(res.status_code, 200)  # 폼 오류로 다시 보임
        photo.refresh_from_db()
        self.assertIsNone(photo.place)

    def test_photo_edit_initial_choice(self):
        place = self.place()
        auto = self.photo(place=place)
        manual = self.photo(place=place, place_manual=True)
        import re

        def checked(photo):
            html = self.client.get(reverse("photo_update", args=[photo.pk])).content.decode()
            return re.findall(r'name="place_choice" value="([^"]+)"[^>]*checked', html)

        self.assertEqual(checked(auto), ["auto"])
        self.assertEqual(checked(manual), [str(place.pk)])

    def test_photo_choices_for_picker(self):
        mine = self.photo(latitude=37.5, longitude=127.0)
        self.photo()
        self.stranger_photo()
        data = self.client.get(reverse("place_photo_choices")).json()["photos"]
        self.assertEqual([p["id"] for p in data], [mine.pk])
        self.assertEqual(set(data[0]), {"id", "src", "lat", "lng", "taken"})


class PlaceSearchSettingsTests(TestCase):
    """설정을 덮어쓰지 않은 실제 설정으로도 검색이 오류 없이 돈다 (KAKAO_CLIENT_ID 가 settings 에 있어야 한다)."""

    def test_search_with_real_settings(self):
        from . import placesearch

        with mock.patch.object(placesearch, "_http_json", return_value=[]):
            self.assertEqual(placesearch.search("성수"), [])


class MemoriesReviewFixTests(TestCase):
    """최종 검토에서 나온 것: 긴 해외 주소, 지운 장소의 직접 연결 사진."""

    setUp = UploadStorageTests.setUp
    tearDown = UploadStorageTests.tearDown
    png = UploadStorageTests.png

    def test_long_osm_address_is_trimmed(self):
        from . import placesearch

        long_name = "가" * 150
        osm = [{"name": long_name, "display_name": "아주 긴 주소, " * 40, "lat": "48.1", "lon": "11.5"}]
        with override_settings(KAKAO_CLIENT_ID=""), mock.patch.object(placesearch, "_http_json", return_value=osm):
            from django.core.cache import cache

            cache.clear()
            r = placesearch.search("뮌헨 시골")[0]
        self.assertLessEqual(len(r["address"]), 200)
        self.assertLessEqual(len(r["name"]), 100)

    def test_too_long_hidden_address_still_saves(self):
        res = self.client.post(reverse("taste_create") + "?kind=place", {"title": "곳", "latitude": "48.1", "longitude": "11.5", "address": "가" * 250})
        place = Taste.objects.get()
        self.assertRedirects(res, reverse("taste_detail", args=[place.pk]))
        self.assertEqual(len(place.address), 200)

    def test_deleted_place_photos_go_back_to_auto(self):
        a = Taste.objects.create(couple=self.couple, author=self.user, category="장소", title="A", latitude=37.5445, longitude=127.056)
        b = Taste.objects.create(couple=self.couple, author=self.user, category="장소", title="B", latitude=37.5449, longitude=127.056)
        photo = Photo.objects.create(couple=self.couple, uploaded_by=self.user, image=self.png(), latitude=37.5445, longitude=127.056, place=a, place_manual=True)
        self.client.post(reverse("taste_delete", args=[a.pk]))
        photo.refresh_from_db()
        self.assertEqual((photo.place, photo.place_manual), (b, False))


class RegionMapTests(TestCase):
    """색칠 지도: 점(장소·사진 위치)과 직접 표시(RegionMark)."""

    setUp = UploadStorageTests.setUp
    tearDown = UploadStorageTests.tearDown
    png = UploadStorageTests.png

    def mark(self, data, raw=None):
        import json as _json

        body = raw if raw is not None else _json.dumps(data)
        return self.client.post(reverse("region_mark"), body, content_type="application/json")

    def test_data_points_and_marks(self):
        from .models import RegionMark

        Taste.objects.create(couple=self.couple, author=self.user, category="장소", title="곳", latitude=37.54, longitude=127.05)
        Taste.objects.create(couple=self.couple, author=self.user, category="장소", title="위치 없음")
        Taste.objects.create(couple=self.couple, author=self.user, category="음악", title="노래", latitude=1, longitude=1)
        Photo.objects.create(couple=self.couple, uploaded_by=self.user, image=self.png(), latitude=33.5, longitude=126.5)
        Photo.objects.create(couple=self.couple, uploaded_by=self.user, image=self.png())
        other = Couple.objects.create()
        stranger = User.objects.create_user("z", password="pw", couple=other)
        Taste.objects.create(couple=other, author=stranger, category="장소", title="남의 곳", latitude=35.0, longitude=129.0)
        Photo.objects.create(couple=other, uploaded_by=stranger, image=self.png(), latitude=35.1, longitude=129.1)
        RegionMark.objects.create(couple=self.couple, level="sigungu", code="11040", state="on")
        RegionMark.objects.create(couple=other, level="sigungu", code="21010", state="on")

        data = self.client.get(reverse("region_data")).json()
        self.assertEqual(
            sorted((p["kind"], p["lat"], p["lng"]) for p in data["points"]),
            [("photo", 33.5, 126.5), ("place", 37.54, 127.05)],
        )
        self.assertEqual(data["marks"], [{"level": "sigungu", "code": "11040", "state": "on"}])

    def test_mark_on_off_auto(self):
        from .models import RegionMark

        self.assertEqual(self.mark({"level": "dong", "code": "1104065", "state": "on"}).json(), {"ok": True})
        self.mark({"level": "dong", "code": "1104065", "state": "off"})
        m = RegionMark.objects.get()
        self.assertEqual((m.state, m.updated_by), ("off", self.user))
        self.mark({"level": "dong", "code": "1104065", "state": "auto"})
        self.assertFalse(RegionMark.objects.exists())

    def test_mark_rejects_bad_input(self):
        bad = [
            {"level": "gu", "code": "11040", "state": "on"},
            {"level": "sigungu", "code": "11040", "state": "maybe"},
            {"level": "sigungu", "code": "abc", "state": "on"},
            {"level": "sigungu", "code": "1", "state": "on"},
            {"level": "sigungu", "code": "12345678901", "state": "on"},
        ]
        for data in bad:
            self.assertEqual(self.mark(data).status_code, 400, data)
        self.assertEqual(self.mark(None, raw="x").status_code, 400)
        self.assertEqual(self.mark(None, raw="[1]").status_code, 400)

    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("region_data")).status_code, 302)
        self.assertEqual(self.mark({"level": "dong", "code": "1104065", "state": "on"}).status_code, 302)


class WishlistTests(TestCase):
    """가고 싶은 곳과 목록."""

    setUp = UploadStorageTests.setUp
    tearDown = UploadStorageTests.tearDown

    def make_list(self, name="맛집", color="rose", couple=None):
        from .models import WishList

        return WishList.objects.create(couple=couple or self.couple, name=name, color=color)

    def wish_data(self, **extra):
        data = {"name": "성수 카페", "latitude": "37.5446", "longitude": "127.0559", "address": "서울 성동구", "memo": "브런치"}
        data.update(extra)
        return data

    def test_list_create_and_duplicate(self):
        from .models import WishList

        self.client.post(reverse("wishlist_create"), {"name": "맛집", "color": "rose"})
        res = self.client.post(reverse("wishlist_create"), {"name": "맛집", "color": "sky"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(WishList.objects.count(), 1)

    def test_wish_save_with_lists_and_merge_new_list(self):
        from .models import WishPlace

        food, trip = self.make_list("맛집"), self.make_list("여행", "sky")
        res = self.client.post(reverse("wish_create"), self.wish_data(lists=[food.pk, trip.pk], new_list=" 맛집 "))
        wish = WishPlace.objects.get()
        self.assertRedirects(res, reverse("wishes"))
        self.assertEqual((wish.latitude, wish.longitude, wish.memo), (37.5446, 127.0559, "브런치"))
        self.assertEqual(sorted(l.name for l in wish.lists.all()), ["맛집", "여행"])
        self.client.post(reverse("wish_create"), self.wish_data(name="부산", new_list="부산 여행"))
        self.assertEqual(WishPlace.objects.get(name="부산").lists.get().name, "부산 여행")

    def test_deleted_list_choice_shows_error(self):
        """고르는 사이에 상대가 목록을 지우면 왜 저장이 안 됐는지 보여 준다."""
        gone = self.make_list("카페")
        pk = gone.pk
        gone.delete()
        res = self.client.post(reverse("wish_create"), self.wish_data(lists=[pk]))
        self.assertContains(res, "목록이 바뀌었어요. 다시 골라 주세요.")

    def test_wish_needs_location(self):
        from .models import WishPlace

        for coords in ({"latitude": "", "longitude": ""}, {"latitude": "0", "longitude": "0"}):
            res = self.client.post(reverse("wish_create"), self.wish_data(**coords))
            self.assertContains(res, "위치를 골라 주세요.")
        self.assertFalse(WishPlace.objects.exists())

    def test_other_couple_list_and_wish(self):
        from .models import WishPlace

        other = Couple.objects.create()
        stranger = User.objects.create_user("z", password="pw", couple=other)
        theirs = self.make_list("남의 목록", couple=other)
        self.client.post(reverse("wish_create"), self.wish_data(lists=[theirs.pk]))
        self.assertFalse(WishPlace.objects.exists())
        their_wish = WishPlace.objects.create(couple=other, name="남의 곳", latitude=35, longitude=129, created_by=stranger)
        self.assertEqual(self.client.get(reverse("wish_update", args=[their_wish.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("wish_delete", args=[their_wish.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("wishlist_delete", args=[theirs.pk])).status_code, 404)

    def test_list_delete_keeps_places(self):
        from .models import WishList, WishPlace

        food = self.make_list("맛집")
        self.client.post(reverse("wish_create"), self.wish_data(lists=[food.pk]))
        self.client.post(reverse("wishlist_delete", args=[food.pk]))
        self.assertFalse(WishList.objects.exists())
        self.assertEqual(WishPlace.objects.get().lists.count(), 0)

    def test_page_filter_and_order(self):
        from django.utils import timezone as tz

        from .models import WishPlace

        food = self.make_list("맛집")
        done = WishPlace.objects.create(couple=self.couple, name="다녀온 곳", latitude=37.5, longitude=127, visited_at=tz.now())
        todo = WishPlace.objects.create(couple=self.couple, name="갈 곳", latitude=37.5, longitude=127)
        other = WishPlace.objects.create(couple=self.couple, name="다른 곳", latitude=37.5, longitude=127)
        todo.lists.add(food); done.lists.add(food)
        html = self.client.get(reverse("wishes")).content.decode()
        self.assertLess(html.index("갈 곳"), html.index("다녀온 곳"))
        html = self.client.get(reverse("wishes") + f"?list={food.pk}").content.decode()
        self.assertIn("갈 곳", html)
        self.assertNotIn("다른 곳", html)

    def test_edit_from_record_map_goes_back_there(self):
        """기록 지도 겹쳐 보기에서 들어온 고치기 화면은 기록 탭으로 돌아간다."""
        from .models import WishPlace

        w = WishPlace.objects.create(couple=self.couple, name="성수 카페", latitude=37.5, longitude=127)
        back = reverse("tastes") + "?tab=record"
        url = reverse("wish_update", args=[w.pk])
        self.assertContains(self.client.get(url + "?from=record"), f'href="{back}"')
        self.assertNotContains(self.client.get(url), f'href="{back}"')
        self.assertRedirects(self.client.post(url + "?from=record", self.wish_data()), back, fetch_redirect_response=False)
        self.assertRedirects(self.client.post(url + "?from=evil", self.wish_data()), reverse("wishes"))

    def test_recent_visits_first(self):
        """다녀온 곳끼리는 최근에 다녀온 곳이 먼저."""
        from datetime import timedelta

        from django.utils import timezone as tz

        from .models import WishPlace

        now = tz.now()
        WishPlace.objects.create(couple=self.couple, name="예전에 간 곳", latitude=37.5, longitude=127, visited_at=now - timedelta(days=30))
        WishPlace.objects.create(couple=self.couple, name="어제 간 곳", latitude=37.5, longitude=127, visited_at=now - timedelta(days=1))
        WishPlace.objects.create(couple=self.couple, name="아직 갈 곳", latitude=37.5, longitude=127)
        names = list(WishPlace.objects.values_list("name", flat=True))
        self.assertEqual(names, ["아직 갈 곳", "어제 간 곳", "예전에 간 곳"])

    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("wishes")).status_code, 302)


class WishVisitedTests(TestCase):
    """다녀왔어요 → 기록 장소, 지도 데이터, 기록 탭 카드."""

    setUp = UploadStorageTests.setUp
    tearDown = UploadStorageTests.tearDown
    png = UploadStorageTests.png

    def wish(self, couple=None, **fields):
        from .models import WishPlace

        data = {"name": "성수 카페", "latitude": 37.5446, "longitude": 127.0559, "address": "서울 성동구", "place_url": "https://place.map.kakao.com/1"}
        data.update(fields)
        return WishPlace.objects.create(couple=couple or self.couple, **data)

    def test_visited_creates_one_record(self):
        w = self.wish()
        photo = Photo.objects.create(couple=self.couple, uploaded_by=self.user, image=self.png(), latitude=37.5447, longitude=127.0559)
        res = self.client.post(reverse("wish_visited", args=[w.pk]))
        place = Taste.objects.get(category="장소")
        self.assertRedirects(res, reverse("taste_detail", args=[place.pk]))
        self.assertEqual((place.title, place.latitude, place.address, place.author), ("성수 카페", 37.5446, "서울 성동구", self.user))
        w.refresh_from_db(); photo.refresh_from_db()
        self.assertTrue(w.is_visited)
        self.assertEqual((w.visited_place, photo.place), (place, place))
        res = self.client.post(reverse("wish_visited", args=[w.pk]))
        self.assertRedirects(res, reverse("taste_detail", args=[place.pk]))
        self.assertEqual(Taste.objects.filter(category="장소").count(), 1)

    def test_visited_again_after_record_deleted(self):
        w = self.wish()
        self.client.post(reverse("wish_visited", args=[w.pk]))
        w.refresh_from_db()
        first_at = w.visited_at
        w.visited_place.delete()
        self.client.post(reverse("wish_visited", args=[w.pk]))
        w.refresh_from_db()
        self.assertEqual(Taste.objects.filter(category="장소").count(), 1)
        self.assertIsNotNone(w.visited_place)
        self.assertEqual(w.visited_at, first_at)

    def test_visited_other_couple_and_get(self):
        other = Couple.objects.create()
        theirs = self.wish(couple=other)
        self.assertEqual(self.client.post(reverse("wish_visited", args=[theirs.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("wish_visited", args=[self.wish().pk])).status_code, 405)

    def test_map_data(self):
        from django.utils import timezone as tz

        from .models import WishList

        food = WishList.objects.create(couple=self.couple, name="맛집", color="rose")
        todo = self.wish(name="갈 곳")
        todo.lists.add(food)
        self.wish(name="다녀온 곳", visited_at=tz.now())
        self.wish(couple=Couple.objects.create(), name="남의 곳")
        data = self.client.get(reverse("wish_map_data")).json()["places"]
        self.assertEqual(sorted(p["name"] for p in data), ["갈 곳", "다녀온 곳"])
        self.assertEqual(set(data[0]), {"id", "name", "lat", "lng", "color", "visited", "url", "address", "photos"})
        got = {p["name"]: p for p in data}
        self.assertEqual((got["갈 곳"]["color"], got["다녀온 곳"]["color"]), ("rose", "peach"))
        self.assertEqual([p["name"] for p in self.client.get(reverse("wish_map_data") + "?open=1").json()["places"]], ["갈 곳"])
        self.assertEqual([p["name"] for p in self.client.get(reverse("wish_map_data") + f"?list={food.pk}").json()["places"]], ["갈 곳"])

    def test_record_tab_card_counts_open(self):
        from django.utils import timezone as tz

        self.wish(name="a"); self.wish(name="b"); self.wish(name="c", visited_at=tz.now())
        html = self.client.get(reverse("tastes") + "?tab=record").content.decode()
        self.assertIn(reverse("wishes"), html)
        self.assertIn("가고 싶은 곳 · 2곳", html)


class MultiDayEventTests(TestCase):
    """여러 날 일정 (하루 종일만)."""

    setUp = ScreenTests.setUp
    event_form = ScreenTests.event_form

    def make(self, start, end=None, title="여행", user=None, scope=Event.SHARED):
        return Event.objects.create(couple=self.couple, created_by=user or self.a, title=title, date=start, end_date=end, scope=scope)

    def test_create_multi_day_clears_times(self):
        day = timezone.localdate()
        self.client.post(reverse("event_create"), self.event_form(date=day.isoformat(), end_date=(day + timedelta(days=2)).isoformat()))
        e = Event.objects.get()
        self.assertEqual(e.end_date, day + timedelta(days=2))
        self.assertEqual((e.start_time, e.end_time), (None, None))
        self.assertTrue(e.is_multi_day)
        self.assertEqual(e.span_days, 3)

    def test_end_date_same_day_is_single(self):
        day = timezone.localdate()
        self.client.post(reverse("event_create"), self.event_form(end_date=day.isoformat()))
        e = Event.objects.get()
        self.assertIsNone(e.end_date)
        self.assertFalse(e.is_multi_day)
        self.assertIsNotNone(e.start_time)

    def test_end_date_before_start_rejected(self):
        day = timezone.localdate()
        res = self.client.post(reverse("event_create"), self.event_form(end_date=(day - timedelta(days=1)).isoformat()))
        self.assertContains(res, "끝나는 날은 시작하는 날보다 뒤여야 해요.")
        self.assertFalse(Event.objects.exists())

    def test_longer_than_60_days_rejected(self):
        day = timezone.localdate()
        res = self.client.post(reverse("event_create"), self.event_form(end_date=(day + timedelta(days=60)).isoformat()))
        self.assertContains(res, "여러 날 일정은 60일까지 넣을 수 있어요.")
        self.client.post(reverse("event_create"), self.event_form(end_date=(day + timedelta(days=59)).isoformat()))
        self.assertEqual(Event.objects.get().span_days, 60)

    def test_month_shows_event_started_last_month(self):
        first = timezone.localdate().replace(day=1)
        start = first - timedelta(days=4)
        e = self.make(start, first + timedelta(days=1))
        res = self.client.get(reverse("calendar") + f"?month={first:%Y-%m}&day={first + timedelta(days=1):%Y-%m-%d}")
        cells = {c["date"]: c for week in res.context["weeks"] for c in week}
        self.assertIn(e, cells[first]["events"])
        self.assertIn(e, cells[first + timedelta(days=1)]["events"])
        self.assertNotIn(e, cells[first + timedelta(days=2)]["events"])
        if first + timedelta(days=1) != timezone.localdate():
            self.assertIn(e, res.context["day_events"])

    def test_ongoing_trip_upcoming_and_editable(self):
        today = timezone.localdate()
        trip = self.make(today - timedelta(days=1), today + timedelta(days=1))
        done = self.make(today - timedelta(days=2), today - timedelta(days=1), title="끝난 여행")
        self.assertIn(trip, list(self.client.get(reverse("calendar")).context["upcoming"]))
        self.assertIn(trip, list(self.client.get(reverse("home")).context["events"]))
        self.assertFalse(trip.is_past)
        self.assertTrue(done.is_past)
        page = self.client.get(reverse("event_update", args=[trip.pk]))
        self.assertNotContains(page, "지난 일정은 고칠 수 없어요")
        self.client.post(reverse("event_update", args=[trip.pk]), self.event_form(
            text="부산 여행", date=trip.date.isoformat(), end_date=trip.end_date.isoformat()))
        trip.refresh_from_db()
        self.assertEqual(trip.title, "부산 여행")
        self.assertContains(self.client.get(reverse("event_update", args=[done.pk])), "지난 일정은 고칠 수 없어요")

    def test_edit_form_prefills_end_date(self):
        today = timezone.localdate()
        trip = self.make(today, today + timedelta(days=2))
        page = self.client.get(reverse("event_update", args=[trip.pk]))
        self.assertEqual(page.context["form"].initial["end_date"], trip.end_date)

    def test_ics_multi_day_all_day(self):
        from .models import CalendarFeed

        today = timezone.localdate()
        self.make(today + timedelta(days=3), today + timedelta(days=5))
        feed, _ = CalendarFeed.objects.get_or_create(user=self.a)
        text = self.client.get(reverse("calendar_feed", args=[feed.token])).content.decode()
        self.assertIn(f"DTSTART;VALUE=DATE:{today + timedelta(days=3):%Y%m%d}", text)
        self.assertIn(f"DTEND;VALUE=DATE:{today + timedelta(days=6):%Y%m%d}", text)

    def test_event_item_shows_range(self):
        today = timezone.localdate()
        start, end = today + timedelta(days=1), today + timedelta(days=3)
        self.make(start, end)
        res = self.client.get(reverse("calendar"))
        self.assertContains(res, f"{start.month}. {start.day}. – {end.month}. {end.day}. · 하루 종일")

    def test_label_past_uses_last_date(self):
        today = timezone.localdate()
        label = Label.objects.create(couple=self.couple, kind=Label.TAG, name="부산")
        trip = self.make(today - timedelta(days=1), today + timedelta(days=1))
        trip.labels.add(label)
        res = self.client.get(reverse("calendar") + f"?label={label.pk}")
        self.assertIn(trip, res.context["label_upcoming"])
        self.assertNotIn(trip, res.context["label_past"])
