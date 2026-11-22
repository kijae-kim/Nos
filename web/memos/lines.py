"""메모 줄 목록 검사와 제목·미리 보기."""
from .models import MemoFolder

MAX_LINES = 2000
MAX_LINE = 1000
MAX_TOTAL = 20000
DEFAULT_FOLDERS = ["버킷리스트", "여행계획"]


def clean_lines(data):
    """보낸 줄 목록을 검사해 깨끗한 목록으로. 잘못되면 ValueError."""
    if not isinstance(data, list) or len(data) > MAX_LINES:
        raise ValueError("lines")
    out, total = [], 0
    for line in data:
        if not isinstance(line, dict):
            raise ValueError("line")
        kind, on, text = line.get("t"), line.get("on"), line.get("s")
        if kind not in ("text", "check") or not isinstance(on, bool) or not isinstance(text, str):
            raise ValueError("line")
        if len(text) > MAX_LINE:
            raise ValueError("line too long")
        text = text.replace("\r", "").replace("\n", " ")
        total += len(text)
        out.append({"t": kind, "on": on if kind == "check" else False, "s": text})
    if total > MAX_TOTAL:
        raise ValueError("too long")
    return out


def _show(line):
    mark = ("☑ " if line["on"] else "☐ ") if line["t"] == "check" else ""
    return mark + line["s"].strip()


def title_and_preview(lines):
    """제목 = 글이 있는 첫 줄, 미리 보기 = 그다음 글이 있는 줄 (체크면 ☐/☑)."""
    filled = [line for line in lines if line["s"].strip()]
    title = filled[0]["s"].strip()[:100] if filled else ""
    preview = _show(filled[1])[:120] if len(filled) > 1 else ""
    return title, preview


def ensure_default_folders(couple):
    """처음 들어올 때 기본 폴더 두 개. 두 사람이 동시에 들어와도 한 번만 (없는 것만 만든다)."""
    if couple.memo_folders.count() >= len(DEFAULT_FOLDERS):
        return
    for name in DEFAULT_FOLDERS:
        MemoFolder.objects.get_or_create(couple=couple, name=name)


def ordered_folders(qs):
    """기본 폴더 두 개(버킷리스트·여행계획) 먼저, 그다음 이름 순."""
    from django.db.models import Case, IntegerField, Value, When

    rank = Case(*[When(name=n, then=Value(i)) for i, n in enumerate(DEFAULT_FOLDERS)],
                default=Value(len(DEFAULT_FOLDERS)), output_field=IntegerField())
    return qs.annotate(rank=rank).order_by("rank", "name")
