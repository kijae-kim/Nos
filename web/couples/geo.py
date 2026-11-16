"""사진 촬영 위치. 브라우저가 보낸 값을 먼저 쓰고, 없으면 사진 정보(EXIF)에서 읽는다.

위치는 커플 두 사람만 보는 정보다. 읽지 못해도 사진 올리기는 막지 않는다.
"""

from PIL import Image

GPS_IFD = 0x8825
LAT_REF, LAT, LNG_REF, LNG = 1, 2, 3, 4


def clean_coords(lat, lng):
    """(위도, 경도) 를 숫자로 바꿔 검사한다. 하나라도 없거나 범위 밖이거나 (0, 0) 이면 None."""
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    if lat == 0 and lng == 0:  # 위치를 못 잡은 사진에 흔히 들어가는 값
        return None
    return lat, lng


def _degrees(dms, ref):
    d, m, s = (float(x) for x in dms)
    value = d + m / 60 + s / 3600
    return -value if ref in ("S", "W") else value


def gps_from_image(fileobj):
    """사진 파일의 EXIF GPS 에서 (위도, 경도). JPEG 등 Pillow 가 여는 형식만, 실패하면 None."""
    start = fileobj.tell() if hasattr(fileobj, "tell") else 0
    try:
        with Image.open(fileobj) as image:
            gps = image.getexif().get_ifd(GPS_IFD)
        if not gps or LAT not in gps or LNG not in gps:
            return None
        return clean_coords(_degrees(gps[LAT], gps.get(LAT_REF, "N")), _degrees(gps[LNG], gps.get(LNG_REF, "E")))
    except Exception:  # 깨진 파일, 모르는 형식(HEIC 등), 이상한 EXIF
        return None
    finally:
        if hasattr(fileobj, "seek"):
            fileobj.seek(start)
