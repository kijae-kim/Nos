from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import services
from .forms import AnniversaryForm
from .models import Anniversary


def _own(request, pk):
    """다른 커플의 기념일에는 접근할 수 없다."""
    return get_object_or_404(Anniversary, pk=pk, couple=request.user.couple)


@login_required
def index(request):
    upcoming, past = services.build(request.user.couple)
    return render(request, "anniversaries/index.html", {"upcoming": upcoming, "past": past})


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
