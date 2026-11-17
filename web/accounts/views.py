from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import EMOJIS, ProfileForm
from .models import COLOR_CHOICES, Avatar, User


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


@login_required
def profile(request):
    """프로필 바꾸기: 사진·이모지·내 색."""
    user = request.user
    partner = user.partner
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, partner=partner)
        if form.is_valid():
            fields = ["emoji", "color"]
            user.emoji = form.cleaned_data["emoji"]
            user.color = form.cleaned_data["color"]
            if form.avatar_bytes:
                Avatar.objects.update_or_create(user=user, defaults={"data": form.avatar_bytes})
                user.has_avatar = True
                user.avatar_version += 1
                fields += ["has_avatar", "avatar_version"]
            elif form.cleaned_data["remove_photo"] and user.has_avatar:
                Avatar.objects.filter(user=user).delete()
                user.has_avatar = False
                fields += ["has_avatar"]
            user.save(update_fields=fields)
            messages.success(request, "프로필을 바꿨어요.")
            return redirect("us")
    else:
        form = ProfileForm(initial={"emoji": user.emoji, "color": user.color}, partner=partner)
    return render(request, "accounts/profile.html", {
        "form": form, "emojis": EMOJIS, "colors": COLOR_CHOICES,
        "partner_color": partner.color if partner else None,
        "current_color": form["color"].value() or user.color,
    })


@login_required
def avatar(request, pk):
    """프로필 사진. 나와 내 커플 상대만 볼 수 있다. 주소 끝 ?v= 가 바뀌면 새 사진."""
    me = request.user
    allowed = pk == me.pk or (me.couple_id and User.objects.filter(pk=pk, couple_id=me.couple_id).exists())
    if not allowed:
        raise Http404
    photo = get_object_or_404(Avatar, user_id=pk)
    res = HttpResponse(bytes(photo.data), content_type="image/jpeg")
    res["Cache-Control"] = "private, max-age=31536000"
    return res

