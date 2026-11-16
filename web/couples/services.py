import re

from .models import COLOR_CHOICES, Label

# @카테고리 와 #태그 는 공백 전까지 한 덩어리로 본다.
LABEL_TOKEN = re.compile(r"([@#])([^\s@#]+)")
KIND_BY_PREFIX = {"@": Label.CATEGORY, "#": Label.TAG}
PALETTE = [color for color, _ in COLOR_CHOICES]


def split_text(text):
    """'전시 보러 가기 @데이트 #성수' → ('전시 보러 가기', [(카테고리, '데이트'), (태그, '성수')])"""
    labels = [(KIND_BY_PREFIX[prefix], name) for prefix, name in LABEL_TOKEN.findall(text)]
    title = " ".join(LABEL_TOKEN.sub(" ", text).split())
    return title, labels


def label_text(event):
    """수정 화면에 다시 채워 넣을 글자. 저장할 때 같은 방식으로 다시 나뉜다."""
    tokens = [l.token for l in event.labels.all()]
    return " ".join([event.title, *tokens])


def get_or_create_label(couple, kind, name):
    label = couple.labels.filter(kind=kind, name=name).first()
    if label:
        return label
    color = PALETTE[couple.labels.count() % len(PALETTE)]
    return Label.objects.create(couple=couple, kind=kind, name=name, color=color)


def save_event(event, couple, data):
    """폼에서 받은 값을 일정에 옮겨 저장한다.

    data["text"] 는 제목과 이름표로 나뉜다. 없던 @·# 이름표는 이때 만들어진다.
    """
    title, tokens = split_text(data["text"])
    event.couple = couple
    event.title = title
    event.date = data["date"]
    event.start_time = data.get("start_time")
    event.end_time = data.get("end_time")
    event.place = data.get("place", "")
    event.memo = data.get("memo", "")
    event.scope = data["scope"]
    event.color = data["color"]
    event.save()
    labels = {get_or_create_label(couple, kind, name) for kind, name in tokens}
    event.labels.set(labels)
    return event
