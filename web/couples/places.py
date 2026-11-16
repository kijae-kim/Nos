"""장소(분류 "장소" 인 추억 글)와 사진 잇기.

사진은 찍은 위치에서 200m 안의 가장 가까운 장소에 저절로 붙는다 (같은 거리면 먼저 만든 장소).
사용자가 직접 정한 연결(Photo.place_manual)은 건드리지 않는다.
"""

import math

from .models import Photo, Taste

LINK_RADIUS_M = 200
EARTH_RADIUS_M = 6371008.8


def distance_m(lat1, lng1, lat2, lng2):
    """두 점 사이 거리(m), 하버사인."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def located_places(couple):
    return list(
        Taste.objects.filter(couple=couple, category=Taste.PLACE, latitude__isnull=False, longitude__isnull=False).order_by("pk")
    )


def nearest_place(couple, lat, lng, places=None):
    """200m 안에서 가장 가까운 장소. 같은 거리면 먼저 만든 것(작은 pk)."""
    if lat is None or lng is None:
        return None
    best, best_d = None, None
    for place in located_places(couple) if places is None else places:
        d = distance_m(lat, lng, place.latitude, place.longitude)
        if d <= LINK_RADIUS_M and (best_d is None or d < best_d - 1e-6):
            best, best_d = place, d
    return best


def link_photo(photo):
    """사진 한 장을 자동으로 잇는다. 직접 정한 사진은 그대로."""
    if photo.place_manual:
        return
    place = nearest_place(photo.couple, photo.latitude, photo.longitude)
    if photo.place_id != (place.pk if place else None):
        photo.place = place
        photo.save(update_fields=["place"])


def relink(couple):
    """장소가 생기거나 바뀌거나 지워졌을 때 커플의 자동 사진을 모두 다시 잇는다. 바뀐 수를 돌려준다."""
    places = located_places(couple)
    changed = []
    for photo in Photo.objects.filter(couple=couple, place_manual=False).only("pk", "latitude", "longitude", "place_id"):
        place = nearest_place(couple, photo.latitude, photo.longitude, places)
        new_id = place.pk if place else None
        if photo.place_id != new_id:
            photo.place_id = new_id
            changed.append(photo)
    Photo.objects.bulk_update(changed, ["place"])
    return len(changed)
