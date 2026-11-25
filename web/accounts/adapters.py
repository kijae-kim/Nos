from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter

from .models import User

NICKNAME_MAX = User._meta.get_field("nickname").max_length


def nickname_from(provider, extra_data):
    """소셜 계정이 알려 준 이름 중 앱에서 부를 이름을 고른다. 없으면 빈 문자열."""
    data = extra_data or {}
    if provider == "kakao":
        # 카카오는 이메일을 주지 않으므로 닉네임이 사실상 유일한 이름이다
        profile = (data.get("kakao_account") or {}).get("profile") or {}
        name = profile.get("nickname") or (data.get("properties") or {}).get("nickname")
    elif provider == "google":
        name = data.get("given_name") or data.get("name")
    else:
        name = data.get("name")
    return (name or "").strip()[:NICKNAME_MAX]


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        """이메일 회원가입은 막는다 (2026-11-25). 새 회원은 카카오·구글로 시작하고, 이미 있는 이메일 계정은 그대로 로그인한다."""
        return False


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(self, request, sociallogin):
        """소셜 로그인으로 처음 오면 가입시킨다 (기본값은 이메일 가입 설정을 따라 막혀 버린다)."""
        return True

    def populate_user(self, request, sociallogin, data):
        """소셜 로그인으로 처음 가입할 때, 그 계정의 이름을 닉네임으로 넣어 둔다. 나중에 '우리'에서 바꿀 수 있다."""
        user = super().populate_user(request, sociallogin, data)
        if not user.nickname:
            user.nickname = nickname_from(sociallogin.account.provider, sociallogin.account.extra_data)
        return user
