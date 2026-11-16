"""장소 검색 (추억 › 기록 › 장소 기록하기).

국내는 카카오 로컬 키워드 검색(REST API 키 = KAKAO_CLIENT_ID, 서버에서만 쓴다).
카카오 결과가 3개보다 적으면 OpenStreetMap(Nominatim) 결과를 뒤에 붙인다 (해외 장소).
Nominatim 사용 정책: 초당 1회, 앱 이름 User-Agent, 결과 캐시. 어느 쪽이든 실패하면 그쪽은 빈 결과.
"""

import hashlib
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache

from .geo import clean_coords

KAKAO_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "NOS-couple-app/1.0"
TIMEOUT = 5
MAX_RESULTS = 10
MAX_QUERY = 60


def _http_json(url, headers=None):
    request = Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urlopen(request, timeout=TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def _result(name, address, lat, lng, url, source):
    coords = clean_coords(lat, lng)
    if not coords or not name:
        return None
    return {"name": name, "address": address, "lat": coords[0], "lng": coords[1], "url": url, "source": source}


def _kakao(query):
    key = settings.KAKAO_CLIENT_ID
    if not key:
        return []
    try:
        data = _http_json(f"{KAKAO_URL}?{urlencode({'query': query, 'size': MAX_RESULTS})}", {"Authorization": f"KakaoAK {key}"})
    except Exception:
        return []
    results = []
    documents = data.get("documents") if isinstance(data, dict) else None  # 모르는 모양이면 결과 없음
    for d in documents if isinstance(documents, list) else []:
        if not isinstance(d, dict):
            continue
        r = _result(d.get("place_name", ""), d.get("road_address_name") or d.get("address_name", ""), d.get("y"), d.get("x"), d.get("place_url", ""), "kakao")
        if r:
            results.append(r)
    return results


def _nominatim(query):
    cache_key = "nominatim:" + hashlib.sha1(query.encode("utf-8")).hexdigest()
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    if not cache.add("nominatim-lock", 1, timeout=1):  # 서버 전체 초당 1회
        return []
    try:
        params = {"q": query, "format": "jsonv2", "accept-language": "ko", "limit": 5}
        data = _http_json(f"{NOMINATIM_URL}?{urlencode(params)}")
    except Exception:
        return []
    results = []
    for d in data if isinstance(data, list) else []:
        if not isinstance(d, dict):
            continue
        display = d.get("display_name", "")
        name = d.get("name") or display.split(",")[0].strip()
        r = _result(name, display, d.get("lat"), d.get("lon"), "", "osm")
        if r:
            results.append(r)
    cache.set(cache_key, results, 86400)
    return results


def search(query):
    query = " ".join((query or "").split())
    if not query or len(query) > MAX_QUERY:
        return []
    results = _kakao(query)
    if len(results) < 3:
        results += _nominatim(query)
    return results[:MAX_RESULTS]
