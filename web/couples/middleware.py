from django.shortcuts import redirect

EXEMPT_PREFIXES = ("/accounts/", "/couple/", "/admin/", "/static/", "/manifest.webmanifest", "/sw.js")


class CoupleRequiredMiddleware:
    """로그인했지만 아직 커플 연결이 안 된 사용자를 연결 화면으로 보낸다."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated and not user.couple_id and not request.path.startswith(EXEMPT_PREFIXES):
            return redirect("couple_connect")
        return self.get_response(request)
