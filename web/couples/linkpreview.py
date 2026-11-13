"""취향 링크 미리보기: 제목, 썸네일, 사이트 이름을 가져온다.

- 유튜브·스포티파이는 공식 oEmbed 주소에 묻는다 (정확하고 빠르다).
- 그 밖의 사이트는 페이지를 조금 읽어 og:title, og:image 같은 태그를 찾는다.
- 서버가 남의 주소를 대신 읽는 기능이라, 공개 인터넷 주소만 읽는다
  (사내망·클라우드 내부 주소로 요청을 보내게 만드는 공격을 막는다). 크기와 시간도 짧게 제한한다.
- 실패하면 빈 결과를 돌려준다. 미리보기가 없어도 취향은 저장된다.
"""
import http.client
import ipaddress
import json
import re
import socket
import ssl
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

from django.core.cache import cache

TIMEOUT = 4  # 초
MAX_BYTES = 512 * 1024  # 페이지 앞부분만 읽어도 태그는 대부분 <head> 에 있다
MAX_REDIRECTS = 3
USER_AGENT = "Mozilla/5.0 (compatible; NOSLinkPreview/1.0)"
CACHE_SECONDS = 60 * 60 * 24


@dataclass
class Preview:
    title: str = ""
    image: str = ""
    site: str = ""
    category: str = ""  # 짐작한 취향 분류 (음악·영상 등). 모르면 빈 값
    embed: str = ""  # 바로 재생할 수 있는 주소 (유튜브·스포티파이)
    embed_height: int = 0

    @property
    def empty(self):
        return not (self.title or self.image)

    def as_dict(self):
        return asdict(self)


# ---------- 재생 주소 (유튜브·스포티파이) ----------

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
SPOTIFY_PATH = re.compile(r"^/(?:intl-[a-z]{2}(?:-[a-z]{2})?/)?(track|album|playlist|episode|show|artist)/([A-Za-z0-9]{10,40})")


def youtube_id(url):
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if host not in YOUTUBE_HOSTS:
        return None
    if host == "youtu.be":
        candidate = parts.path.lstrip("/").split("/")[0]
    elif parts.path == "/watch":
        candidate = parse_qs(parts.query).get("v", [""])[0]
    else:
        m = re.match(r"^/(?:shorts|embed|live)/([^/?#]+)", parts.path)
        candidate = m.group(1) if m else ""
    return candidate if YOUTUBE_ID.match(candidate or "") else None


def spotify_kind(url):
    parts = urlsplit(url)
    if (parts.hostname or "").lower() != "open.spotify.com":
        return None
    m = SPOTIFY_PATH.match(parts.path)
    return (m.group(1), m.group(2)) if m else None


def embed_for(url):
    """(재생 주소, 높이). 재생할 수 없는 링크면 ("", 0)."""
    if not url:
        return "", 0
    vid = youtube_id(url)
    if vid:
        return f"https://www.youtube-nocookie.com/embed/{vid}", 0  # 높이는 CSS 가 16:9 로 맞춘다
    kind = spotify_kind(url)
    if kind:
        height = 152 if kind[0] in ("track", "episode") else 352
        return f"https://open.spotify.com/embed/{kind[0]}/{kind[1]}", height
    return "", 0


def guess_category(url):
    host = (urlsplit(url).hostname or "").lower()
    if host == "music.youtube.com" or host.endswith(("spotify.com", "melon.com", "genie.co.kr", "music.apple.com", "soundcloud.com", "flo.com", "vibe.naver.com")):
        return "음악"
    if host in YOUTUBE_HOSTS or host.endswith(("vimeo.com", "tiktok.com")):
        return "영상"
    if host.endswith(("netflix.com", "watcha.com", "tving.com", "wavve.com", "disneyplus.com", "coupangplay.com", "imdb.com", "themoviedb.org")):
        return "영화"
    if host.endswith(("yes24.com", "aladin.co.kr", "kyobobook.co.kr", "millie.co.kr", "ridibooks.com", "goodreads.com")):
        return "책"
    if host.endswith(("map.naver.com", "naver.me", "place.map.kakao.com", "map.kakao.com", "maps.google.com", "maps.app.goo.gl", "goo.gl")) or (
        host.startswith(("www.google.", "google.")) and "/maps" in urlsplit(url).path
    ):
        return "장소"
    return ""


# ---------- 안전하게 읽기 ----------

class UnsafeURL(Exception):
    pass


def check_public(url):
    """http(s) 이고, 이름이 가리키는 모든 IP 가 공개 인터넷 주소일 때만 통과."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise UnsafeURL("http(s) 주소만")
    if parts.username or parts.password:
        raise UnsafeURL("주소 안의 계정 정보")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if port not in (80, 443):
        raise UnsafeURL("기본 포트만")
    try:
        infos = socket.getaddrinfo(parts.hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise UnsafeURL("이름을 찾지 못함") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:
            raise UnsafeURL("공개 주소가 아님")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # 넘겨주는 주소도 검사하려고 직접 따라간다


def _tls_context():
    """인증서 목록은 certifi 것을 쓴다 (allauth → requests 를 따라 이미 설치돼 있다).
    Windows 의 Python 은 기본 목록에 중간 인증서가 빠져 있어 스포티파이 등에서 검증이 실패한다."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


_opener = build_opener(_NoRedirect, HTTPSHandler(context=_tls_context()))


def fetch(url, accept="text/html,application/xhtml+xml"):
    """(최종 주소, content-type, 앞부분 바이트). 넘겨주기는 매번 검사하며 3번까지 따라간다."""
    for _ in range(MAX_REDIRECTS + 1):
        check_public(url)
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept, "Accept-Language": "ko,en;q=0.8"})
        try:
            response = _opener.open(request, timeout=TIMEOUT)
        except HTTPError as e:
            if e.code in (301, 302, 303, 307, 308) and e.headers.get("Location"):
                url = urljoin(url, e.headers["Location"])
                continue
            raise
        with response:
            return response.geturl(), response.headers.get("Content-Type", ""), response.read(MAX_BYTES)
    raise UnsafeURL("넘겨주기가 너무 많음")


# ---------- 페이지에서 태그 찾기 ----------

class _MetaParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta = {}
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key and a.get("content") and key not in self.meta:
                self.meta[key] = a["content"].strip()
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title and len(self.title) < 300:
            self.title += data


def _decode(body, content_type):
    m = re.search(r"charset=([\w-]+)", content_type, re.I) or re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", body[:4096], re.I)
    charset = m.group(1) if m else "utf-8"
    if isinstance(charset, bytes):
        charset = charset.decode("ascii", "ignore")
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def _clean(text, limit):
    return re.sub(r"\s+", " ", text or "").strip()[:limit]


def _https_image(src, base):
    if not src:
        return ""
    url = urljoin(base, src)
    if url.startswith("//"):
        url = "https:" + url
    return url[:500] if url.startswith("https://") else ""  # http 그림은 https 화면에서 막히므로 버린다


def _from_html(url):
    final, content_type, body = fetch(url)
    if "html" not in content_type.lower():
        return Preview()
    parser = _MetaParser()
    try:
        parser.feed(_decode(body, content_type))
    except Exception:  # 깨진 HTML 이어도 찾은 데까지 쓴다
        pass
    m = parser.meta
    return Preview(
        title=_clean(m.get("og:title") or m.get("twitter:title") or parser.title, 200),
        image=_https_image(m.get("og:image:secure_url") or m.get("og:image") or m.get("twitter:image"), final),
        site=_clean(m.get("og:site_name") or (urlsplit(final).hostname or "").removeprefix("www."), 60),
    )


def _from_oembed(endpoint, url, site):
    _, _, body = fetch(f"{endpoint}?{urlencode({'url': url, 'format': 'json'})}", accept="application/json")
    data = json.loads(body.decode("utf-8"))
    title = data.get("title", "")
    author = data.get("author_name", "")
    if site == "YouTube" and author and author not in title:
        title = f"{title} · {author}"
    return Preview(title=_clean(title, 200), image=_https_image(data.get("thumbnail_url"), url), site=site)


def get_preview(url):
    """링크 하나의 미리보기. 같은 링크는 하루 동안 기억해 두고 다시 묻지 않는다."""
    url = (url or "").strip()
    if not url:
        return Preview()
    key = "linkpreview:" + url[:400]
    cached = cache.get(key)
    if cached is not None:
        return Preview(**cached)

    try:
        if youtube_id(url):
            preview = _from_oembed("https://www.youtube.com/oembed", url, "YouTube")
        elif spotify_kind(url):
            preview = _from_oembed("https://open.spotify.com/oembed", url, "Spotify")
        else:
            preview = _from_html(url)
    except (UnsafeURL, HTTPError, URLError, OSError, ValueError, UnicodeError, http.client.HTTPException):
        preview = Preview()
    preview.category = guess_category(url)
    preview.embed, preview.embed_height = embed_for(url)
    if not preview.empty:
        cache.set(key, preview.as_dict(), CACHE_SECONDS)
    return preview
