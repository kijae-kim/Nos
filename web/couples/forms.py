from django import forms
from django.utils import timezone

from .models import CODE_LENGTH


class StartDateField(forms.DateField):
    def __init__(self, **kwargs):
        kwargs.setdefault("label", "사귀기 시작한 날")
        kwargs.setdefault("required", False)
        kwargs.setdefault("widget", forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
        super().__init__(**kwargs)

    def validate(self, value):
        super().validate(value)
        if value and value > timezone.localdate():
            raise forms.ValidationError("오늘 이후의 날짜는 선택할 수 없어요.")


class CreateForm(forms.Form):
    start_date = StartDateField(help_text="나중에 설정해도 괜찮아요.")


class JoinForm(forms.Form):
    code = forms.CharField(
        label="초대 코드",
        max_length=CODE_LENGTH,
        min_length=CODE_LENGTH,
        widget=forms.TextInput(attrs={"autocomplete": "off", "autocapitalize": "characters", "placeholder": "ABC234"}),
    )

    def clean_code(self):
        return self.cleaned_data["code"].strip().upper()


class ProfileForm(forms.Form):
    nickname = forms.CharField(label="닉네임", max_length=20, required=False)
    start_date = StartDateField()
