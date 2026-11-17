"""프로필 사진·색 도우미."""
import io

from PIL import Image, ImageOps, UnidentifiedImageError

from .models import COLOR_CHOICES

COLORS = [c for c, _ in COLOR_CHOICES]
MAX_BYTES = 2 * 1024 * 1024
SIZE = 256


def clean_avatar(data):
    """올린 사진을 가운데 정사각형 256px JPEG 로 다시 만든다. 촬영 정보(EXIF, 위치)는 남지 않는다.

    너무 크면 ValueError("too_big"), 사진이 아니면 ValueError("bad").
    """
    if len(data) > MAX_BYTES:
        raise ValueError("too_big")
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)  # 돌려 찍은 사진 바로 세우기
        img = ImageOps.fit(img.convert("RGB"), (SIZE, SIZE), Image.LANCZOS)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise ValueError("bad")
    out = io.BytesIO()
    img.save(out, "JPEG", quality=85)  # exif 를 넘기지 않으므로 촬영 정보가 빠진다
    return out.getvalue()


def free_color(taken):
    """taken 이 아닌 첫 색."""
    return next(c for c in COLORS if c != taken)


def assign_default_colors(couple):
    """처음 색: 먼저 가입한 사람 장미, 다음 사람 하늘."""
    for person, color in zip(couple.members.order_by("date_joined", "pk"), ["rose", "sky"]):
        if person.color != color:
            person.color = color
            person.save(update_fields=["color"])


def fix_color_on_join(user):
    """커플에 들어올 때 상대와 색이 같으면 다른 색으로."""
    partner = user.partner
    if partner and partner.color == user.color:
        user.color = free_color(partner.color)
        user.save(update_fields=["color"])
