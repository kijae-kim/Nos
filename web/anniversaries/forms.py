from django import forms

from .models import Anniversary


class AnniversaryForm(forms.ModelForm):
    class Meta:
        model = Anniversary
        fields = ["title", "date", "repeat_yearly"]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "예: 생일, 첫 여행"}),
            "date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }
