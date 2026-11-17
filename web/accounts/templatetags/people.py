"""사람 모습(아바타) 그리기. 사진 > 이모지(내 색 바탕) > 내 색. 보는 사람과 상관없이 같은 모습."""
from django import template
from django.utils.html import format_html

register = template.Library()


@register.simple_tag
def avatar(person, size=""):
    extra = f" {size}" if size else ""
    if person is None:
        return format_html('<i class="av vacant{}" aria-hidden="true">?</i>', extra)
    if person.has_avatar:
        return format_html('<img class="av{}" src="{}" alt="">', extra, person.avatar_url)
    if person.emoji:
        return format_html('<i class="av emoji{}" style="--c: var(--{})" aria-hidden="true">{}</i>', extra, person.color, person.emoji)
    return format_html('<i class="av{}" style="--c: var(--{})" aria-hidden="true"></i>', extra, person.color)
