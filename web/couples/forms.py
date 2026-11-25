from django import forms
from django.utils import timezone

from config.fields import TypedDateField

from . import quota
from .geo import clean_coords, gps_from_image
from .places import link_photo
from .models import CODE_LENGTH, COLOR_CHOICES, Album, Label, Photo, Taste, TasteComment, WishList, WishPlace
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
    end_date = forms.DateField(
        label="끝나는 날 (여러 날이면)",
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "data-end-date": ""}, format="%Y-%m-%d"),
        help_text="여행처럼 며칠 이어지면 넣어 주세요. 여러 날 일정은 하루 종일로 저장돼요.",
    )
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
    scope = forms.ChoiceField(label="구분", choices=[("shared", "공통 일정"), ("personal", "개인 일정")], widget=forms.RadioSelect, initial="shared")
    color = forms.ChoiceField(label="색", choices=COLOR_CHOICES, widget=forms.RadioSelect, initial="sky")

    def clean(self):
        from .services import split_text

        cleaned = super().clean()
        text = cleaned.get("text")
        if text:
            title, _ = split_text(text)
            if not title:
                self.add_error("text", "이름표만 적으면 일정 이름이 없어요. 일정 이름을 먼저 적어 주세요.")
        start_day, end_day = cleaned.get("date"), cleaned.get("end_date")
        if start_day and end_day:
            if end_day == start_day:
                cleaned["end_date"] = None  # 같은 날이면 하루 일정
            elif end_day < start_day:
                self.add_error("end_date", "끝나는 날은 시작하는 날보다 뒤여야 해요.")
            elif (end_day - start_day).days > 59:
                self.add_error("end_date", "여러 날 일정은 60일까지 넣을 수 있어요.")
            else:
                cleaned["all_day"] = True  # 여러 날 일정은 하루 종일만
        if cleaned.get("all_day"):
            cleaned["start_time"] = cleaned["end_time"] = None
        start, end = cleaned.get("start_time"), cleaned.get("end_time")
        if start and end and end <= start:
            self.add_error("end_time", "끝나는 시간이 시작 시간보다 늦어야 해요.")
        return cleaned


class QuickEventForm(EventForm):
    """캘린더 날짜 팝업의 빠른 추가: 장소·메모·색은 빼고(자세히 쓰기에서), 날짜는 누른 날."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("place", "memo", "color"):
            del self.fields[name]
        self.fields["date"].widget = forms.HiddenInput()
        self.fields["text"].help_text = ""
        self.fields["end_date"].help_text = ""  # 좁은 팝업에서는 길다


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
            "title": forms.TextInput(attrs={"placeholder": "영화 제목, 곡 제목, 책 이름"}),
            "link": forms.URLInput(attrs={"placeholder": "유튜브·스포티파이·지도 링크를 붙여 넣어 보세요", "inputmode": "url", "data-link-preview": "/tastes/preview/"}),
            "comment": forms.Textarea(attrs={"rows": 3, "placeholder": "왜 좋았는지 한마디 남겨 보세요"}),
        }

    def __init__(self, *args, couple=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.couple = couple
        # 순간의 태그는 넷 중 하나 (장소는 기록에서 따로 쓴다). 빈 선택지("---------")는 빼고, 이름도 한국어로
        if "category" in self.fields:
            category = self.fields["category"]
            category.label = "태그"
            category.choices = [(c, c) for c in Taste.MOMENT_TAGS]
            category.error_messages["required"] = "태그를 하나 골라 주세요."
            category.error_messages["invalid_choice"] = "태그를 하나 골라 주세요."
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


# 순간(영화·음악·영상·책) 쓰기. 예전 이름도 남겨 둔다
MomentForm = TasteForm


class PlaceForm(TasteForm):
    """기록 › 장소 기록하기. 위치는 화면의 장소 고르기(place-picker.js)가 숨은 칸에 넣는다."""

    latitude = forms.CharField(required=False, widget=forms.HiddenInput)
    longitude = forms.CharField(required=False, widget=forms.HiddenInput)
    # 숨은 칸이라 길이 오류를 보여 줄 수 없으니 막지 않고 저장할 때 자른다
    address = forms.CharField(required=False, widget=forms.HiddenInput)
    place_url = forms.URLField(required=False, widget=forms.HiddenInput)
    from_photo = forms.IntegerField(required=False, widget=forms.HiddenInput)

    class Meta(TasteForm.Meta):
        fields = ["title", "link", "comment", "image"]
        widgets = {
            **TasteForm.Meta.widgets,
            "title": forms.TextInput(attrs={"placeholder": "장소 이름"}),
            "comment": forms.Textarea(attrs={"rows": 3, "placeholder": "어땠는지 한마디 남겨 보세요"}),
        }
        labels = {"title": "이름"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial.setdefault("latitude", "" if self.instance.latitude is None else self.instance.latitude)
            self.initial.setdefault("longitude", "" if self.instance.longitude is None else self.instance.longitude)
            self.initial.setdefault("address", self.instance.address)
            self.initial.setdefault("place_url", self.instance.place_url)

    def save_for(self, couple, user):
        from .places import relink

        self.instance.category = Taste.PLACE
        coords = clean_coords(self.cleaned_data.get("latitude"), self.cleaned_data.get("longitude"))
        self.instance.latitude, self.instance.longitude = coords or (None, None)
        self.instance.address = (self.cleaned_data.get("address", "") or "")[:200] if coords else ""
        self.instance.place_url = self.cleaned_data.get("place_url", "")
        place = super().save_for(couple, user)
        # "사진에서" 위치를 가져왔으면 그 사진은 이 장소에 직접 잇는다 (내 커플 사진만)
        photo_id = self.cleaned_data.get("from_photo")
        if photo_id:
            Photo.objects.filter(pk=photo_id, couple=couple).update(place=place, place_manual=True)
        relink(couple)
        return place


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
    # 브라우저가 줄이기 전에 읽은 촬영 위치 (app.js). 없으면 서버가 사진에서 읽는다.
    latitude = forms.CharField(required=False, widget=forms.HiddenInput)
    longitude = forms.CharField(required=False, widget=forms.HiddenInput)
    # 사진 고치기에서만: 이 사진을 찍은 장소 (자동으로 / 없음 / 장소 하나)
    place_choice = forms.ChoiceField(label="장소", required=False, widget=forms.RadioSelect)

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
            del self.fields["place_choice"]
        else:
            self.fields["image"].required = False
            places = Taste.objects.filter(couple=couple, category=Taste.PLACE).order_by("title") if couple else Taste.objects.none()
            self.fields["place_choice"].choices = [("auto", "자동으로 (찍은 곳 근처)"), ("none", "없음")] + [(str(p.pk), p.title) for p in places]
            if not self.instance.place_manual:
                self.initial["place_choice"] = "auto"
            else:
                self.initial["place_choice"] = str(self.instance.place_id) if self.instance.place_id else "none"

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("album") and cleaned.get("new_album"):
            self.add_error("new_album", "앨범은 하나만 고를 수 있어요. 새 앨범을 만들거나 기존 앨범을 고르세요.")
        new_file = cleaned.get("image")
        if self.couple is not None and "image" in self.changed_data and new_file:
            reason = quota.problem(self.couple, new_file.size, self.instance.size if self.instance.pk else 0, with_thumb=True)
            if reason:
                self.add_error("image", reason)
        return cleaned

    def save_for(self, couple, user):
        old_name = self.old_image_name
        old_thumb = self.instance.thumb.name if self.instance.pk and self.instance.thumb else ""
        photo = self.save(commit=False)
        photo.couple = couple
        if photo.pk is None:
            photo.uploaded_by = user
        name = self.cleaned_data.get("new_album", "").strip()
        if name:
            photo.album, _ = Album.objects.get_or_create(couple=couple, title=name)
        if "image" in self.changed_data and self.cleaned_data.get("image"):
            new_file = self.cleaned_data["image"]
            photo.size = new_file.size
            # 새 사진이 들어올 때만 위치를 정한다. 사진 정보만 고치면 위치는 그대로.
            coords = clean_coords(self.cleaned_data.get("latitude"), self.cleaned_data.get("longitude")) or gps_from_image(new_file)
            photo.latitude, photo.longitude = coords or (None, None)
            relink_needed = True
        else:
            relink_needed = False
        choice = self.cleaned_data.get("place_choice") if "place_choice" in self.fields else None
        if choice == "none":
            photo.place, photo.place_manual = None, True
        elif choice and choice != "auto":
            photo.place, photo.place_manual = Taste.objects.get(pk=int(choice), couple=couple, category=Taste.PLACE), True
        elif choice == "auto":
            photo.place_manual = False
            relink_needed = True
        photo.save()
        if "image" in self.changed_data and self.cleaned_data.get("image"):
            from .thumbs import attach_thumb

            if old_thumb:
                delete_file(old_thumb)
                photo.thumb = ""
            attach_thumb(photo, source=self.cleaned_data["image"])  # 받은 파일로 만든다 (R2 에서 다시 읽지 않음)
        if relink_needed:
            link_photo(photo)
        if old_name and old_name != photo.image.name:
            delete_file(old_name)
        return photo


class WishListForm(forms.ModelForm):
    """가고 싶은 곳 목록 만들기·고치기."""

    class Meta:
        model = WishList
        fields = ["name", "color"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "예: 맛집, 카페, 성수 데이트"}),
            "color": forms.RadioSelect,
        }

    def __init__(self, *args, couple=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.couple = couple
        self.fields["color"].choices = COLOR_CHOICES

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        taken = WishList.objects.filter(couple=self.couple, name=name).exclude(pk=self.instance.pk)
        if taken.exists():
            raise forms.ValidationError("이미 있는 목록 이름이에요.")
        return name


class WishPlaceForm(forms.ModelForm):
    """가고 싶은 곳 저장·고치기. 위치는 장소 고르기(place-picker.js)가 숨은 칸에 넣는다."""

    latitude = forms.CharField(required=False, widget=forms.HiddenInput)
    longitude = forms.CharField(required=False, widget=forms.HiddenInput)
    address = forms.CharField(required=False, widget=forms.HiddenInput)
    place_url = forms.URLField(required=False, widget=forms.HiddenInput)
    lists = forms.ModelMultipleChoiceField(label="목록", queryset=WishList.objects.none(), required=False, widget=forms.CheckboxSelectMultiple)
    new_list = forms.CharField(label="새 목록", max_length=20, required=False, widget=forms.TextInput(attrs={"placeholder": "새 목록 이름 (선택)"}))

    class Meta:
        model = WishPlace
        fields = ["name", "link", "memo"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "장소 이름"}),
            "link": forms.URLInput(attrs={"placeholder": "네이버 지도·인스타그램 링크 (선택)", "inputmode": "url"}),
            "memo": forms.TextInput(attrs={"placeholder": "한 줄 메모 (선택)"}),
        }
        labels = {"name": "이름", "memo": "메모"}

    def __init__(self, *args, couple=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.couple = couple
        self.fields["lists"].queryset = WishList.objects.filter(couple=couple) if couple else WishList.objects.none()
        if self.instance.pk:
            for f in ("latitude", "longitude", "address", "place_url"):
                self.initial.setdefault(f, getattr(self.instance, f))
            self.initial.setdefault("lists", list(self.instance.lists.all()))

    def clean(self):
        cleaned = super().clean()
        coords = clean_coords(cleaned.get("latitude"), cleaned.get("longitude"))
        if not coords:
            raise forms.ValidationError("위치를 골라 주세요.")
        cleaned["coords"] = coords
        return cleaned

    def save_for(self, couple, user):
        wish = self.save(commit=False)
        wish.couple = couple
        if wish.pk is None:
            wish.created_by = user
        wish.latitude, wish.longitude = self.cleaned_data["coords"]
        wish.address = (self.cleaned_data.get("address") or "")[:200]
        wish.place_url = self.cleaned_data.get("place_url") or ""
        wish.save()
        lists = list(self.cleaned_data.get("lists") or [])
        new_name = " ".join((self.cleaned_data.get("new_list") or "").split())
        if new_name:
            # 이미 같은 이름이 있으면 그 목록에 넣는다
            lst, _ = WishList.objects.get_or_create(couple=couple, name=new_name, defaults={"created_by": user})
            lists.append(lst)
        wish.lists.set(lists)
        return wish


class LabelForm(forms.ModelForm):
    """이름표(@카테고리 #태그) 만들기·고치기. 고칠 때는 종류를 바꾸지 않는다.

    고칠 때 같은 종류에 같은 이름이 이미 있으면 오류가 아니라 합치기(뷰에서)로 처리하므로 `merge_into` 에 담는다.
    """

    class Meta:
        model = Label
        fields = ["kind", "name", "color"]
        widgets = {
            "kind": forms.RadioSelect,
            "name": forms.TextInput(attrs={"placeholder": "예: 데이트, 성수, 기념일", "maxlength": 20}),
            "color": forms.RadioSelect,
        }
        labels = {"kind": "종류", "name": "이름", "color": "색"}

    def __init__(self, *args, couple=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.couple = couple
        self.merge_into = None
        self.fields["kind"].choices = [(Label.CATEGORY, "@ 카테고리"), (Label.TAG, "# 태그")]
        self.fields["kind"].initial = Label.TAG
        self.fields["color"].choices = COLOR_CHOICES
        if self.instance.pk:
            del self.fields["kind"]

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name or any(ch.isspace() for ch in name) or "@" in name or "#" in name:
            raise forms.ValidationError("이름표에는 띄어쓰기와 @·# 를 넣을 수 없어요.")
        return name

    def clean(self):
        cleaned = super().clean()
        name = cleaned.get("name")
        kind = self.instance.kind if self.instance.pk else cleaned.get("kind")
        if name and kind:
            same = Label.objects.filter(couple=self.couple, kind=kind, name=name).exclude(pk=self.instance.pk).first()
            if same and not self.instance.pk:
                self.add_error("name", "이미 있는 이름표예요.")
            self.merge_into = same if self.instance.pk else None
        return cleaned

    def _post_clean(self):
        # 합칠 때는 모델 유일 제약 검사를 건너뛴다 (뷰가 합친다)
        if self.merge_into is None:
            super()._post_clean()

