"""캘린더 구독(ICS) 파일 만들기.

아이폰·구글·네이버 캘린더가 구독 주소를 몇 시간마다 읽어 가서 NÓS 일정을 함께 보여 준다.
한 방향이다: 캘린더 앱에서 고친 내용은 NÓS 로 돌아오지 않는다.
표준(RFC 5545) 중 필요한 만큼만 직접 만든다. 라이브러리를 더하지 않으려고.
"""
from datetime import datetime, timedelta, timezone as dt_timezone

from django.utils import timezone

from anniversaries import services as anniversary_services

from .models import Event

PRODID = "-//NOS//Couple Calendar//KO"
PAST_DAYS = 365  # 지난 일정은 1년 치만 (파일이 너무 커지지 않게)


def escape(text):
    """글자 값 안의 \\ ; , 줄바꿈을 표준대로 바꾼다."""
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def fold(line):
    """한 줄은 75바이트까지. 넘으면 다음 줄을 공백으로 시작해 잇는다 (한글이 중간에 잘리지 않게)."""
    out, current, size = [], "", 0
    for ch in line:
        n = len(ch.encode("utf-8"))
        limit = 75 if not out else 74  # 이어지는 줄은 앞의 공백 한 칸을 뺀다
        if size + n > limit:
            out.append(current)
            current, size = "", 0
        current += ch
        size += n
    out.append(current)
    return "\r\n ".join(out)


def _utc(dt):
    return dt.astimezone(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _day(d):
    return d.strftime("%Y%m%d")


def _event_lines(event, stamp):
    lines = ["BEGIN:VEVENT", f"UID:event-{event.pk}@nos", f"DTSTAMP:{stamp}"]
    if event.start_time:
        tz = timezone.get_current_timezone()
        start = timezone.make_aware(datetime.combine(event.date, event.start_time), tz)
        if event.end_time:
            end = timezone.make_aware(datetime.combine(event.date, event.end_time), tz)
            if end <= start:  # 밤을 넘기는 일정 (예: 22시 ~ 1시)
                end += timedelta(days=1)
        else:
            end = start + timedelta(hours=1)
        lines += [f"DTSTART:{_utc(start)}", f"DTEND:{_utc(end)}"]
    else:
        lines += [f"DTSTART;VALUE=DATE:{_day(event.date)}", f"DTEND;VALUE=DATE:{_day(event.date + timedelta(days=1))}"]
    title = event.title + (" (개인)" if event.scope == Event.PERSONAL else "")
    lines.append(f"SUMMARY:{escape(title)}")
    if event.place:
        lines.append(f"LOCATION:{escape(event.place)}")
    notes = [event.memo] if event.memo else []
    labels = " ".join(label.token for label in event.labels.all())
    if labels:
        notes.append(labels)
    notes.append(f"{event.created_by.display_name}님이 만든 일정")
    lines.append(f"DESCRIPTION:{escape(chr(10).join(notes))}")
    if event.scope == Event.PERSONAL:
        lines.append("CLASS:PRIVATE")
    lines.append("END:VEVENT")
    return lines


def _anniversary_lines(uid, title, day, stamp, yearly=False):
    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}@nos",
        f"DTSTAMP:{stamp}",
        f"DTSTART;VALUE=DATE:{_day(day)}",
        f"DTEND;VALUE=DATE:{_day(day + timedelta(days=1))}",
        f"SUMMARY:{escape(title)}",
        "TRANSP:TRANSPARENT",  # 하루 종일 '바쁨'으로 잡히지 않게
    ]
    if yearly:
        lines.append("RRULE:FREQ=YEARLY")
    lines.append("END:VEVENT")
    return lines


def build_calendar(feed, now=None):
    """구독 주소 하나의 ICS 내용. 공통 일정 + (켜 두었으면) 그 사람의 개인 일정 + 기념일."""
    now = now or timezone.now()
    stamp = _utc(now)
    user = feed.user
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:NÓS",
        "X-WR-TIMEZONE:Asia/Seoul",
        "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
        "X-PUBLISHED-TTL:PT1H",
    ]
    couple = user.couple
    if couple is not None:  # 커플 연결을 끊었으면 빈 캘린더
        # 공통 일정은 늘, 개인 일정은 켜 두었을 때 내 것만 (상대 개인 일정은 절대 넣지 않는다)
        if feed.include_personal:
            events = Event.objects.visible_to(user)
        else:
            events = Event.objects.filter(couple=couple, scope=Event.SHARED)
        since = timezone.localdate() - timedelta(days=PAST_DAYS)
        for event in events.filter(date__gte=since).select_related("created_by").prefetch_related("labels"):
            lines += _event_lines(event, stamp)

        # 직접 등록한 기념일 (생일처럼 매년 반복이면 캘린더 앱이 알아서 해마다 보여 준다)
        for a in couple.anniversaries.all():
            lines += _anniversary_lines(f"anniversary-{a.pk}", a.title, a.date, stamp, yearly=a.repeat_yearly)
        # 100일 단위·주년 (앞으로 다가오는 몇 개)
        for item in anniversary_services.auto_milestones(couple.start_date, timezone.localdate()):
            lines += _anniversary_lines(f"milestone-{item.date:%Y%m%d}", f"우리 {item.title}", item.date, stamp)
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(line) for line in lines) + "\r\n"
