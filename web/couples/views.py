import calendar as month_calendar
from collections import defaultdict
from datetime import date

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Exists, OuterRef
from urllib.parse import urlencode

from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from anniversaries import services as anniversary_services

from . import ics, quota, services
from .storage import MAX_IMAGE_BYTES, delete_file
from .forms import AlbumForm, CreateForm, EventForm, JoinForm, PhotoForm, ProfileForm, TasteCommentForm, TasteForm
from .models import Album, CalendarFeed, Couple, Event, Photo, Taste, TasteComment, TasteLike


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
            for name in list(couple.photos.values_list("image", flat=True)) + list(couple.tastes.values_list("image", flat=True)):
                delete_file(name)
            couple.delete()
    return redirect("couple_connect")


@login_required
def home(request):
    user, couple = request.user, request.user.couple
    today = timezone.localdate()
    upcoming, _ = anniversary_services.build(couple)
    return render(
        request,
        "couples/home.html",
        {
            "couple": couple,
            "partner": user.partner,
            "days": couple.days_together,
            "next_item": upcoming[0] if upcoming else None,
            "anniversaries": upcoming[:3],
            # 공통 일정과 내 개인 일정만 보인다 (캘린더와 같은 규칙)
            "events": Event.objects.visible_to(user).filter(date__gte=today).select_related("created_by").prefetch_related("labels")[:3],
            "tastes": Taste.objects.filter(couple=couple).select_related("author")[:3],
            "photos": Photo.objects.filter(couple=couple)[:4],
        },
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
    return render(
        request,
        "couples/us.html",
        {"form": form, "couple": couple, "partner": user.partner, "days": couple.days_together},
    )


# ---------- 캘린더 ----------

def _month_param(value, today):
    """?month=2026-11 을 날짜로 바꾼다. 잘못된 값이면 이번 달."""
    try:
        year, month = map(int, value.split("-"))
        return date(year, month, 1)
    except (AttributeError, ValueError):
        return date(today.year, today.month, 1)


def _shift_month(first, step):
    month_index = first.year * 12 + first.month - 1 + step
    return date(month_index // 12, month_index % 12 + 1, 1)


def _calendar_url(day):
    return f"{reverse('calendar')}?month={day:%Y-%m}&day={day:%Y-%m-%d}"


@login_required
def calendar(request):
    user = request.user
    today = timezone.localdate()
    first = _month_param(request.GET.get("month"), today)
    try:
        selected = date.fromisoformat(request.GET.get("day", ""))
    except ValueError:
        selected = today
    if selected.year != first.year or selected.month != first.month:
        selected = first

    # 일요일부터 시작하는 달력. 앞뒤 달의 날짜도 함께 받아 주차를 채운다.
    weeks = month_calendar.Calendar(firstweekday=6).monthdatescalendar(first.year, first.month)
    visible = Event.objects.visible_to(user).select_related("created_by").prefetch_related("labels")
    by_date = defaultdict(list)
    for event in visible.filter(date__gte=weeks[0][0], date__lte=weeks[-1][-1]):
        by_date[event.date].append(event)

    grid = [
        [
            {
                "date": d,
                "day": d.day,
                "in_month": d.month == first.month,
                "is_today": d == today,
                "is_selected": d == selected,
                "events": by_date.get(d, []),
            }
            for d in week
        ]
        for week in weeks
    ]

    upcoming = list(visible.filter(date__gte=today)[:3])
    day_events = by_date.get(selected, [])
    list_title = "다가오는 일정" if selected == today else f"{selected.month}월 {selected.day}일"
    if selected == today:
        day_events = upcoming

    # 이름표 모아 보기: ?label=<id> 이면 그 이름표가 붙은 일정만 (다가오는 것 먼저, 지난 것은 아래에)
    label = None
    label_upcoming, label_past = [], []
    label_id = request.GET.get("label", "")
    if label_id.isdigit():
        label = user.couple.labels.filter(pk=int(label_id)).first()
    if label:
        tagged = visible.filter(labels=label)
        label_upcoming = list(tagged.filter(date__gte=today))
        label_past = list(tagged.filter(date__lt=today).order_by("-date", "-start_time"))

    anniversaries, _ = anniversary_services.build(user.couple)
    return render(
        request,
        "couples/calendar.html",
        {
            "today": today,
            "first": first,
            "selected": selected,
            "prev_url": f"?month={_shift_month(first, -1):%Y-%m}",
            "next_url": f"?month={_shift_month(first, 1):%Y-%m}",
            "weeks": grid,
            "day_events": day_events,
            "upcoming": upcoming,
            "list_title": list_title,
            "new_event_url": f"/calendar/events/new/?date={selected:%Y-%m-%d}",
            "days": user.couple.days_together,
            "next_item": anniversaries[0] if anniversaries else None,
            "labels": user.couple.labels.filter(events__in=visible).distinct(),
            "label": label,
            "label_upcoming": label_upcoming,
            "label_past": label_past,
            "month_param": f"{first:%Y-%m}",
        },
    )


@login_required
def calendar_subscribe(request):
    """캘린더 앱에서 보기: 구독 주소를 보여 주고, 개인 일정 넣기와 주소 새로 만들기를 한다."""
    feed, _ = CalendarFeed.objects.get_or_create(user=request.user)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "personal":
            feed.include_personal = request.POST.get("include_personal") == "on"
            feed.save(update_fields=["include_personal"])
            messages.success(request, "개인 일정도 넣어요." if feed.include_personal else "공통 일정만 넣어요.")
        elif action == "reset":
            feed.reset_token()
            messages.success(request, "새 주소를 만들었어요. 캘린더 앱에서 예전 구독을 지우고 다시 추가해 주세요.")
        return redirect("calendar_subscribe")

    url = request.build_absolute_uri(reverse("calendar_feed", args=[feed.token]))
    webcal = "webcal://" + url.split("://", 1)[1]
    return render(
        request,
        "couples/calendar_subscribe.html",
        {
            "feed": feed,
            "feed_url": url,
            "webcal_url": webcal,
            "google_url": "https://calendar.google.com/calendar/render?" + urlencode({"cid": webcal}),
        },
    )


def calendar_feed(request, token):
    """캘린더 앱이 읽어 가는 ICS. 로그인 없이 주소(열쇠)로만 연다."""
    feed = get_object_or_404(CalendarFeed.objects.select_related("user__couple"), token=token)
    response = HttpResponse(ics.build_calendar(feed), content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = 'inline; filename="nos.ics"'
    response["Cache-Control"] = "private, max-age=900"
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


def _event_for_user(request, pk):
    return get_object_or_404(Event.objects.visible_to(request.user), pk=pk)


@login_required
def event_create(request):
    couple = request.user.couple
    initial = {}
    day = request.GET.get("date")
    if day:
        initial["date"] = day
    form = EventForm(request.POST or None, initial=initial or {"date": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        event = services.save_event(Event(created_by=request.user), couple, form.cleaned_data)
        return redirect(_calendar_url(event.date))
    return render(request, "couples/event_form.html", {"form": form, "labels": couple.labels.all(), "event": None})


@login_required
def event_update(request, pk):
    event = _event_for_user(request, pk)
    couple = request.user.couple
    if request.method == "POST":
        form = EventForm(request.POST)
    else:
        form = EventForm(initial=_event_initial(event))
    if request.method == "POST" and form.is_valid():
        services.save_event(event, couple, form.cleaned_data)
        messages.success(request, "일정을 바꿨어요.")
        return redirect(_calendar_url(event.date))
    return render(request, "couples/event_form.html", {"form": form, "labels": couple.labels.all(), "event": event})


@login_required
@require_POST
def event_delete(request, pk):
    event = _event_for_user(request, pk)
    day = event.date
    event.delete()
    messages.success(request, "일정을 지웠어요.")
    return redirect(_calendar_url(day))


def _event_initial(event):
    return {
        "text": services.label_text(event),
        "date": event.date,
        "all_day": event.start_time is None,
        "start_time": event.start_time,
        "end_time": event.end_time,
        "place": event.place,
        "scope": event.scope,
        "color": event.color,
    }


# ---------- 취향 ----------

@login_required
def taste(request):
    couple, user = request.user.couple, request.user
    partner = user.partner
    category = request.GET.get("cat", "전체")
    who = request.GET.get("who", "all")

    tastes = Taste.objects.filter(couple=couple).select_related("author").annotate(
        like_count=Count("likes", distinct=True),
        comment_count=Count("comments", distinct=True),
        liked=Exists(TasteLike.objects.filter(taste=OuterRef("pk"), user=user)),
    )
    if category != "전체":
        tastes = tastes.filter(category=category)
    if who.isdigit():
        tastes = tastes.filter(author_id=int(who))

    who_options = [("all", "둘 다"), (str(user.pk), user.display_name)]
    if partner:
        who_options.append((str(partner.pk), partner.display_name))
    return render(
        request,
        "couples/taste.html",
        {
            "tastes": tastes,
            "categories": ["전체", *Taste.CATEGORIES],
            "category": category,
            "who_options": who_options,
            "who": who,
        },
    )


@login_required
def taste_create(request):
    form = TasteForm(request.POST or None, request.FILES or None, couple=request.user.couple)
    if request.method == "POST" and form.is_valid():
        taste = form.save_for(request.user.couple, request.user)
        messages.success(request, "취향을 공유했어요.")
        return redirect("taste_detail", pk=taste.pk)
    return render(request, "couples/taste_form.html", {"form": form, "taste": None})


@login_required
def taste_detail(request, pk):
    taste = get_object_or_404(Taste.objects.select_related("author"), pk=pk, couple=request.user.couple)
    return render(request, "couples/taste_detail.html", _taste_detail_context(request, taste))


def _taste_detail_context(request, taste, comment_form=None):
    likers = [like.user for like in taste.likes.select_related("user").order_by("created_at")]
    return {
        "taste": taste,
        "likers": likers,
        "liked": request.user in likers,
        "comments": taste.comments.select_related("author"),
        "comment_form": comment_form or TasteCommentForm(),
    }


def _like_text(likers, user):
    """좋아요 옆에 보일 말: "바다님이 좋아해요", "둘 다 좋아해요" 등."""
    if not likers:
        return "좋아요"
    if len(likers) >= 2:
        return "둘 다 좋아해요"
    return "내가 좋아해요" if likers[0] == user else f"{likers[0].display_name}님이 좋아해요"


@login_required
@require_POST
def taste_like(request, pk):
    """좋아요를 누르면 켜고, 다시 누르면 끈다."""
    taste = get_object_or_404(Taste, pk=pk, couple=request.user.couple)
    like = TasteLike.objects.filter(taste=taste, user=request.user).first()
    if like:
        like.delete()
    else:
        TasteLike.objects.get_or_create(taste=taste, user=request.user)
    if _wants_json(request):
        likers = [l.user for l in taste.likes.select_related("user").order_by("created_at")]
        return JsonResponse({"liked": request.user in likers, "count": len(likers), "text": _like_text(likers, request.user)})
    return redirect("taste_detail", pk=taste.pk)


@login_required
@require_POST
def taste_comment_create(request, pk):
    taste = get_object_or_404(Taste, pk=pk, couple=request.user.couple)
    form = TasteCommentForm(request.POST)
    if form.is_valid():
        TasteComment.objects.create(taste=taste, author=request.user, text=form.cleaned_data["text"])
        return redirect(f"{reverse('taste_detail', args=[taste.pk])}#comments")
    return render(request, "couples/taste_detail.html", _taste_detail_context(request, taste, form), status=400)


@login_required
@require_POST
def taste_comment_delete(request, pk):
    comment = get_object_or_404(TasteComment, pk=pk, taste__couple=request.user.couple, author=request.user)
    taste_pk = comment.taste_id
    comment.delete()
    messages.success(request, "댓글을 지웠어요.")
    return redirect(f"{reverse('taste_detail', args=[taste_pk])}#comments")


@login_required
def taste_update(request, pk):
    taste = get_object_or_404(Taste, pk=pk, couple=request.user.couple)
    form = TasteForm(request.POST or None, request.FILES or None, instance=taste, couple=request.user.couple)
    if request.method == "POST" and form.is_valid():
        form.save_for(request.user.couple, request.user)
        messages.success(request, "취향을 고쳤어요.")
        return redirect("taste_detail", pk=taste.pk)
    return render(request, "couples/taste_form.html", {"form": form, "taste": taste})


@login_required
@require_POST
def taste_delete(request, pk):
    taste = get_object_or_404(Taste, pk=pk, couple=request.user.couple)
    if taste.image:
        taste.image.delete(save=False)
    taste.delete()
    messages.success(request, "취향을 지웠어요.")
    return redirect("tastes")


# ---------- 앨범 ----------

def _memory(couple, today):
    """1년 전 오늘 찍었거나 올린 사진이 있으면 추억 카드에 보여 준다."""
    try:
        last_year = today.replace(year=today.year - 1)
    except ValueError:  # 2월 29일
        last_year = today.replace(year=today.year - 1, day=28)
    photos = [p for p in couple.photos.all() if p.shot_date == last_year]
    return photos[0] if photos else None


@login_required
def _uploaded_notice(request):
    count = request.GET.get("uploaded", "")
    if count.isdigit() and int(count) > 0:
        messages.success(request, f"사진 {int(count)}장을 올렸어요.")


def album(request):
    couple = request.user.couple
    _uploaded_notice(request)
    today = timezone.localdate()
    photos = list(couple.photos.select_related("album"))
    by_month = defaultdict(list)
    for photo in photos:
        by_month[f"{photo.shot_date:%Y년 %m월}"].append(photo)
    return render(
        request,
        "couples/album.html",
        {
            "albums": couple.albums.prefetch_related("photos"),
            "unassigned_count": couple.photos.filter(album__isnull=True).count(),
            "memory": _memory(couple, today),
            "photo_groups": [{"month": m, "photos": ps} for m, ps in by_month.items()],
            "has_photos": bool(photos),
        },
    )


@login_required
def album_detail(request, pk):
    couple = request.user.couple
    album = get_object_or_404(Album, pk=pk, couple=couple)
    if request.method == "GET":
        _uploaded_notice(request)
    form = AlbumForm(request.POST or None, instance=album)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "앨범 이름을 바꿨어요.")
        return redirect("album_detail", pk=album.pk)
    return render(request, "couples/album_detail.html", {"album": album, "form": form, "photos": album.photos.all()})


@login_required
@require_POST
def album_delete(request, pk):
    """앨범만 지운다. 안에 있던 사진은 '앨범 없음'으로 남는다."""
    get_object_or_404(Album, pk=pk, couple=request.user.couple).delete()
    messages.success(request, "앨범을 지웠어요. 사진은 그대로 남아 있어요.")
    return redirect("albums")


def _wants_json(request):
    return "application/json" in request.headers.get("Accept", "")


@login_required
def photo_create(request):
    """사진 올리기. 여러 장은 화면의 스크립트가 한 장씩 따로 보낸다 (Vercel 은 요청 하나에 4.5MB까지만 받는다).
    스크립트가 보낸 요청에는 JSON 으로 답한다. 스크립트가 없으면 고른 사진 한 장만 올라간다."""
    couple = request.user.couple
    form = PhotoForm(request.POST or None, request.FILES or None, couple=couple)
    if request.method == "POST":
        if form.is_valid():
            photo = form.save_for(couple, request.user)
            if _wants_json(request):
                return JsonResponse({"ok": True, "id": photo.pk, "album": photo.album_id})
            messages.success(request, "사진을 올렸어요.")
            return redirect("photo_detail", pk=photo.pk)
        if _wants_json(request):
            errors = [e for field_errors in form.errors.values() for e in field_errors]
            return JsonResponse({"ok": False, "error": errors[0] if errors else "올리지 못했어요."}, status=400)
    return render(
        request,
        "couples/photo_form.html",
        {
            "form": form,
            "photo": None,
            "albums": couple.albums.all(),
            "room": quota.room_for(couple),
            "max_bytes": MAX_IMAGE_BYTES,
            "drive_picker": settings.DRIVE_PICKER,
        },
    )


@login_required
def photo_detail(request, pk):
    photo = get_object_or_404(Photo, pk=pk, couple=request.user.couple)
    return render(request, "couples/photo_detail.html", {"photo": photo})


@login_required
def photo_update(request, pk):
    couple = request.user.couple
    photo = get_object_or_404(Photo, pk=pk, couple=couple)
    form = PhotoForm(request.POST or None, request.FILES or None, instance=photo, couple=couple)
    if request.method == "POST" and form.is_valid():
        form.save_for(couple, request.user)
        messages.success(request, "사진 정보를 고쳤어요.")
        return redirect("photo_detail", pk=photo.pk)
    return render(request, "couples/photo_form.html", {"form": form, "photo": photo, "albums": couple.albums.all()})


@login_required
@require_POST
def photo_delete(request, pk):
    photo = get_object_or_404(Photo, pk=pk, couple=request.user.couple)
    photo.image.delete(save=False)
    photo.delete()
    messages.success(request, "사진을 지웠어요.")
    return redirect("albums")
