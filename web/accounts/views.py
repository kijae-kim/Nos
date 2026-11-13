from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from .models import User


@login_required
@require_POST
def appearance(request):
    """테마·화면 모드를 계정에 저장한다. "우리" 화면에서 고를 때 app.js 가 보낸다."""
    user = request.user
    fields = []
    palette = request.POST.get("palette")
    if palette in dict(User.PALETTE_CHOICES):
        user.palette = palette
        fields.append("palette")
    mode = request.POST.get("mode")
    if mode in dict(User.MODE_CHOICES):
        user.mode = mode
        fields.append("mode")
    if not fields:
        return JsonResponse({"ok": False}, status=400)
    user.save(update_fields=fields)
    return JsonResponse({"ok": True, "palette": user.palette, "mode": user.mode})


def social_login_cancelled(request):
    """카카오·구글 로그인 창에서 취소했을 때. 안내 문구만 남기고 원래 화면으로 돌려보낸다."""
    if request.user.is_authenticated:
        # 로그인한 상태에서 취소했다면 '연결된 계정'에서 연결하다 그만둔 것
        messages.info(request, "계정 연결을 취소했어요.")
        return redirect("socialaccount_connections")
    messages.info(request, "로그인을 취소했어요.")
    return redirect("account_login")
