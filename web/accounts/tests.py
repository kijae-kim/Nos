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
        self.assertContains(self.client.get(reverse("socialaccount_login_cancelled")), "로그인을 취소했어요")
        self.assertContains(self.client.get(reverse("socialaccount_login_error")), "로그인하지 못했어요", status_code=401)
