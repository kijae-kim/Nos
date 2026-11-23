"""글로 일정: '12월 25일 찜질방가기' 같은 한 줄에서 날짜·시간·이름을 찾는다 (규칙, 무료).

알아듣는 말
- 날짜: 12월 25일 · 12/25 · 25일 · 오늘·내일·모레·글피 · (이번/다음 주) 금요일
- 기간: 12월 25일~27일 · 12월 30일~1월 2일 · 25~27일
- 시간: 저녁 7시 · 오후 3시 반 · 오전 10시 20분 · 19:30 · 3시~5시
날짜를 못 찾으면 None. 나중에 LLM 을 붙이면 이 함수 자리에서 바꾸면 된다.
"""

import re
from datetime import date, time, timedelta

PERIOD = r"(오전|오후|아침|점심|저녁|밤|새벽)"
HOUR = PERIOD + r"?\s*(\d{1,2})\s*시(?!간)(?:\s*(\d{1,2})\s*분|\s*(반))?"  # "2시간" 은 시간이 아니다
WEEKDAYS = "월화수목금토일"

RE_RANGE_MD = re.compile(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일?\s*[~\-–]\s*(?:(\d{1,2})\s*월\s*)?(\d{1,2})\s*일")
RE_RANGE_D = re.compile(r"(?<!\d)(\d{1,2})\s*일?\s*[~\-–]\s*(\d{1,2})\s*일")
RE_MD = re.compile(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일")
RE_SLASH = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?![\d/])")
RE_D = re.compile(r"(?<!\d)(\d{1,2})\s*일(?!\s*[~\-–])")
RE_REL = re.compile(r"오늘|내일|모레|글피")
RE_WEEK = re.compile(r"(?:(이번|다음|담)\s*주\s*)?([월화수목금토일])요일")
RE_TIME_RANGE = re.compile(HOUR + r"\s*(?:[~\-–]|부터)\s*" + HOUR + r"(?:\s*까지)?")
RE_TIME = re.compile(HOUR)
RE_CLOCK = re.compile(r"(?<!\d)(\d{1,2}):(\d{2})(?:\s*[~\-–]\s*(\d{1,2}):(\d{2}))?")
# 기간을 말하는 글("1박 2일", "3일 동안")은 날짜로 보지 않는다
RE_DURATION = re.compile(r"\d{1,2}\s*박\s*\d{1,2}\s*일|\d{1,2}\s*일\s*(?:동안|간|째)")
RE_PARTICLE = re.compile(r"(^|\s)(에|에는|부터|까지)(?=\s|$)")

REL_DAYS = {"오늘": 0, "내일": 1, "모레": 2, "글피": 3}


def _safe(y, m, d):
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _upcoming_md(m, d, today):
    """올해 그 날짜, 이미 지났으면 내년."""
    found = _safe(today.year, m, d)
    if found and found < today:
        found = _safe(today.year + 1, m, d)
    return found


def _upcoming_d(d, today):
    """이번 달 그 날, 지났으면 다음 달."""
    found = _safe(today.year, today.month, d)
    if found is None or found < today:
        nxt = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
        found = _safe(nxt.year, nxt.month, d)
    return found


def _hour(period, h, minute, half):
    h, m = int(h), int(minute) if minute else (30 if half else 0)
    if h > 24 or m > 59:
        return None
    if period in ("오후", "저녁", "밤") and h < 12:
        h += 12
    elif period == "점심" and h < 5:
        h += 12
    elif period is None and 1 <= h <= 7:  # 시간만 쓰면 1~7시는 오후로 (약속은 대개 낮·저녁)
        h += 12
    return time(h % 24, m)


def _cut(text, m):
    return text[: m.start()] + " " + text[m.end():]


def _find_date(text, today):
    """(시작, 끝 날짜 또는 None, 남은 글). 못 찾으면 None.
    기간 글은 같은 길이의 # 로 가린 사본에서 찾고, 자르기는 원래 글에서 한다 (위치가 같다)."""
    masked = RE_DURATION.sub(lambda d: "#" * len(d[0]), text)
    m = RE_RANGE_MD.search(masked)
    if m:
        start = _upcoming_md(int(m[1]), int(m[2]), today)
        if start:
            end_month = int(m[3]) if m[3] else start.month
            end = _safe(start.year, end_month, int(m[4]))
            if end and end < start:
                end = _safe(start.year + 1, end_month, int(m[4])) if m[3] else None
            if end:
                return start, end, _cut(text, m)
    m = RE_RANGE_D.search(masked)
    if m:
        start = _upcoming_d(int(m[1]), today)
        end = start and _safe(start.year, start.month, int(m[2]))
        if start and end and end < start:  # 30일~2일: 끝은 다음 달
            nxt = (start.replace(day=1) + timedelta(days=32)).replace(day=1)
            end = _safe(nxt.year, nxt.month, int(m[2]))
        if start and end:
            return start, end, _cut(text, m)
    for regex, make, strict in (
        (RE_MD, lambda m: _upcoming_md(int(m[1]), int(m[2]), today), True),
        (RE_SLASH, lambda m: _upcoming_md(int(m[1]), int(m[2]), today), True),
        (RE_REL, lambda m: today + timedelta(days=REL_DAYS[m[0]]), False),
        (RE_WEEK, lambda m: _weekday(m[1], m[2], today), False),
        (RE_D, lambda m: _upcoming_d(int(m[1]), today), False),
    ):
        m = regex.search(masked)
        if m:
            found = make(m)
            if found:
                return found, None, _cut(text, m)
            if strict:  # 2월 30일처럼 없는 날짜를 분명히 썼으면 다른 날로 짐작하지 않는다
                return None
    return None


def _weekday(which, name, today):
    idx = WEEKDAYS.index(name)
    monday = today - timedelta(days=today.weekday())
    if which == "이번":
        return monday + timedelta(days=idx)
    if which in ("다음", "담"):
        return monday + timedelta(days=7 + idx)
    return today + timedelta(days=(idx - today.weekday()) % 7)  # 다가오는 그 요일 (오늘 포함)


def _find_time(text):
    """(시작, 끝, 남은 글)."""
    m = RE_CLOCK.search(text)
    if m:
        start = _safe_time(m[1], m[2])
        end = _safe_time(m[3], m[4]) if m[3] else None
        if start:
            return start, end, _cut(text, m)
    m = RE_TIME_RANGE.search(text)
    if m:
        start = _hour(m[1], m[2], m[3], m[4])
        end = _hour(m[5] or m[1], m[6], m[7], m[8])
        if start and end and end <= start and end.hour < 12:
            end = time(end.hour + 12, end.minute)
        if start and end:
            return start, end, _cut(text, m)
    m = RE_TIME.search(text)
    if m:
        start = _hour(m[1], m[2], m[3], m[4])
        if start:
            return start, None, _cut(text, m)
    return None, None, text


def _safe_time(h, m):
    try:
        return time(int(h), int(m))
    except ValueError:
        return None


def parse(text: str, today: date):
    """{'date', 'end_date', 'start_time', 'end_time', 'title'} 또는 None (날짜를 못 찾음)."""
    text = (text or "").strip()
    if not text:
        return None
    found = _find_date(text, today)
    if not found:
        return None
    start, end, rest = found
    start_time, end_time, rest = _find_time(rest)
    title = RE_PARTICLE.sub(" ", rest)
    title = re.sub(r"\s+", " ", title).strip()
    return {"date": start, "end_date": end, "start_time": start_time, "end_time": end_time, "title": title}
