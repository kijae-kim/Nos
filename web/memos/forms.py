from django import forms

from .models import MemoFolder


class FolderForm(forms.ModelForm):
    class Meta:
        model = MemoFolder
        fields = ["name"]
        widgets = {"name": forms.TextInput(attrs={"placeholder": "예: 데이트 코스, 사고 싶은 것", "maxlength": 20})}

    def __init__(self, *args, couple=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.couple = couple

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        if MemoFolder.objects.filter(couple=self.couple, name=name).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("이미 있는 폴더 이름이에요.")
        return name
