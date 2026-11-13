import re

from django import forms

DISPLAY_FORMAT = "%Y.%m.%d"
INPUT_FORMATS = ["%Y.%m.%d", "%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"]


class TypedDateInput(forms.DateInput):
    """숫자 키패드가 뜨는 글자 칸. app.js 가 치는 동안 2026.11.13 처럼 점을 넣는다."""

    input_type = "text"

    def __init__(self, attrs=None):
        base = {
            "inputmode": "numeric",
            "placeholder": "예: 2026.11.13",
            "autocomplete": "off",
            "maxlength": "12",
            "data-date-type": "",
        }
        super().__init__(attrs={**base, **(attrs or {})}, format=DISPLAY_FORMAT)


class TypedDateField(forms.DateField):
    """폰의 날짜 선택기 대신 숫자로 치는 날짜 칸 (기념일, 사귀기 시작한 날처럼 오래전 날짜에)."""

    widget = TypedDateInput
    input_formats = INPUT_FORMATS
    default_error_messages = {"invalid": "날짜를 다시 확인해 주세요. 예: 2026.11.13"}

    def to_python(self, value):
        if isinstance(value, str):
            # "2026. 11. 13." 처럼 띄어 쓰거나 끝에 점을 찍어도 받는다
            value = re.sub(r"\s+", "", value).rstrip(".")
        return super().to_python(value)
