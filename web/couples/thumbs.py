"""사진의 작은 사진(긴 변 320px JPEG). 지도 핀·사진 줄·앨범 격자에 쓴다.

원본 이름 옆에 `-thumb.jpg` 로 둔다. 촬영 정보(EXIF, 위치)는 넣지 않는다.
못 만들면(HEIC 등 서버가 못 여는 사진) 없는 채로 두고 화면은 원본을 쓴다.
"""
import io
import os

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from PIL import Image, ImageOps

EDGE = 320
MAX_PIXELS = 80_000_000  # 화소가 너무 많은 사진은 풀지 않는다 (서버 메모리)


def thumb_name(image_name):
    return os.path.splitext(image_name)[0] + "-thumb.jpg"


def make_thumb(fileobj):
    """사진 파일에서 작은 사진 JPEG 바이트를 만든다. 못 만들면 None."""
    try:
        fileobj.seek(0)
        img = Image.open(fileobj)
        if img.width * img.height > MAX_PIXELS:
            return None
        img.draft("RGB", (EDGE * 2, EDGE * 2))  # JPEG 는 작게 풀어 메모리를 아낀다
        img = ImageOps.exif_transpose(img)
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            base = Image.new("RGB", img.size, (255, 255, 255))
            base.paste(img, mask=img.getchannel("A"))
            img = base
        img = img.convert("RGB")
        img.thumbnail((EDGE, EDGE), Image.LANCZOS)
        out = io.BytesIO()
        img.save(out, "JPEG", quality=80)  # exif 를 넘기지 않으므로 촬영 정보가 빠진다
        return out.getvalue()
    except Exception:  # 못 여는 형식·깨진 파일
        return None
    finally:
        try:
            fileobj.seek(0)
        except Exception:
            pass


def delete_thumb(photo):
    if photo.thumb:
        default_storage.delete(photo.thumb.name)


def attach_thumb(photo, source=None):
    """작은 사진을 만들어 붙이고 저장한다. source 가 없으면 저장된 원본을 연다(R2 GET 한 번).
    옛 작은 사진은 지운다. 못 만들면 False (작은 사진 없이 둔다)."""
    old = photo.thumb.name if photo.thumb else ""
    try:
        if source is not None:
            data = make_thumb(source)
        else:
            with photo.image.open("rb") as f:
                data = make_thumb(f)
    except Exception:  # 저장소에 원본이 없거나 열 수 없음
        data = None
    if old and old != thumb_name(photo.image.name):
        default_storage.delete(old)
    if not data:
        if old:
            default_storage.delete(old)
        photo.thumb, photo.thumb_size = "", 0
        photo.save(update_fields=["thumb", "thumb_size"])
        return False
    try:
        saved = default_storage.save(thumb_name(photo.image.name), ContentFile(data))
    except Exception:  # 저장소 오류(R2 연결 등): 작은 사진 없이 둔다. 사진 올리기는 성공해야 한다
        photo.thumb, photo.thumb_size = "", 0
        photo.save(update_fields=["thumb", "thumb_size"])
        return False
    photo.thumb.name, photo.thumb_size = saved, len(data)
    photo.save(update_fields=["thumb", "thumb_size"])
    return True
