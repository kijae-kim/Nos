from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
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
