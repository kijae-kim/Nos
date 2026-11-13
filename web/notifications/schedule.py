"""오늘 보낼 기념일 알림을 계산한다. 보내기는 push.py, 언제 부르는지는 views.cron_anniversaries."""

from dataclasses import dataclass
from datetime import date

from anniversaries.services import build

URL = "/anniversaries/"
OFFSETS = (0, 1, 7)  # 당일, 하루 전, 일주일 전


@dataclass
class Due:
    user: object
    key: str  # 같은 알림을 두 번 보내지 않기 위한 열쇠 (PushLog.key)
    title: str
    body: str
    url: str = URL


def josa_ieyo(word):
    """받침이 있으면 '이에요', 없으면 '예요'. 한글로 끝나지 않으면 '이에요'."""
    last = word[-1] if word else ""
    if "가" <= last <= "힣" and (ord(last) - ord("가")) % 28 == 0:
        return f"{word}예요"
    return f"{word}이에요"


def _texts(title, d, offset):
    if offset == 0:
        return f"오늘은 {josa_ieyo(title)}", "함께한 날을 축하해요"
    if offset == 1:
        return f"내일은 {josa_ieyo(title)}", f"{d.month}월 {d.day}일, 미리 준비해 볼까요?"
    return f"{title}까지 일주일 남았어요", f"{d.month}월 {d.day}일이에요"


def _wants(user, offset):
    # 당일 알림은 항상, 하루 전·일주일 전은 그 사람이 켰을 때만
    if offset == 0:
        return True
    if offset == 1:
        return user.notify_day_before
    return user.notify_week_before


def due_for_couple(couple, today: date) -> list[Due]:
    upcoming, _ = build(couple, today)
    members = list(couple.members.all())
    due = []
    for item in upcoming:
        offset = item.days_left
        if offset not in OFFSETS:
            continue
        if item.anniversary is not None:
            key = f"anniv:{item.anniversary.pk}:{item.date.isoformat()}:{offset}"
        else:
            key = f"auto:{item.title}:{item.date.isoformat()}:{offset}"
        title, body = _texts(item.title, item.date, offset)
        due += [Due(user, key, title, body) for user in members if _wants(user, offset)]
    return due
