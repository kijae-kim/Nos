import json
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db import IntegrityError
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .forms import FolderForm
from .lines import MAX_TOTAL, clean_lines, ensure_default_folders, ordered_folders, title_and_preview
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
    # 수는 글이 있는 메모만 (제목이 비면 빈 메모)
    folders = ordered_folders(couple.memo_folders.annotate(count=Count("memos", filter=~Q(memos__title=""))))
    return render(request, "memos/index.html", {"folders": folders})


@login_required
def folder_create(request):
    form = FolderForm(request.POST or None, couple=request.user.couple)
    if request.method == "POST" and form.is_valid():
        folder = form.save(commit=False)
        folder.couple = request.user.couple
        try:
            folder.save()
        except IntegrityError:  # 상대가 같은 이름을 방금 만든 경우
            form.add_error("name", "이미 있는 폴더 이름이에요.")
        else:
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
    # 방금 내가 만든 빈 메모가 있으면 그걸 다시 연다 (두 번 누름·뒤로 가기로 빈 메모가 쌓이지 않게)
    recent = timezone.now() - timedelta(minutes=10)
    memo = (Memo.objects.filter(couple=couple, folder=folder, created_by=request.user, title="", version=0, created_at__gte=recent)
            .order_by("-pk").first())
    if memo is None:
        memo = Memo.objects.create(couple=couple, folder=folder, lines=[{"t": "text", "on": False, "s": ""}],
                                   created_by=request.user, updated_by=request.user)
    return redirect("memo_edit", pk=memo.pk)


@login_required
@never_cache  # 뒤로 가기로 옛 내용이 다시 뜨지 않게
def memo_edit(request, pk):
    memo = _memo(request, pk)
    folders = ordered_folders(request.user.couple.memo_folders.all())
    data = {"lines": memo.lines or [{"t": "text", "on": False, "s": ""}], "version": memo.version}
    return render(request, "memos/edit.html", {"memo": memo, "folders": folders, "data": data})


@login_required
@require_POST
def memo_save(request, pk):
    """JSON {lines, version}. 버전이 다르면 409 와 서버 것 (덮어쓰지 않는다)."""
    memo = _memo(request, pk)
    too_long = False
    try:
        body = json.loads(request.body or b"{}")
        lines = clean_lines(body.get("lines")) if isinstance(body, dict) else None
        version = body.get("version") if isinstance(body, dict) else None
    except ValueError as e:
        lines, too_long = None, str(e) == "too long"
    except UnicodeDecodeError:
        lines = None
    if lines is None or type(version) is not int:  # bool 은 int 로 치지 않는다
        error = f"메모가 너무 길어요. {MAX_TOTAL // 10000}만 자까지 쓸 수 있어요." if too_long else "저장하지 못했어요. 잠시 뒤 다시 해 볼까요?"
        return JsonResponse({"ok": False, "error": error}, status=400)
    with transaction.atomic():
        memo = Memo.objects.select_for_update().get(pk=memo.pk)
        if version != memo.version:
            return JsonResponse({"ok": False, "lines": memo.lines, "version": memo.version}, status=409)
        memo.lines = lines
        memo.title, memo.preview = title_and_preview(lines)
        memo.version += 1
        memo.updated_by = request.user
        memo.save()
    return JsonResponse({"ok": True, "version": memo.version, "title": memo.title,
                         "updated": timezone.localtime(memo.updated_at).isoformat()})


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
