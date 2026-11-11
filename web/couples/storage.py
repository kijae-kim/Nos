import os
import uuid

from django import forms
from django.core.exceptions import ValidationError

# 사진 한 장의 최대 크기. 이보다 큰 파일은 올릴 수 없다.
MAX_IMAGE_BYTES = 10 * 1024 * 1024


def _name_for(couple_id, filename):
    """원래 파일 이름 대신 무작위 이름을 쓴다. 커플별 폴더에 나눠 담는다."""
    ext = os.path.splitext(filename)[1].lower()
    return f"{couple_id}/{uuid.uuid4().hex}{ext}"


def photo_upload_to(instance, filename):
    return f"photos/{_name_for(instance.couple_id, filename)}"


def taste_upload_to(instance, filename):
    return f"tastes/{_name_for(instance.couple_id, filename)}"


class ImageUploadField(forms.ImageField):
    """이미지인지 확인하고, 크기 제한을 넘으면 막는다."""

    def clean(self, data, initial=None):
        cleaned = super().clean(data, initial)
        if cleaned and cleaned.size > MAX_IMAGE_BYTES:
            raise ValidationError("사진은 10MB 이하로 골라 주세요.")
        return cleaned


def delete_file(name):
    """저장소에 있는 파일을 지운다. 이름이 없으면 아무것도 하지 않는다."""
    if name:
        from django.core.files.storage import default_storage

        default_storage.delete(name)
