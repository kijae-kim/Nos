import os
import tempfile
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import services
from .models import Album, Couple, Event, Label, Photo, Taste

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

    def test_taste_create_detail_edit_delete(self):
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
