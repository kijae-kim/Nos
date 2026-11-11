from dataclasses import dataclass
from datetime import date, timedelta

from django.utils import timezone

HUNDRED_DAY_COUNT = 3  # 앞으로 보여 줄 100일 단위 기념일 개수
YEARLY_COUNT = 2  # 앞으로 보여 줄 주년 개수


@dataclass
class Item:
    title: str
    date: date
    days_left: int  # 0이면 오늘, 음수면 지난 날
    anniversary: object = None  # 직접 등록한 기념일이면 Anniversary, 자동 계산이면 None

    @property
    def dday(self):
        if self.days_left == 0:
            return "오늘"
        if self.days_left > 0:
            return f"D-{self.days_left}"
        return f"D+{-self.days_left}"


def add_years(d, years):
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # 2월 29일 → 평년에는 2월 28일
        return d.replace(year=d.year + years, day=28)


def next_occurrence(d, today):
    """매년 반복되는 날짜 d가 today 이후(당일 포함) 처음 돌아오는 날."""
    if d >= today:
        return d
    candidate = add_years(d, today.year - d.year)
    if candidate < today:
        candidate = add_years(d, today.year - d.year + 1)
    return candidate


def auto_milestones(start_date, today):
    """사귄 날 기준 100일 단위와 주년. 사귄 날을 1일째로 센다."""
    if not start_date or start_date > today:
        return []
    items = []

    days_so_far = (today - start_date).days + 1
    first_hundred = -(-days_so_far // 100) * 100  # 오늘이 딱 N00일이면 오늘 포함
    for n in range(first_hundred, first_hundred + 100 * HUNDRED_DAY_COUNT, 100):
        d = start_date + timedelta(days=n - 1)
        items.append(Item(f"{n}일", d, (d - today).days))

    year = max(1, today.year - start_date.year)
    found = 0
    while found < YEARLY_COUNT:
        d = add_years(start_date, year)
        if d >= today:
            items.append(Item(f"{year}주년", d, (d - today).days))
            found += 1
        year += 1
    return items


def build(couple, today=None):
    """(다가오는 기념일, 지난 기념일) 을 돌려준다. 다가오는 쪽은 가까운 순."""
    today = today or timezone.localdate()
    upcoming = auto_milestones(couple.start_date, today)
    past = []
    for a in couple.anniversaries.all():
        d = next_occurrence(a.date, today) if a.repeat_yearly else a.date
        item = Item(a.title, d, (d - today).days, a)
        (upcoming if d >= today else past).append(item)
    upcoming.sort(key=lambda i: i.date)
    past.sort(key=lambda i: i.date, reverse=True)
    return upcoming, past
