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
    color = forms.ChoiceField(choices=COLOR_CHOICES, widget=forms.RadioSelect)

    def __init__(self, *args, partner=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.partner = partner
        self.avatar_bytes = None

    def clean_emoji(self):
        value = self.cleaned_data["emoji"].strip()
        if value and any(ch.isspace() or ch.isascii() or ch.isalpha() for ch in value):
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
