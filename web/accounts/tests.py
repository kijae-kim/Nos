from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from couples.models import Couple

from .adapters import SocialAccountAdapter, nickname_from

User = get_user_model()

# 시험용 소셜 로그인 설정. 실제 키가 아니며 외부로 요청을 보내지 않는다.
PROVIDERS = {
    "kakao": {"APPS": [{"client_id": "test-kakao", "secret": "", "key": ""}]},
    "google": {"APPS": [{"client_id": "test-google", "secret": "x", "key": ""}], "SCOPE": ["profile", "email"]},
}


class NicknameTests(TestCase):
    def test_kakao_nickname(self):
        data = {"id": 1, "kakao_account": {"profile": {"nickname": " 바다 "}}}
        self.assertEqual(nickname_from("kakao", data), "바다")

    def test_kakao_nickname_from_old_properties(self):
        self.assertEqual(nickname_from("kakao", {"properties": {"nickname": "하늘"}}), "하늘")

    def test_google_prefers_given_name(self):
        self.assertEqual(nickname_from("google", {"given_name": "하늘", "name": "김하늘"}), "하늘")
        self.assertEqual(nickname_from("google", {"name": "김하늘"}), "김하늘")

    def test_long_or_missing_names(self):
        self.assertEqual(len(nickname_from("kakao", {"kakao_account": {"profile": {"nickname": "가" * 50}}})), 20)
        self.assertEqual(nickname_from("kakao", {}), "")
        self.assertEqual(nickname_from("google", None), "")

    def test_adapter_fills_nickname_on_social_signup(self):
        user = User()
        account = SocialAccount(provider="kakao", uid="1", extra_data={"kakao_account": {"profile": {"nickname": "바다"}}})
        login = SocialLogin(user=user, account=account)
        request = RequestFactory().get("/")
        SocialAccountAdapter(request).populate_user(request, login, {"username": "바다"})
        self.assertEqual(user.nickname, "바다")


@override_settings(SOCIALACCOUNT_PROVIDERS=PROVIDERS)
class ScreenTests(TestCase):
    def setUp(self):
        self.couple = Couple.objects.create()
        self.user = User.objects.create_user("a", email="a@example.com", password="pw-test-1234", couple=self.couple)
        self.client.force_login(self.user)

    def test_login_page_shows_buttons_and_guidance(self):
        self.client.logout()
        page = self.client.get(reverse("account_login"))
        self.assertContains(page, "카카오로 시작하기")
        self.assertContains(page, "Google로 시작하기")
        self.assertContains(page, "data-needs-browser")
        self.assertContains(page, "처음 가입한 방법으로 로그인해 주세요")

    def test_us_screen_links_to_connections(self):
        page = self.client.get(reverse("us"))
        self.assertContains(page, reverse("socialaccount_connections"))
        self.assertContains(page, "연결된 계정")

    def test_connections_lists_and_offers_only_missing_providers(self):
        SocialAccount.objects.create(user=self.user, provider="kakao", uid="123", extra_data={})
        page = self.client.get(reverse("socialaccount_connections"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "카카오")
        self.assertContains(page, "Google 연결하기")
        self.assertNotContains(page, "카카오 연결하기")
        self.assertContains(page, "process=connect")

    def test_disconnect_social_account(self):
        account = SocialAccount.objects.create(user=self.user, provider="google", uid="9", extra_data={})
        self.client.post(reverse("socialaccount_connections"), {"account": account.pk})
        self.assertFalse(SocialAccount.objects.filter(pk=account.pk).exists())

    def test_cannot_remove_the_only_way_to_log_in(self):
        self.user.set_unusable_password()
        self.user.save()
        self.client.force_login(self.user)
        account = SocialAccount.objects.create(user=self.user, provider="kakao", uid="7", extra_data={})
        self.client.post(reverse("socialaccount_connections"), {"account": account.pk})
        self.assertTrue(SocialAccount.objects.filter(pk=account.pk).exists())

    def test_logout_and_social_problem_pages_use_app_layout(self):
        self.assertContains(self.client.get(reverse("account_logout")), "로그아웃할까요?")
        # 로그인 취소는 화면 없이 로그인으로 돌아간다 (SocialLoginCancelledTests)
        self.assertContains(self.client.get(reverse("socialaccount_login_error")), "로그인하지 못했어요", status_code=401)


class AppearanceTests(TestCase):
    """테마·화면 모드를 계정에 저장한다."""

    def setUp(self):
        self.user = get_user_model().objects.create_user("t", password="pw", couple=Couple.objects.create())
        self.client.force_login(self.user)

    def test_defaults(self):
        self.assertEqual((self.user.palette, self.user.mode), ("boat", "system"))

    def test_save_palette_and_mode(self):
        response = self.client.post(reverse("appearance"), {"palette": "journey"})
        self.assertEqual(response.json(), {"ok": True, "palette": "journey", "mode": "system"})
        self.client.post(reverse("appearance"), {"mode": "dark"})
        self.user.refresh_from_db()
        self.assertEqual((self.user.palette, self.user.mode), ("journey", "dark"))

    def test_rejects_unknown_values(self):
        self.assertEqual(self.client.post(reverse("appearance"), {"palette": "neon", "mode": "x"}).status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual((self.user.palette, self.user.mode), ("boat", "system"))

    def test_needs_login_and_post(self):
        self.assertEqual(self.client.get(reverse("appearance")).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.post(reverse("appearance"), {"mode": "dark"}).status_code, 302)

    def test_page_carries_account_values(self):
        self.user.palette, self.user.mode = "journey", "dark"
        self.user.save()
        response = self.client.get(reverse("home"))
        self.assertContains(response, 'data-account-palette="journey" data-account-mode="dark"')


class SocialLoginCancelledTests(TestCase):
    """카카오·구글 로그인 창에서 취소하면 안내 문구만 보이고 로그인 화면으로 돌아간다."""

    def test_cancel_redirects_to_login_with_notice(self):
        res = self.client.get(reverse("socialaccount_login_cancelled"), follow=True)
        self.assertRedirects(res, reverse("account_login"))
        self.assertContains(res, "로그인을 취소했어요.")

    def test_cancel_while_connecting_returns_to_connections(self):
        user = get_user_model().objects.create_user("c", password="pw", couple=Couple.objects.create())
        self.client.force_login(user)
        res = self.client.get(reverse("socialaccount_login_cancelled"), follow=True)
        self.assertRedirects(res, reverse("socialaccount_connections"))
        self.assertContains(res, "계정 연결을 취소했어요.")


def _jpeg(w=600, h=400, gps=False):
    """시험용 JPEG. gps=True 면 위치 EXIF 를 넣는다."""
    import io

    from PIL import Image

    img = Image.new("RGB", (w, h), (200, 80, 60))
    buf = io.BytesIO()
    if gps:
        exif = Image.Exif()
        exif[0x8825] = {1: "N", 2: (37.0, 32.0, 0.0), 3: "E", 4: (127.0, 3.0, 0.0)}  # GPSInfo
        exif[0x010F] = "TestCam"  # Make
        img.save(buf, "JPEG", exif=exif)
    else:
        img.save(buf, "JPEG")
    return buf.getvalue()


class ProfileTests(TestCase):
    """프로필: 사진·이모지·내 색."""

    def setUp(self):
        from datetime import timedelta

        from django.utils import timezone

        self.couple = Couple.objects.create()
        now = timezone.now()
        self.a = User.objects.create_user("a", password="pw", couple=self.couple, nickname="하늘", date_joined=now - timedelta(days=2))
        self.b = User.objects.create_user("b", password="pw", couple=self.couple, nickname="바다", date_joined=now - timedelta(days=1))
        from .avatars import assign_default_colors

        assign_default_colors(self.couple)
        self.a.refresh_from_db(); self.b.refresh_from_db()
        self.client.force_login(self.a)

    def upload(self, data, name="me.jpg", **extra):
        from django.core.files.uploadedfile import SimpleUploadedFile

        payload = {"photo": SimpleUploadedFile(name, data, content_type="image/jpeg"), "color": self.a.color, "emoji": self.a.emoji}
        payload.update(extra)
        return self.client.post(reverse("profile"), payload, follow=True)

    def test_default_colors_by_join_order(self):
        self.assertEqual((self.a.color, self.b.color), ("rose", "sky"))

    def test_join_changes_color_if_same(self):
        other = Couple.objects.create()
        host = User.objects.create_user("h", password="pw", couple=other, color="sky")
        guest = User.objects.create_user("g", password="pw", color="sky")
        self.client.force_login(guest)
        self.client.post(reverse("couple_join"), {"code": other.invite_code})
        guest.refresh_from_db(); host.refresh_from_db()
        self.assertEqual(guest.couple, other)
        self.assertEqual((host.color, guest.color), ("sky", "rose"))

    def test_upload_photo_strips_exif_and_resizes(self):
        import io

        from PIL import Image

        self.upload(_jpeg(gps=True))
        self.a.refresh_from_db()
        self.assertTrue(self.a.has_avatar)
        self.assertEqual(self.a.avatar_version, 1)
        img = Image.open(io.BytesIO(bytes(self.a.avatar_data.data)))
        self.assertEqual(img.size, (256, 256))
        self.assertEqual(len(img.getexif()), 0)
        self.assertNotIn(b"TestCam", bytes(self.a.avatar_data.data))

    def test_bad_and_big_photo(self):
        self.assertContains(self.upload(b"hello", name="x.txt"), "이 사진은 열 수 없어요. 다른 사진을 골라 주세요.")
        self.assertContains(self.upload(b"0" * (2 * 1024 * 1024 + 1)), "사진이 너무 커요. 다른 사진을 골라 주세요.")
        self.a.refresh_from_db()
        self.assertFalse(self.a.has_avatar)

    def test_avatar_url_access(self):
        self.upload(_jpeg())
        self.a.refresh_from_db()
        url = self.a.avatar_url
        self.assertTrue(url.startswith(reverse("avatar", args=[self.a.pk]) + "?v=1"))
        res = self.client.get(url)
        self.assertEqual((res.status_code, res["Content-Type"]), (200, "image/jpeg"))
        self.assertIn("max-age=31536000", res["Cache-Control"])
        self.client.force_login(self.b)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.get(reverse("avatar", args=[self.b.pk])).status_code, 404)  # 사진 없음
        stranger = User.objects.create_user("s", password="pw", couple=Couple.objects.create())
        self.client.force_login(stranger)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

    def post(self, **data):
        payload = {"color": self.a.color, "emoji": ""}
        payload.update(data)
        return self.client.post(reverse("profile"), payload)

    def test_emoji_rules(self):
        self.post(emoji="🐻")
        self.a.refresh_from_db()
        self.assertEqual(self.a.emoji, "🐻")
        for bad in ("ab", "곰 곰", "1", "🐻" * 17):
            self.assertContains(self.post(emoji=bad), "이모지 하나만 넣어 주세요.")
        self.post(emoji="")
        self.a.refresh_from_db()
        self.assertEqual(self.a.emoji, "")

    def test_partner_color_rejected(self):
        res = self.post(color="sky")
        self.assertContains(res, "상대가 쓰고 있는 색이에요. 다른 색을 골라 주세요.")
        self.a.refresh_from_db()
        self.assertEqual(self.a.color, "rose")
        self.post(color="lav")
        self.a.refresh_from_db()
        self.assertEqual(self.a.color, "lav")

    def test_emoji_keeps_photo_until_removed(self):
        self.upload(_jpeg())
        self.post(emoji="🐰")
        self.a.refresh_from_db()
        self.assertTrue(self.a.has_avatar)
        self.assertEqual(self.a.emoji, "🐰")
        self.post(emoji="🐰", remove_photo="1")
        self.a.refresh_from_db()
        self.assertFalse(self.a.has_avatar)
        from .models import Avatar

        self.assertFalse(Avatar.objects.filter(user=self.a).exists())
        self.assertEqual(self.a.avatar_url, "")

    def test_us_page_links_profile(self):
        self.assertContains(self.client.get(reverse("us")), reverse("profile"))
        self.assertEqual(self.client.get(reverse("profile")).status_code, 200)


class AvatarRenderTests(TestCase):
    """아바타: 사람마다 같은 모습. 일정은 만든 사람 색 점."""

    setUp = ProfileTests.setUp

    def render(self, person, size=""):
        from django.template import Context, Template

        return Template("{% load people %}{% avatar person size %}").render(Context({"person": person, "size": size}))

    def test_tag_variants(self):
        self.a.emoji = "🐻"
        html = self.render(self.a, "big")
        self.assertIn("🐻", html)
        self.assertIn("--c: var(--rose)", html)
        self.assertIn('class="av emoji big"', html)
        self.assertIn('class="av"', self.render(self.b))
        self.assertIn("--c: var(--sky)", self.render(self.b))
        self.assertIn("vacant", self.render(None))
        self.a.has_avatar, self.a.avatar_version = True, 3
        html = self.render(self.a)
        self.assertIn("<img", html)
        self.assertIn(reverse("avatar", args=[self.a.pk]) + "?v=3", html)

    def test_tag_escapes(self):
        self.a.emoji = "<b>"
        self.assertIn("&lt;b&gt;", self.render(self.a))

    def test_screens_use_people_not_relative_colors(self):
        from couples.models import Event

        Event.objects.create(couple=self.couple, created_by=self.a, title="같이 저녁", date=timezone_today())
        Event.objects.create(couple=self.couple, created_by=self.b, title="바다 약속", date=timezone_today())
        for name in ("home", "us", "calendar"):
            html = self.client.get(reverse(name)).content.decode()
            self.assertNotRegex(html, r'class="av [ab][ "]', name)
        cal = self.client.get(reverse("calendar")).content.decode()
        self.assertIn('class="dot" style="background: var(--rose)"', cal)
        self.assertIn('class="dot" style="background: var(--sky)"', cal)

    def test_event_list_does_not_load_avatar_bytes(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from couples.models import Event

        Event.objects.create(couple=self.couple, created_by=self.b, title="바다 약속", date=timezone_today())
        with CaptureQueriesContext(connection) as ctx:
            self.client.get(reverse("calendar"))
        event_sql = [q["sql"] for q in ctx if "couples_event" in q["sql"] and "accounts_user" in q["sql"]]
        self.assertTrue(event_sql)
        self.assertFalse(any('"avatar"' in sql for sql in event_sql))


def timezone_today():
    from django.utils import timezone

    return timezone.localdate()


class ProfileStyleTests(TestCase):
    """화면이 깨지지 않게 하는 스타일·스크립트 규칙 (브라우저에서도 확인)."""

    def css(self):
        from pathlib import Path

        return (Path(__file__).resolve().parent.parent / "static/css/app.css").read_text()

    def test_hidden_preview_really_hides(self):
        self.assertIn(".profile-preview [hidden] { display: none; }", self.css())

    def test_plain_color_avatar_keeps_size_inside_link(self):
        css = self.css()
        self.assertIn(".profile-link { display: grid; }", css)
        self.assertRegex(css, r"\.av \{[^}]*display: inline-block")

    def test_submit_waits_for_photo_shrink(self):
        from pathlib import Path

        js = (Path(__file__).resolve().parent.parent / "static/js/app.js").read_text()
        self.assertIn("data-profile-submit", js)
