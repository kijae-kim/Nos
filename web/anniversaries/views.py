from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import services
from .forms import AnniversaryForm
from .models import Anniversary


def _own(request, pk):
    """다른 커플의 기념일에는 접근할 수 없다."""
    return get_object_or_404(Anniversary, pk=pk, couple=request.user.couple)


def _progress(couple, item):
    """자동으로 세는 100일 기념일이면, 직전 100일 구간을 기준으로 진행률을 구한다."""
    if item.anniversary is not None or not item.title.endswith("일") or not couple.start_date:
        return None
    days = couple.days_together
    if days is None:
        return None
    end = int(item.title[:-1])
    start = end - 100
    percent = min(100, max(0, days - start))  # 구간이 100일이므로 날 수가 곧 퍼센트
    return {
        "start": f"{start}일" if start else "시작",
        "end": item.title,
        "today": days,
        "percent": percent,
    }


@login_required
def index(request):
    couple = request.user.couple
    upcoming, past = services.build(couple)
    next_item = upcoming[0] if upcoming else None
    return render(
        request,
        "anniversaries/index.html",
        {
            "next_item": next_item,
            "progress": _progress(couple, next_item) if next_item else None,
            "ahead": upcoming[1:],
            "past": past,
        },
    )


@login_required
def create(request):
    form = AnniversaryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        anniversary = form.save(commit=False)
        anniversary.couple = request.user.couple
        anniversary.created_by = request.user
        anniversary.save()
        return redirect("anniversary_index")
    return render(request, "anniversaries/form.html", {"form": form})


@login_required
def update(request, pk):
    anniversary = _own(request, pk)
    form = AnniversaryForm(request.POST or None, instance=anniversary)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("anniversary_index")
    return render(request, "anniversaries/form.html", {"form": form, "anniversary": anniversary})


@login_required
@require_POST
def delete(request, pk):
    _own(request, pk).delete()
    return redirect("anniversary_index")
