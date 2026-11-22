import json
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .forms import FolderForm
from .lines import clean_lines, ensure_default_folders, title_and_preview
from .models import Memo, MemoFolder


def _folder(request, pk):
    return get_object_or_404(MemoFolder, pk=pk, couple=request.user.couple)


def _memo(request, pk):
    return get_object_or_404(Memo, pk=pk, couple=request.user.couple)


@login_required
def memos(request):
    """폴더 화면: 폴더마다 메모 수."""
    couple = request.user.couple
    ensure_default_folders(couple)
    folders = couple.memo_folders.annotate(count=Count("memos"))
    return render(request, "memos/index.html", {"folders": folders})


@login_required
def folder_create(request):
    form = FolderForm(request.POST or None, couple=request.user.couple)
    if request.method == "POST" and form.is_valid():
        folder = form.save(commit=False)
        folder.couple = request.user.couple
        folder.save()
        return redirect("memo_folder", pk=folder.pk)
    return render(request, "memos/folder_form.html", {"form": form, "folder": None})


@login_required
def folder_update(request, pk):
    folder = _folder(request, pk)
    form = FolderForm(request.POST or None, instance=folder, couple=request.user.couple)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("memo_folder", pk=folder.pk)
    return render(request, "memos/folder_form.html", {"form": form, "folder": folder})


@login_required
@require_POST
def folder_delete(request, pk):
    folder = _folder(request, pk)
    if folder.memos.exists():
        messages.error(request, "메모를 옮기거나 지운 뒤에 지울 수 있어요.")
        return redirect("memo_folder", pk=folder.pk)
    folder.delete()
    messages.success(request, "폴더를 지웠어요.")
    return redirect("memos")


EMPTY_MEMO_AGE = timedelta(hours=1)


@login_required
@never_cache
def folder(request, pk):
    """메모 목록 (최근 고친 순). 글이 없는 메모는 숨기고, 1시간 넘게 빈 채인 것만 지운다
    (상대가 방금 열어 아직 쓰는 중인 새 메모를 지우지 않게)."""
    folder = _folder(request, pk)
    items = list(folder.memos.select_related("updated_by"))
    stale = timezone.now() - EMPTY_MEMO_AGE
    old_empty = [m.pk for m in items if m.is_empty and m.updated_at < stale]
    if old_empty:
        Memo.objects.filter(pk__in=old_empty).delete()
    items = [m for m in items if not m.is_empty]
    request.session["memo_folder"] = folder.pk  # + 메뉴 '메모' 가 이 폴더에 새 메모를 연다
    return render(request, "memos/folder.html", {"folder": folder, "items": items})


@login_required
def memo_new(request):
    """빈 메모를 만들고 쓰기 화면으로. 폴더: ?folder= → 마지막으로 쓴 폴더 → 첫 폴더."""
    couple = request.user.couple
    ensure_default_folders(couple)
    folder_id = request.GET.get("folder") or request.session.get("memo_folder")
    folder = couple.memo_folders.filter(pk=folder_id).first() if str(folder_id or "").isdigit() else None
    folder = folder or couple.memo_folders.first()
    request.session["memo_folder"] = folder.pk
    memo = Memo.objects.create(couple=couple, folder=folder, lines=[{"t": "text", "on": False, "s": ""}],
                               created_by=request.user, updated_by=request.user)
    return redirect("memo_edit", pk=memo.pk)


@login_required
@never_cache  # 뒤로 가기로 옛 내용이 다시 뜨지 않게
def memo_edit(request, pk):
    memo = _memo(request, pk)
    folders = request.user.couple.memo_folders.all()
    data = {"lines": memo.lines or [{"t": "text", "on": False, "s": ""}], "version": memo.version}
    return render(request, "memos/edit.html", {"memo": memo, "folders": folders, "data": data})


@login_required
@require_POST
def memo_save(request, pk):
    """JSON {lines, version}. 버전이 다르면 409 와 서버 것 (덮어쓰지 않는다)."""
    memo = _memo(request, pk)
    try:
        body = json.loads(request.body or b"{}")
        lines = clean_lines(body.get("lines")) if isinstance(body, dict) else None
        version = body.get("version") if isinstance(body, dict) else None
    except (ValueError, UnicodeDecodeError):
        lines = None
    if lines is None or not isinstance(version, int):
        return JsonResponse({"ok": False, "error": "저장하지 못했어요. 잠시 뒤 다시 해 볼까요?"}, status=400)
    with transaction.atomic():
        memo = Memo.objects.select_for_update().get(pk=memo.pk)
        if version != memo.version:
            return JsonResponse({"ok": False, "lines": memo.lines, "version": memo.version}, status=409)
        memo.lines = lines
        memo.title, memo.preview = title_and_preview(lines)
        memo.version += 1
        memo.updated_by = request.user
        memo.save()
    return JsonResponse({"ok": True, "version": memo.version, "title": memo.title})


@login_required
@require_POST
def memo_move(request, pk):
    memo = _memo(request, pk)
    target = request.POST.get("folder", "")
    folder = request.user.couple.memo_folders.filter(pk=target).first() if target.isdigit() else None
    if folder:
        memo.folder = folder
        memo.save(update_fields=["folder"])
        messages.success(request, f"'{folder.name}' 폴더로 옮겼어요.")
    return redirect("memo_edit", pk=memo.pk)


@login_required
@require_POST
def memo_delete(request, pk):
    memo = _memo(request, pk)
    folder_pk = memo.folder_id
    memo.delete()
    messages.success(request, "메모를 지웠어요.")
    return redirect("memo_folder", pk=folder_pk)
