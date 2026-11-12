"""앱 아이콘을 만든다: web/static/icons/ 의 icon.svg 와 icon-180/192/512.png

로고를 바꾸면 아래 SHAPES(와 색)만 고치고 다시 실행하면 된다.

    python tools/make_icons.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "web" / "static" / "icons"

BACKGROUND = "#2A45F5"
# 배 로고. 30 × 33 좌표에 그린 다각형 (색, 꼭짓점들)
LOGO_W, LOGO_H = 30, 33
SHAPES = [
    ("#FF5A5F", [(0, 24), (30, 24), (24, 33), (6, 33)]),  # 선체
    ("#FFFFFF", [(15, 0), (15, 21), (29, 21)]),  # 큰 돛
    ("#FFB8DC", [(12, 6), (12, 21), (3, 21)]),  # 작은 돛
]
LOGO_RATIO = 0.5  # 아이콘 너비에서 로고가 차지하는 비율. 기기가 모서리를 잘라도 안전한 크기
PNG_SIZES = [180, 192, 512]  # 180: iOS 홈 화면, 192·512: 안드로이드·설치 화면


def placed(size):
    """로고를 size × size 정사각형 가운데에 놓았을 때의 (색, 꼭짓점들)."""
    scale = size * LOGO_RATIO / LOGO_W
    dx = (size - LOGO_W * scale) / 2
    dy = (size - LOGO_H * scale) / 2
    return [(color, [(dx + x * scale, dy + y * scale) for x, y in points]) for color, points in SHAPES]


def write_png(size):
    big = size * 4  # 크게 그린 뒤 줄여서 가장자리를 부드럽게 한다
    image = Image.new("RGB", (big, big), BACKGROUND)
    draw = ImageDraw.Draw(image)
    for color, points in placed(big):
        draw.polygon(points, fill=color)
    image.resize((size, size), Image.LANCZOS).save(OUT / f"icon-{size}.png", optimize=True)


def write_svg(size=512):
    polygons = "\n".join(
        '  <polygon fill="{}" points="{}"/>'.format(color, " ".join(f"{x:g},{y:g}" for x, y in points))
        for color, points in placed(size)
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}">\n'
        f'  <rect width="{size}" height="{size}" rx="{size * 0.22:g}" fill="{BACKGROUND}"/>\n'
        f"{polygons}\n</svg>\n"
    )
    (OUT / "icon.svg").write_text(svg, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    write_svg()
    for s in PNG_SIZES:
        write_png(s)
    print("만든 파일:", ", ".join(sorted(p.name for p in OUT.iterdir())))
