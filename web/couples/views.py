import calendar as month_calendar
import json
from collections import defaultdict
from datetime import date, time, timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Exists, F, OuterRef
from urllib.parse import urlencode

from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from accounts.avatars import fix_color_on_join
from anniversaries import services as anniversary_services
from memos.models import Memo

from . import ics, linkpreview, places, placesearch, quota, services
from .storage import MAX_IMAGE_BYTES, delete_file
from .forms import (
    AlbumForm, CreateForm, EventForm, JoinForm, LabelForm, MomentForm, QuickEventForm, PhotoForm, PlaceForm, ProfileForm, TasteCommentForm, WishListForm, WishPlaceForm,
)
from .models import Album, CalendarFeed, Couple, Event, Label, Photo, RegionMark, Taste, TasteComment, TasteLike, WishList, WishPlace


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
                fix_color_on_join(request.user)  # 상대와 같은 색이면 다른 색으로
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
            names = (
                list(couple.photos.values_list("image", flat=True))
                + list(couple.photos.exclude(thumb="").values_list("thumb", flat=True))
                + list(couple.tastes.values_list("image", flat=True))
            )
            for name in names:
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
            "events": Event.objects.visible_to(user).not_past(today).select_related("created_by").prefetch_related("labels")[:3],
            "tastes": Taste.objects.filter(couple=couple).select_related("author")[:3],
            "photos": Photo.objects.filter(couple=couple)[:4],
            # 최근 고친 메모 (제목 있는 것만)
            "memos": Memo.objects.filter(couple=couple).exclude(title="").select_related("folder")[:3],
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


def calendar_lanes(week, events):
    """큰 달력 한 주의 막대 조각. 같은 일정은 그 주 안에서 같은 줄(lane)에 둔다.

    돌려주는 것: 날마다 [{"event", "lane", "start", "end", "title"}] (lane 순).
    start/end = 그 조각이 일정의 첫날/끝날인지, title = 제목을 쓸 조각(첫날이거나 주의 첫 칸).
    """
    first, last = week[0], week[-1]
    inside = [e for e in events if e.date <= last and e.last_date >= first]
    # 여러 날 먼저, 일찍 시작하는 것, 긴 것, 시작 시간, 만든 순
    inside.sort(key=lambda e: (not e.is_multi_day, e.date, -e.span_days, e.start_time is not None, e.start_time or time.min, e.pk))
    taken = [set() for _ in week]  # 날마다 쓰인 줄
    days = [[] for _ in week]
    for e in inside:
        idx = [i for i, d in enumerate(week) if e.date <= d <= e.last_date]
        lane = 0
        while any(lane in taken[i] for i in idx):
            lane += 1
        for i in idx:
            taken[i].add(lane)
            d = week[i]
            days[i].append({"event": e, "lane": lane, "start": d == e.date, "end": d == e.last_date, "title": d == e.date or i == 0})
    for day in days:
        day.sort(key=lambda p: p["lane"])
    return days


@login_required
@ensure_csrf_cookie  # 끌어서 옮기기(calendar-drag.js)가 csrftoken 쿠키를 읽는다
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
    grid_start, grid_end = weeks[0][0], weeks[-1][-1]
    # 여러 날 일정은 걸친 날마다 넣는다 (달력 범위 안만)
    for event in visible.overlapping(grid_start, grid_end):
        d = max(event.date, grid_start)
        while d <= min(event.last_date, grid_end):
            by_date[d].append(event)
            d += timedelta(days=1)

    grid = []
    for week in weeks:
        week_events = list({e.pk: e for d in week for e in by_date.get(d, [])}.values())
        lanes = calendar_lanes(week, week_events)
        row = []
        for i, d in enumerate(week):
            # 큰 달력 칸은 줄 0·1 만 보인다. 빈 줄은 None 자리로 높이를 맞춘다
            shown = [None, None]
            for p in lanes[i]:
                if p["lane"] < 2:
                    shown[p["lane"]] = p
            while shown and shown[-1] is None:
                shown.pop()
            row.append({
                "date": d,
                "day": d.day,
                "in_month": d.month == first.month,
                "is_today": d == today,
                "events": by_date.get(d, []),
                "pieces": shown,
                "more": sum(1 for p in lanes[i] if p["lane"] >= 2),
            })
        grid.append(row)

    upcoming = list(visible.not_past(today)[:3])

    # 이름표 모아 보기: ?label=<id> 이면 그 이름표가 붙은 일정만 (다가오는 것 먼저, 지난 것은 아래에)
    label = None
    label_upcoming, label_past = [], []
    label_id = request.GET.get("label", "")
    if label_id.isdigit():
        label = user.couple.labels.filter(pk=int(label_id)).first()
    if label:
        tagged = visible.filter(labels=label)
        label_upcoming = list(tagged.not_past(today))
        label_past = list(tagged.exclude(pk__in=[e.pk for e in label_upcoming]).order_by("-date", "-start_time"))

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
            "upcoming": upcoming,
            "days": user.couple.days_together,
            "next_item": anniversaries[0] if anniversaries else None,
            "labels": user.couple.labels.filter(events__in=visible).distinct(),
            "label": label,
            # 이름표로 거를 때 큰 달력에서 그 이름표가 없는 일정은 흐리게
            "label_event_ids": set(visible.filter(labels=label).values_list("pk", flat=True)) if label else set(),
            "label_upcoming": label_upcoming,
            "label_past": label_past,
            "month_param": f"{first:%Y-%m}",
            "last_move": _last_move(request, today),
        },
    )


@login_required
def labels(request):
    """이름표 관리: @카테고리와 #태그, 각각 붙은 일정 수 (내가 볼 수 있는 일정만 센다)."""
    user = request.user
    all_labels = list(user.couple.labels.all())
    counts = {l.pk: 0 for l in all_labels}
    visible = Event.objects.visible_to(user)
    for row in Label.events.through.objects.filter(event__in=visible, label__in=all_labels).values("label_id").annotate(n=Count("id")):
        counts[row["label_id"]] = row["n"]
    for l in all_labels:
        l.count = counts[l.pk]
    return render(request, "couples/labels.html", {
        "categories": [l for l in all_labels if l.kind == Label.CATEGORY],
        "tags": [l for l in all_labels if l.kind == Label.TAG],
    })


@login_required
def label_create(request):
    form = LabelForm(request.POST or None, couple=request.user.couple)
    if request.method == "POST" and form.is_valid():
        label = form.save(commit=False)
        label.couple = request.user.couple
        label.save()
        messages.success(request, f"{label.token} 이름표를 만들었어요.")
        return redirect("labels")
    return render(request, "couples/label_form.html", {"form": form, "label": None})


@login_required
def label_update(request, pk):
    label = get_object_or_404(Label, pk=pk, couple=request.user.couple)
    form = LabelForm(request.POST or None, instance=label, couple=request.user.couple)
    if request.method == "POST" and form.is_valid():
        target = form.merge_into
        if target:
            # 같은 이름이 이미 있으면 합친다: 일정을 그 이름표로 옮기고 이것은 지운다 (색은 원래 있던 것)
            with transaction.atomic():
                through = Label.events.through
                have = set(through.objects.filter(label=target).values_list("event_id", flat=True))
                through.objects.bulk_create(
                    [through(event_id=eid, label=target) for eid in label.events.values_list("pk", flat=True) if eid not in have]
                )
                label.delete()
            messages.success(request, f"{target.token}에 합쳤어요.")  # '에' 는 받침과 상관없이 자연스럽다
        else:
            form.save()
            messages.success(request, "이름표를 고쳤어요.")
        return redirect("labels")
    return render(request, "couples/label_form.html", {"form": form, "label": label})


@login_required
@require_POST
def label_delete(request, pk):
    """이름표만 지운다. 붙어 있던 일정은 그대로 남는다."""
    label = get_object_or_404(Label, pk=pk, couple=request.user.couple)
    label.delete()
    messages.success(request, "이름표를 지웠어요. 일정은 그대로 남아 있어요.")
    return redirect("labels")


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
    # 날짜 팝업에서 '자세히 쓰기' 로 넘어온 값들 (폼이 다시 검사한다)
    if request.GET.get("text"):
        initial["text"] = request.GET["text"][:140]
    for key in ("start_time", "end_time", "end_date"):
        if request.GET.get(key):
            initial[key] = request.GET[key][:10]
    if request.GET.get("scope") in ("shared", "personal"):
        initial["scope"] = request.GET["scope"]
    if request.GET.get("all_day") == "on":
        initial["all_day"] = True
    form = EventForm(request.POST or None, initial={"date": timezone.localdate(), **initial})
    if request.method == "POST" and form.is_valid():
        event = services.save_event(Event(created_by=request.user), couple, form.cleaned_data)
        return redirect(_calendar_url(event.date))
    return render(request, "couples/event_form.html", {"form": form, "labels": couple.labels.all(), "event": None})


@login_required
def day_popup(request, day):
    """캘린더 날짜 팝업(조각 HTML): 그날에 걸친 일정 + 빠른 추가. 저장 성공이면 JSON 으로 돌아갈 주소."""
    try:
        the_day = date.fromisoformat(day)
    except ValueError:
        raise Http404
    couple = request.user.couple
    form = QuickEventForm(request.POST or None, initial={"date": the_day, "all_day": True, "scope": "shared"})
    if request.method == "POST":
        if form.is_valid():
            data = {**form.cleaned_data, "place": "", "memo": "", "color": "sky"}
            event = services.save_event(Event(created_by=request.user), couple, data)
            return JsonResponse({"ok": True, "url": _calendar_url(event.date)})
    events = (Event.objects.visible_to(request.user).overlapping(the_day, the_day)
              .select_related("created_by").prefetch_related("labels")
              # 하루 종일·여러 날 먼저, 그다음 시작 시간 순 (DB 마다 빈 시간 순서가 달라 명시)
              .order_by(F("start_time").asc(nulls_first=True), "date", "pk"))
    res = render(request, "couples/_day_popup.html", {
        "day": the_day, "events": events, "form": form, "labels": couple.labels.all(),
        "full_url": f"{reverse('event_create')}?date={the_day:%Y-%m-%d}",
    })
    if request.method == "POST":
        res.status_code = 400
    return res


@login_required
def event_update(request, pk):
    event = _event_for_user(request, pk)
    couple = request.user.couple
    # 지난 일정(오늘보다 전)은 보기만 한다. 지우기는 따로(event_delete) 된다
    locked = event.is_past
    if locked and request.method == "POST":
        messages.error(request, "지난 일정은 고칠 수 없어요.")
        return redirect(_calendar_url(event.date))
    if request.method == "POST":
        form = EventForm(request.POST)
    else:
        form = EventForm(initial=_event_initial(event))
    if request.method == "POST" and form.is_valid():
        services.save_event(event, couple, form.cleaned_data)
        messages.success(request, "일정을 바꿨어요.")
        return redirect(_calendar_url(event.date))
    return render(request, "couples/event_form.html", {
        "form": form, "labels": [] if locked else couple.labels.all(), "event": event, "locked": locked,
    })


MOVE_NOTE_SECONDS = 600


def _last_move(request, today):
    """옮긴 뒤 한 번 보이는 안내. 되돌리면 지난 일정이 되는 경우(자정이 지난 뒤 등)는 되돌리기를 뺀다."""
    note = request.session.pop("last_move", None)
    if not note:
        return None
    # 다시 불러오기가 끊겨 한참 뒤에 보이는 안내는 버린다 (10분)
    if timezone.now().timestamp() - note.get("at", 0) > MOVE_NOTE_SECONDS:
        return None
    if note.get("undo_last", "") < today.isoformat():
        note["undo_date"] = None
    return note


@login_required
@require_POST
def event_move(request, pk):
    """큰 달력에서 끌어서 옮기기. JSON {"date": 새 시작일}. 날짜만 바뀌고 여러 날 일정은 길이를 유지한다."""
    event = _event_for_user(request, pk)
    fail = "옮기지 못했어요. 잠시 뒤 다시 해 볼까요?"
    try:
        data = json.loads(request.body or b"{}")
        new_start = date.fromisoformat(data["date"]) if isinstance(data, dict) and isinstance(data.get("date"), str) else None
    except (ValueError, UnicodeDecodeError):
        new_start = None
    if new_start is None:
        return JsonResponse({"ok": False, "error": fail}, status=400)
    today = timezone.localdate()
    if event.is_past:
        return JsonResponse({"ok": False, "error": "지난 일정은 옮길 수 없어요."}, status=400)
    shift = new_start - event.date
    try:
        new_last = event.last_date + shift
    except OverflowError:  # 9999년을 넘는 날짜 (손으로 만든 요청)
        return JsonResponse({"ok": False, "error": fail}, status=400)
    if new_last < today:
        return JsonResponse({"ok": False, "error": "지난 날로는 옮길 수 없어요."}, status=400)
    undoing = data.get("undo") is True
    old_start = event.date
    event.date = new_start
    if event.end_date:
        event.end_date += shift
    event.save(update_fields=["date", "end_date"])
    # 다음에 그려지는 캘린더 위쪽에 한 번 보여 줄 안내와 되돌리기 (되돌려도 지난 일정이 안 될 때만)
    # 되돌리기로 온 요청이면 "되돌렸어요" 만 (또 되돌리기 버튼은 없다)
    request.session["last_move"] = {
        "event": event.pk,
        "text": "되돌렸어요." if undoing else f"{new_start.month}월 {new_start.day}일로 옮겼어요.",
        "undo_date": None if undoing else old_start.isoformat(),
        "undo_last": (event.last_date - shift).isoformat(),  # 되돌리면 끝나는 날
        "at": timezone.now().timestamp(),
    }
    return JsonResponse({"ok": True, "date": event.date.isoformat(), "end_date": event.end_date.isoformat() if event.end_date else None})


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
        "end_date": event.end_date,
        "all_day": event.start_time is None,
        "start_time": event.start_time,
        "end_time": event.end_time,
        "place": event.place,
        "memo": event.memo,
        "scope": event.scope,
        "color": event.color,
    }


# ---------- 취향 ----------

@login_required
def taste(request):
    """추억. 순간(영화·음악·영상·책)과 기록(장소 지도·목록)."""
    couple, user = request.user.couple, request.user
    tab = "record" if request.GET.get("tab") == "record" else "moment"
    common = {"tab_name": tab, "kakao_js_key": settings.KAKAO_JS_KEY}
    if tab == "record":
        places = (
            Taste.objects.filter(couple=couple, category=Taste.PLACE)
            .annotate(photo_count=Count("place_photos", distinct=True))
            .order_by(F("latitude").asc(nulls_last=True), "-created_at", "-pk")
        )
        # 가고 싶은 곳 카드를 누르면 바로 아래에 펼쳐 보이는 목록(태그)들. 숫자는 아직 안 다녀온 곳
        from django.db.models import Q

        wish_lists = couple.wish_lists.annotate(open_count=Count("places", filter=Q(places__visited_at__isnull=True)))
        wish_open_count = WishPlace.objects.filter(couple=couple, visited_at__isnull=True).count()
        return render(request, "couples/taste.html", {
            **common, "places": places, "wish_open_count": wish_open_count, "wish_lists": wish_lists,
        })

    partner = user.partner
    category = request.GET.get("cat", "전체")
    if category not in Taste.MOMENT_TAGS:
        category = "전체"
    who = request.GET.get("who", "all")
    tastes = Taste.objects.filter(couple=couple).exclude(category=Taste.PLACE).select_related("author").annotate(
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
    # 머리 줄 작은 버튼: 지금 값을 보여 주고, 누르면 다음 값(둘 다 → 나 → 상대 → 둘 다)
    values = [v for v, _ in who_options]
    at = values.index(who) if who in values else 0
    who_label = who_options[at][1]
    who_next = values[(at + 1) % len(values)]
    params = {} if who_next == "all" else {"who": who_next}
    if category != "전체":
        params["cat"] = category
    who_next_query = "?" + urlencode(params) if params else "?"
    return render(
        request,
        "couples/taste.html",
        {
            **common,
            "tastes": tastes,
            "categories": ["전체", *Taste.MOMENT_TAGS],
            "category": category,
            "who": who,
            "who_label": who_label,
            "who_next_query": who_next_query,
        },
    )


@login_required
def place_map_data(request):
    """기록 지도에 찍을 장소들. 내 커플의 위치 있는 장소만."""
    places = (
        Taste.objects.filter(couple=request.user.couple, category=Taste.PLACE, latitude__isnull=False, longitude__isnull=False)
        .annotate(photo_count=Count("place_photos", distinct=True))
        .order_by("-created_at", "-pk")
    )
    return JsonResponse(
        {
            "places": [
                {"id": p.pk, "name": p.title, "lat": p.latitude, "lng": p.longitude, "photos": p.photo_count,
                 "url": reverse("taste_detail", args=[p.pk]), "address": p.address,
                 "strip": reverse("place_photo_strip", args=[p.pk])}
                for p in places
            ]
        }
    )

def _photo_day(qs):
    """찍은 날(없으면 올린 날)을 day 로 붙인다."""
    from django.db.models.functions import Coalesce, TruncDate

    return qs.annotate(day=Coalesce("taken_on", TruncDate("created_at")))


def _photo_item(p, with_coords=False):
    # 핀(with_coords)은 작은 사진이 없으면 null (핀에 원본을 받지 않는다), 사진 줄은 원본으로 대신한다
    thumb = p.thumb.url if p.thumb else (None if with_coords else p.image.url)
    item = {"id": p.pk, "thumb": thumb,
            "url": reverse("photo_detail", args=[p.pk]), "date": p.day.isoformat()}
    if with_coords:
        item.update(lat=p.latitude, lng=p.longitude)
    return item


PHOTO_PINS_MAX = 500
PLACE_STRIP_MAX = 60


@login_required
def photo_map_data(request):
    """사진 핀: 위치 있는 사진 중 장소에 안 묶였거나 묶인 장소에 위치가 없는 것. 최근 찍은 순 500장."""
    from django.db.models import Q

    photos = (
        _photo_day(Photo.objects.filter(couple=request.user.couple, latitude__isnull=False, longitude__isnull=False))
        .filter(Q(place__isnull=True) | Q(place__latitude__isnull=True) | Q(place__longitude__isnull=True))
        .order_by("-day", "-pk")[:PHOTO_PINS_MAX]
    )
    return JsonResponse({"photos": [_photo_item(p, with_coords=True) for p in photos]})


@login_required
def place_photo_strip(request, pk):
    """장소 카드의 사진 줄: 그 장소 사진을 찍은 날 순서로 60장까지."""
    place = get_object_or_404(Taste, pk=pk, couple=request.user.couple, category=Taste.PLACE)
    photos = _photo_day(place.place_photos.all())
    total = photos.count()
    # 최근 60장을 골라 날짜 순서로 (자주 가는 곳도 최근 방문이 보이게)
    recent = sorted(photos.order_by("-day", "-pk")[:PLACE_STRIP_MAX], key=lambda p: (p.day, p.pk))
    return JsonResponse({
        "photos": [_photo_item(p) for p in recent],
        "total": total,
        "more_url": reverse("taste_detail", args=[place.pk]),
    })


# ---------- 가고 싶은 곳 ----------

@login_required
def wishes(request):
    """가고 싶은 곳. 목록 칩으로 거르고, 아직 안 다녀온 곳 먼저."""
    couple = request.user.couple
    lists = couple.wish_lists.all()
    current = None
    places = couple.wish_places.prefetch_related("lists")
    list_id = request.GET.get("list", "")
    if list_id.isdigit():
        current = lists.filter(pk=int(list_id)).first()
        if current:
            places = places.filter(lists=current)
    return render(
        request,
        "couples/wishes.html",
        {"lists": lists, "current": current, "places": places, "kakao_js_key": settings.KAKAO_JS_KEY},
    )


def _wish_back(request):
    """돌아갈 곳: 기록 지도 겹쳐 보기에서 왔으면(?from=record) 기록 탭, 아니면 가고 싶은 곳 화면."""
    if request.GET.get("from") == "record":
        return f"{reverse('tastes')}?tab=record"
    return reverse("wishes")


def _wish_form_page(request, form, wish):
    return render(request, "couples/wish_form.html", {
        "form": form, "wish": wish, "kakao_js_key": settings.KAKAO_JS_KEY, "back_url": _wish_back(request),
    })


@login_required
def wish_create(request):
    form = WishPlaceForm(request.POST or None, couple=request.user.couple)
    if request.method == "POST" and form.is_valid():
        form.save_for(request.user.couple, request.user)
        messages.success(request, "가고 싶은 곳에 저장했어요.")
        return redirect("wishes")
    return _wish_form_page(request, form, None)


@login_required
def wish_update(request, pk):
    wish = get_object_or_404(WishPlace, pk=pk, couple=request.user.couple)
    form = WishPlaceForm(request.POST or None, instance=wish, couple=request.user.couple)
    if request.method == "POST" and form.is_valid():
        form.save_for(request.user.couple, request.user)
        messages.success(request, "고쳤어요.")
        return redirect(_wish_back(request))
    return _wish_form_page(request, form, wish)


@login_required
@require_POST
def wish_delete(request, pk):
    get_object_or_404(WishPlace, pk=pk, couple=request.user.couple).delete()
    messages.success(request, "가고 싶은 곳에서 지웠어요.")
    return redirect("wishes")


@login_required
@require_POST
def wish_visited(request, pk):
    """다녀왔어요: 기록 장소를 만들고 가고 싶은 곳에는 다녀옴으로 남긴다 (커플이 함께 본다).
    행을 잠가 두 사람이 동시에 눌러도 기록은 하나만 생긴다."""
    couple = request.user.couple
    with transaction.atomic():
        wish = get_object_or_404(WishPlace.objects.select_for_update(), pk=pk, couple=couple)
        if wish.visited_place_id:
            return redirect("taste_detail", pk=wish.visited_place_id)
        place = Taste.objects.create(
            couple=couple, author=request.user, category=Taste.PLACE, title=wish.name,
            latitude=wish.latitude, longitude=wish.longitude, address=wish.address,
            place_url=wish.place_url, link=wish.link,
        )
        wish.visited_place = place
        if wish.visited_at is None:
            wish.visited_at = timezone.now()
        wish.save(update_fields=["visited_place", "visited_at"])
    places.relink(couple)
    messages.success(request, "기록으로 옮겼어요. 사진은 근처에서 찍은 것이 저절로 모여요.")
    return redirect("taste_detail", pk=place.pk)


WISH_NEAR_RECORD_M = 100


@login_required
def wish_map_data(request):
    """가고 싶은 곳 지도용. ?list= 로 거르고, ?open=1 이면 아직 안 다녀온 곳만 (기록 지도에 겹쳐 볼 때)."""
    wishes_qs = request.user.couple.wish_places.prefetch_related("lists")
    list_id = request.GET.get("list", "")
    if list_id.isdigit():
        wishes_qs = wishes_qs.filter(lists__pk=int(list_id))
    wishes = list(wishes_qs.distinct())
    matched = []
    if request.GET.get("open") == "1":
        # 기록 지도에 겹쳐 볼 때: 아직 안 다녀온 곳만, 그리고 이미 기록한 장소 100m 안의 곳은 핀을 따로 찍지 않고
        # 그 기록 장소에 색·목록을 알려 준다 (기록 핀을 가고 싶은 곳 색으로 바꿔 한 핀으로 보이게)
        records = list(Taste.objects.filter(couple=request.user.couple, category=Taste.PLACE,
                                            latitude__isnull=False, longitude__isnull=False).values_list("pk", "latitude", "longitude"))
        kept = []
        for w in wishes:
            if w.is_visited:
                continue
            near = [(places.distance_m(w.latitude, w.longitude, lat, lng), pk) for pk, lat, lng in records]
            near = [x for x in near if x[0] <= WISH_NEAR_RECORD_M]
            if near:
                matched.append({"place": min(near)[1], "color": w.color, "name": w.name,
                                "lists": [{"name": l.name, "color": l.color} for l in sorted(w.lists.all(), key=lambda l: l.name)]})
            else:
                kept.append(w)
        wishes = kept
    return JsonResponse(
        {
            "matched": matched,
            "places": [
                {"id": w.pk, "name": w.name, "lat": w.latitude, "lng": w.longitude, "color": w.color,
                 "visited": w.is_visited, "url": reverse("wish_update", args=[w.pk]), "address": w.address, "photos": 0,
                 "lists": [{"name": l.name, "color": l.color} for l in sorted(w.lists.all(), key=lambda l: l.name)]}
                for w in wishes
            ]
        }
    )


@login_required
def wishlist_create(request):
    form = WishListForm(request.POST or None, couple=request.user.couple)
    if request.method == "POST" and form.is_valid():
        lst = form.save(commit=False)
        lst.couple, lst.created_by = request.user.couple, request.user
        lst.save()
        messages.success(request, "목록을 만들었어요.")
        return redirect(f"{reverse('wishes')}?list={lst.pk}")
    return render(request, "couples/wishlist_form.html", {"form": form, "wish_list": None})


@login_required
def wishlist_update(request, pk):
    lst = get_object_or_404(WishList, pk=pk, couple=request.user.couple)
    form = WishListForm(request.POST or None, instance=lst, couple=request.user.couple)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "목록을 고쳤어요.")
        return redirect(f"{reverse('wishes')}?list={lst.pk}")
    return render(request, "couples/wishlist_form.html", {"form": form, "wish_list": lst})


@login_required
@require_POST
def wishlist_delete(request, pk):
    """목록만 지운다. 그 안의 가고 싶은 곳은 남는다."""
    get_object_or_404(WishList, pk=pk, couple=request.user.couple).delete()
    messages.success(request, "목록을 지웠어요. 장소는 그대로 남아 있어요.")
    return redirect("wishes")


@login_required
def region_data(request):
    """색칠 지도에 쓸 점(위치 있는 장소·사진)과 직접 표시. 이름·사진 주소는 넣지 않는다."""
    couple = request.user.couple
    places = Taste.objects.filter(couple=couple, category=Taste.PLACE, latitude__isnull=False, longitude__isnull=False)
    photos = couple.photos.filter(latitude__isnull=False, longitude__isnull=False)
    points = [{"lat": p.latitude, "lng": p.longitude, "kind": "place"} for p in places.only("latitude", "longitude")]
    points += [{"lat": p.latitude, "lng": p.longitude, "kind": "photo"} for p in photos.only("latitude", "longitude")]
    # 아직 안 다녀온 가고 싶은 곳: 다녀온 곳과 다른 색(옅게·빗금)으로 칠한다
    wishes = couple.wish_places.filter(visited_at__isnull=True).only("latitude", "longitude")
    points += [{"lat": w.latitude, "lng": w.longitude, "kind": "wish"} for w in wishes]
    marks = [{"level": m.level, "code": m.code, "state": m.state} for m in couple.region_marks.order_by("level", "code")]
    return JsonResponse({"points": points, "marks": marks})


@login_required
@require_POST
def region_mark(request):
    """색칠 지도에서 지역을 직접 칠하기(on)·지우기(off)·자동으로(auto: 표시 지움)."""
    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        data = None
    if not isinstance(data, dict):
        return JsonResponse({"ok": False}, status=400)
    level, code, state = data.get("level"), data.get("code"), data.get("state")
    valid = (
        level in dict(RegionMark.LEVELS)
        and isinstance(code, str) and code.isdigit() and 4 <= len(code) <= 10
        and state in ("on", "off", "auto")
    )
    if not valid:
        return JsonResponse({"ok": False}, status=400)
    couple = request.user.couple
    if state == "auto":
        RegionMark.objects.filter(couple=couple, level=level, code=code).delete()
    else:
        RegionMark.objects.update_or_create(couple=couple, level=level, code=code, defaults={"state": state, "updated_by": request.user})
    return JsonResponse({"ok": True})


@login_required
def place_search(request):
    """장소 기록하기의 검색. 카카오 장소 검색, 모자라면 OpenStreetMap (couples/placesearch.py)."""
    return JsonResponse({"results": placesearch.search(request.GET.get("q", ""))})


def _taste_form_page(request, form, taste):
    """순간이면 순간 쓰기, 장소면 장소 기록하기 화면."""
    if isinstance(form, PlaceForm):
        return render(request, "couples/place_form.html", {"form": form, "taste": taste, "kakao_js_key": settings.KAKAO_JS_KEY})
    return render(request, "couples/taste_form.html", {"form": form, "taste": taste})


@login_required
def taste_create(request):
    is_place = request.GET.get("kind") == "place"
    form_class = PlaceForm if is_place else MomentForm
    form = form_class(request.POST or None, request.FILES or None, couple=request.user.couple)
    if request.method == "POST" and form.is_valid():
        taste = form.save_for(request.user.couple, request.user)
        messages.success(request, "장소를 기록했어요." if is_place else "순간을 남겼어요.")
        return redirect("taste_detail", pk=taste.pk)
    return _taste_form_page(request, form, None)


@login_required
def taste_link_preview(request):
    """쓰는 화면에서 링크를 붙여 넣으면 제목·썸네일을 미리 보여 주고 빈 칸을 채운다."""
    preview = linkpreview.get_preview(request.GET.get("url", "")[:1000])
    return JsonResponse({"ok": not preview.empty, **preview.as_dict()})


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
        "place_photos": taste.place_photos.order_by("taken_on", "created_at", "pk") if taste.is_place else None,
        "kakao_js_key": settings.KAKAO_JS_KEY,
    }


@login_required
def place_photos_edit(request, pk):
    """장소 화면 › 사진 고르기. 고른 사진은 이 장소에 직접 잇고, 뺀 사진은 장소를 뗀다 (둘 다 직접 정한 것)."""
    couple = request.user.couple
    place = get_object_or_404(Taste, pk=pk, couple=couple, category=Taste.PLACE)
    photos = couple.photos.order_by("-taken_on", "-created_at", "-pk")
    if request.method == "POST":
        chosen = {int(v) for v in request.POST.getlist("photos") if v.isdigit()}
        mine = set(photos.values_list("pk", flat=True))
        chosen &= mine
        photos.filter(pk__in=chosen).update(place=place, place_manual=True)
        photos.filter(place=place).exclude(pk__in=chosen).update(place=None, place_manual=True)
        messages.success(request, "사진을 골랐어요.")
        return redirect("taste_detail", pk=place.pk)
    return render(request, "couples/place_photos.html", {"place": place, "photos": photos})


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
    form_class = PlaceForm if taste.is_place else MomentForm
    form = form_class(request.POST or None, request.FILES or None, instance=taste, couple=request.user.couple)
    if request.method == "POST" and form.is_valid():
        form.save_for(request.user.couple, request.user)
        messages.success(request, "고쳤어요.")
        return redirect("taste_detail", pk=taste.pk)
    return _taste_form_page(request, form, taste)


@login_required
@require_POST
def taste_delete(request, pk):
    taste = get_object_or_404(Taste, pk=pk, couple=request.user.couple)
    if taste.image:
        taste.image.delete(save=False)
    was_place = taste.is_place
    if was_place:
        # 지운 장소에 직접 붙였던 사진도 다시 자동 연결로 (근처 다른 장소가 있으면 거기로)
        taste.place_photos.update(place_manual=False)
    taste.delete()
    if was_place:
        places.relink(request.user.couple)  # 그 장소에 붙어 있던 자동 사진을 다른 가까운 장소로
    messages.success(request, "지웠어요.")
    return redirect(f"{reverse('tastes')}?tab=record" if was_place else "tastes")


@login_required
def place_photo_choices(request):
    """장소 고르기의 "사진에서": 위치 있는 내 커플 사진 최근 60장."""
    photos = request.user.couple.photos.filter(latitude__isnull=False, longitude__isnull=False).order_by("-created_at", "-pk")[:60]
    return JsonResponse(
        {"photos": [{"id": p.pk, "src": p.image.url, "lat": p.latitude, "lng": p.longitude, "taken": p.shot_date.isoformat()} for p in photos]}
    )


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


@login_required
def album(request):
    if request.GET.get("view") == "map":  # 예전 앨범 지도 주소 → 추억 › 기록 지도
        focus = request.GET.get("focus")
        return redirect(f"{reverse('tastes')}?tab=record" + (f"&focus={focus}" if focus else ""))
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
    if photo.thumb:
        delete_file(photo.thumb.name)
    photo.image.delete(save=False)
    photo.delete()
    messages.success(request, "사진을 지웠어요.")
    return redirect("albums")
