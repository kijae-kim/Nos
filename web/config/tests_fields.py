from datetime import date, timedelta

from django import forms
from django.test import SimpleTestCase
from django.utils import timezone

from anniversaries.forms import AnniversaryForm
from config.fields import TypedDateField
from couples.forms import StartDateField


class TypedDateFieldTests(SimpleTestCase):
    """폰에서 숫자로 치는 날짜 칸. 달력 선택기 대신 2026.11.13 처럼 입력한다."""

    def clean(self, value):
        return TypedDateField().clean(value)

    def test_accepts_formats(self):
        for value in ["2026.11.13", "2026-11-13", "2026/11/13", "20261113", "2026. 11. 13.", "2026.1.5"]:
            expected = date(2026, 1, 5) if value == "2026.1.5" else date(2026, 11, 13)
            self.assertEqual(self.clean(value), expected, value)

    def test_rejects_impossible_date(self):
        with self.assertRaisesMessage(forms.ValidationError, "날짜를 다시 확인해 주세요"):
            self.clean("2026.02.30")

    def test_renders_numeric_text_input_with_dots(self):
        field = TypedDateField()
        rendered = field.widget.render("date", date(2026, 11, 13))
        self.assertIn('type="text"', rendered)
        self.assertIn('inputmode="numeric"', rendered)
        self.assertIn('value="2026.11.13"', rendered)
        self.assertIn('placeholder="예: 2026.11.13"', rendered)
        self.assertIn("data-date-type", rendered)

    def test_anniversary_form_uses_typed_date(self):
        form = AnniversaryForm(data={"title": "첫 여행", "date": "20240305"})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["date"], date(2024, 3, 5))
        self.assertIn('inputmode="numeric"', str(form["date"]))

    def test_start_date_still_rejects_future(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        with self.assertRaisesMessage(forms.ValidationError, "오늘 이후의 날짜는 선택할 수 없어요."):
            StartDateField().clean(tomorrow.strftime("%Y.%m.%d"))
        self.assertEqual(StartDateField().clean("2024.03.01"), date(2024, 3, 1))
        self.assertIsNone(StartDateField().clean(""))
