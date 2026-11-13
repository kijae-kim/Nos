from django import forms

from config.fields import TypedDateField

from .models import Anniversary


class AnniversaryForm(forms.ModelForm):
    date = TypedDateField(label="날짜")

    class Meta:
        model = Anniversary
        fields = ["title", "date", "repeat_yearly"]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "예: 생일, 첫 여행"}),
        }
