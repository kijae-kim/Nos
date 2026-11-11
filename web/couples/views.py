from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from anniversaries import services as anniversary_services

from .forms import CreateForm, JoinForm, ProfileForm
from .models import Couple


def _render_connect(request, create_form=None, join_form=None):
    return render(
        request,
        "couples/connect.html",
        {"create_form": create_form or CreateForm(), "join_form": join_form or JoinForm()},
    )


@login_required
def connect(request):
    if request.user.couple_id:
        return redirect("home")
    return _render_connect(request)


@login_required
@require_POST
def create(request):
    if request.user.couple_id:
        return redirect("home")
    form = CreateForm(request.POST)
    if not form.is_valid():
        return _render_connect(request, create_form=form)
    couple = Couple.objects.create(start_date=form.cleaned_data["start_date"])
    request.user.couple = couple
    request.user.save(update_fields=["couple"])
    return redirect("home")


@login_required
@require_POST
def join(request):
    if request.user.couple_id:
        return redirect("home")
    form = JoinForm(request.POST)
    if form.is_valid():
        with transaction.atomic():
            couple = Couple.objects.select_for_update().filter(invite_code=form.cleaned_data["code"]).first()
            if couple is None:
                form.add_error("code", "초대 코드를 찾을 수 없어요.")
            elif couple.is_full:
                form.add_error("code", "이미 두 사람이 연결된 공간이에요.")
            else:
                request.user.couple = couple
                request.user.save(update_fields=["couple"])
                return redirect("home")
    return _render_connect(request, join_form=form)


@login_required
@require_POST
def leave(request):
    couple = request.user.couple
    if couple:
        request.user.couple = None
        request.user.save(update_fields=["couple"])
        if not couple.members.exists():
            couple.delete()
    return redirect("couple_connect")


@login_required
def home(request):
    couple = request.user.couple
    upcoming, _ = anniversary_services.build(couple)
    return render(
        request,
        "couples/home.html",
        {"couple": couple, "partner": request.user.partner, "anniversaries": upcoming[:3]},
    )


@login_required
def us(request):
    user, couple = request.user, request.user.couple
    if request.method == "POST":
        form = ProfileForm(request.POST)
        if form.is_valid():
            user.nickname = form.cleaned_data["nickname"]
            user.save(update_fields=["nickname"])
            couple.start_date = form.cleaned_data["start_date"]
            couple.save(update_fields=["start_date"])
            messages.success(request, "저장했어요.")
            return redirect("us")
    else:
        form = ProfileForm(initial={"nickname": user.nickname, "start_date": couple.start_date})
    return render(request, "couples/us.html", {"form": form, "couple": couple, "partner": user.partner})


@login_required
def coming_soon(request, title):
    return render(request, "couples/coming_soon.html", {"title": title})
