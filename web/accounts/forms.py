import unicodedata

from django import forms

from .avatars import clean_avatar
from .models import COLOR_CHOICES

# 프로필 화면의 이모지 격자 (커플·데이트·동물·음식 위주)
EMOJIS = [
    "🐻", "🐰", "🐱", "🐶", "🦊", "🐼", "🐨", "🐯", "🐸", "🐧",
    "🐳", "🦄", "🐥", "🦦", "🐹", "🌷", "🌻", "🌙", "⭐", "☀️",
    "🌈", "🍀", "🍓", "🍑", "🍒", "🍰", "🍩", "☕", "🍜", "🍕",
    "💛", "💙", "💗", "💜", "🎈", "🎧", "📷", "✈️", "⛵", "🏝️",
]


class ProfileForm(forms.Form):
    """사진(선택)·사진 빼기·이모지·내 색. 상대가 쓰는 색은 고를 수 없다."""

    photo = forms.FileField(required=False, widget=forms.FileInput(attrs={"accept": "image/*", "data-avatar-input": ""}))
    remove_photo = forms.BooleanField(required=False)
    emoji = forms.CharField(required=False, max_length=16, error_messages={"max_length": "이모지 하나만 넣어 주세요."}, widget=forms.TextInput(attrs={"placeholder": "직접 넣기", "maxlength": 16, "data-emoji-input": ""}))
    color = forms.ChoiceField(choices=COLOR_CHOICES, widget=forms.RadioSelect, error_messages={"required": "색을 골라 주세요.", "invalid_choice": "색을 골라 주세요."})

    def __init__(self, *args, partner=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.partner = partner
        self.avatar_bytes = None

    def clean_emoji(self):
        value = self.cleaned_data["emoji"].strip()
        if value and not is_one_emoji(value):
            raise forms.ValidationError("이모지 하나만 넣어 주세요.")
        return value

    def clean_color(self):
        color = self.cleaned_data["color"]
        if self.partner and self.partner.color == color:
            raise forms.ValidationError("상대가 쓰고 있는 색이에요. 다른 색을 골라 주세요.")
        return color

    def clean_photo(self):
        f = self.cleaned_data.get("photo")
        if not f:
            return None
        if f.size > 2 * 1024 * 1024:
            raise forms.ValidationError("사진이 너무 커요. 다른 사진을 골라 주세요.")
        try:
            self.avatar_bytes = clean_avatar(f.read())
        except ValueError as e:
            if str(e) == "too_big":
                raise forms.ValidationError("사진이 너무 커요. 다른 사진을 골라 주세요.")
            raise forms.ValidationError("이 사진은 열 수 없어요. 다른 사진을 골라 주세요.")
        return f


# 이모지 한 글자를 이루는 덧붙는 문자: 이음(ZWJ), 모양 고르기, 피부색, 키캡, 태그(깃발)
_JOINER = "\u200d"
_MODIFIERS = {"\ufe0e", "\ufe0f", "\u20e3"} | {chr(c) for c in range(0x1F3FB, 0x1F400)} | {chr(c) for c in range(0xE0020, 0xE0080)}


def is_one_emoji(text):
    """이모지(기호) 하나인지. 👩‍❤️‍👨 처럼 이어 붙인 것, 깃발(🇰🇷), 키캡(1️⃣)도 하나로 센다."""
    bases, joins, regional = [], 0, 0
    chars = list(text)
    for i, ch in enumerate(chars):
        if ch == _JOINER:
            joins += 1
        elif ch in _MODIFIERS:
            continue
        elif 0x1F1E6 <= ord(ch) <= 0x1F1FF:
            regional += 1
        elif ch in "0123456789#*" and "\u20e3" in chars[i + 1:i + 3]:
            bases.append(ch)  # 키캡의 바탕 글자
        elif unicodedata.category(ch) == "So":
            bases.append(ch)
        else:
            return False  # 글자·숫자·띄어쓰기 등
    if regional:
        return regional == 2 and not bases
    return len(bases) - joins == 1

