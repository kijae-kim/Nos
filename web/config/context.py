from django.conf import settings


def app(request):
    data = {"APP_NAME": settings.APP_NAME, "WEBPUSH_ENABLED": settings.WEBPUSH_ENABLED}
    # 처음 한 번 튜토리얼, 그다음은 새 소식이 있을 때 한 번 팝업 (accounts/news.py). 팝업 안(?sheet=1)에서는 띄우지 않는다
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and user.couple_id and request.GET.get("sheet") != "1":
        from accounts.news import LATEST, NEWS

        data["show_tutorial"] = not user.tutorial_done
        data["show_news"] = user.tutorial_done and user.news_seen != LATEST
        data["news_latest"] = NEWS[0]
    return data
