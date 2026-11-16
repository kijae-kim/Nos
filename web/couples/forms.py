from django import forms
from django.utils import timezone

from config.fields import TypedDateField

from . import quota
from .models import CODE_LENGTH, COLOR_CHOICES, Album, Photo, Taste, TasteComment
from .storage import ImageUploadField, delete_file


class StartDateField(TypedDateField):
    def __init__(self, **kwargs):
        kwargs.setdefault("label", "사귀기 시작한 날")
        kwargs.setdefault("required", False)
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


class EventForm(forms.Form):
    text = forms.CharField(
        label="일정",
        max_length=140,
        help_text="@카테고리 #태그 를 함께 적으면 그 이름표에 바로 묶여요. 예: 전시 보러 가기 @데이트 #성수",
        widget=forms.TextInput(attrs={"placeholder": "무슨 일정인가요?", "autocomplete": "off"}),
    )
    date = forms.DateField(label="날짜", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    all_day = forms.BooleanField(label="하루 종일", required=False)
    start_time = forms.TimeField(label="시작", required=False, widget=forms.TimeInput(attrs={"type": "time", "step": 900}, format="%H:%M"))
    end_time = forms.TimeField(label="끝", required=False, widget=forms.TimeInput(attrs={"type": "time", "step": 900}, format="%H:%M"))
    place = forms.CharField(label="장소", max_length=100, required=False)
    memo = forms.CharField(
        label="메모",
        max_length=1000,
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "준비물, 예약 번호처럼 적어 두고 싶은 것"}),
    )
    scope = forms.ChoiceField(label="공개", choices=[("shared", "공통 일정"), ("personal", "개인 일정")], widget=forms.RadioSelect, initial="shared")
    color = forms.ChoiceField(label="색", choices=COLOR_CHOICES, widget=forms.RadioSelect, initial="sky")

    def clean(self):
        from .services import split_text

        cleaned = super().clean()
        text = cleaned.get("text")
        if text:
            title, _ = split_text(text)
            if not title:
                self.add_error("text", "이름표만 적으면 일정 이름이 없어요. 일정 이름을 먼저 적어 주세요.")
        if cleaned.get("all_day"):
            cleaned["start_time"] = cleaned["end_time"] = None
        start, end = cleaned.get("start_time"), cleaned.get("end_time")
        if start and end and end <= start:
            self.add_error("end_time", "끝나는 시간이 시작 시간보다 늦어야 해요.")
        return cleaned


class TasteForm(forms.ModelForm):
    image = ImageUploadField(
        label="사진",
        required=False,
        widget=forms.FileInput(attrs={"accept": "image/*"}),
        help_text="없어도 괜찮아요. 캡처 화면이나 앨범 커버를 올려 보세요. 큰 사진은 올릴 때 알아서 줄여요.",
    )
    clear_image = forms.BooleanField(label="사진 빼기", required=False)

    class Meta:
        model = Taste
        fields = ["category", "title", "link", "comment", "image"]
        widgets = {
            "category": forms.RadioSelect,
            "title": forms.TextInput(attrs={"placeholder": "곡 제목, 영화 제목, 장소 이름"}),
            "link": forms.URLInput(attrs={"placeholder": "유튜브·스포티파이·지도 링크를 붙여 넣어 보세요", "inputmode": "url", "data-link-preview": "/tastes/preview/"}),
            "comment": forms.Textarea(attrs={"rows": 3, "placeholder": "왜 좋았는지 한마디 남겨 보세요"}),
        }

    def __init__(self, *args, couple=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.couple = couple
        # 분류는 다섯 중 하나. 빈 선택지("---------")는 빼고, 이름도 한국어로
        category = self.fields["category"]
        category.label = "분류"
        category.choices = [(c, c) for c in Taste.CATEGORIES]
        category.error_messages["required"] = "분류를 골라 주세요."
        # 검사하면서 새 사진이 인스턴스에 들어가므로, 바꾸기 전 이름과 크기를 미리 적어 둔다
        self.old_image_name = self.instance.image.name if self.instance.pk else None
        self.old_image_size = self.instance.image_size if self.instance.pk else 0

    def clean(self):
        cleaned = super().clean()
        new_file = cleaned.get("image")
        if self.couple is not None and "image" in self.changed_data and new_file:
            reason = quota.problem(self.couple, new_file.size, self.old_image_size)
            if reason:
                self.add_error("image", reason)
        return cleaned

    def save_for(self, couple, user):
        old_name = self.old_image_name
        taste = self.save(commit=False)
        taste.couple = couple
        if taste.pk is None:
            taste.author = user
        if self.cleaned_data.get("clear_image") and taste.image:
            taste.image = None
        if "image" in self.changed_data and self.cleaned_data.get("image"):
            taste.image_size = self.cleaned_data["image"].size
        elif not taste.image:
            taste.image_size = 0
        # 링크가 바뀌었거나 아직 미리보기가 없으면 가져온다 (실패해도 저장은 된다)
        if "link" in self.changed_data or (taste.link and not (taste.preview_title or taste.preview_image)):
            taste.refresh_preview()
        taste.save()
        if old_name and old_name != taste.image.name:
            delete_file(old_name)
        return taste


class AlbumForm(forms.ModelForm):
    class Meta:
        model = Album
        fields = ["title"]
        widgets = {"title": forms.TextInput(attrs={"placeholder": "예: 성수동 산책"})}


class TasteCommentForm(forms.Form):
    text = forms.CharField(
        label="댓글",
        max_length=TasteComment.MAX_LENGTH,
        widget=forms.Textarea(attrs={"rows": 1, "placeholder": "한마디 남기기", "maxlength": TasteComment.MAX_LENGTH}),
        error_messages={"required": "댓글을 적어 주세요.", "max_length": f"{TasteComment.MAX_LENGTH}자까지 적을 수 있어요."},
    )

    def clean_text(self):
        text = self.cleaned_data["text"].strip()
        if not text:
            raise forms.ValidationError("댓글을 적어 주세요.")
        return text


class PhotoForm(forms.ModelForm):
    image = ImageUploadField(label="사진", widget=forms.FileInput(attrs={"accept": "image/*"}))
    album = forms.ModelChoiceField(label="앨범", queryset=Album.objects.none(), required=False, empty_label="앨범 없이", widget=forms.RadioSelect)
    new_album = forms.CharField(label="새 앨범 이름", max_length=50, required=False, widget=forms.TextInput(attrs={"placeholder": "새 앨범을 만들려면 적어 주세요"}))
    taken_on = forms.DateField(label="찍은 날", required=False, widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))

    class Meta:
        model = Photo
        fields = ["image", "album", "taken_on", "caption"]
        widgets = {
            "image": forms.FileInput(attrs={"accept": "image/*"}),
            "caption": forms.Textarea(attrs={"rows": 3, "placeholder": "이날을 한 줄로 남겨 보세요"}),
        }
        labels = {"image": "사진", "caption": "한마디"}

    def __init__(self, *args, couple=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.couple = couple
        self.fields["album"].queryset = Album.objects.filter(couple=couple) if couple else Album.objects.none()
        # 검사하면서 새 사진이 인스턴스에 들어가므로, 바꾸기 전 이름을 미리 적어 둔다
        self.old_image_name = self.instance.image.name if self.instance.pk else None
        if self.instance.pk is None:
            self.fields["image"].required = True
        else:
            self.fields["image"].required = False

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("album") and cleaned.get("new_album"):
            self.add_error("new_album", "앨범은 하나만 고를 수 있어요. 새 앨범을 만들거나 기존 앨범을 고르세요.")
        new_file = cleaned.get("image")
        if self.couple is not None and "image" in self.changed_data and new_file:
            reason = quota.problem(self.couple, new_file.size, self.instance.size if self.instance.pk else 0)
            if reason:
                self.add_error("image", reason)
        return cleaned

    def save_for(self, couple, user):
        old_name = self.old_image_name
        photo = self.save(commit=False)
        photo.couple = couple
        if photo.pk is None:
            photo.uploaded_by = user
        name = self.cleaned_data.get("new_album", "").strip()
        if name:
            photo.album, _ = Album.objects.get_or_create(couple=couple, title=name)
        if "image" in self.changed_data and self.cleaned_data.get("image"):
            photo.size = self.cleaned_data["image"].size
        photo.save()
        if old_name and old_name != photo.image.name:
            delete_file(old_name)
        return photo
