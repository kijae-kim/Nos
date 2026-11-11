import tempfile
from datetime import timedelta

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
