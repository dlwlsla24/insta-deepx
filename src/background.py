"""기사 이미지 추출 + 세련된 배경 직접 생성 (AI 이미지 생성 안 함).

- 기사 페이지에서 본문 텍스트와 대표 이미지(og:image)를 추출한다.
- 대표 이미지가 있으면 커버 배경으로 쓰고, 본문/아웃트로 카드는 그 이미지의
  색을 뽑아 만든 mesh 그라데이션 배경을 쓴다 (사진 위 본문 텍스트 가독성 확보).
- 이미지가 없으면 브랜드 팔레트로 mesh 배경을 생성한다.
"""

# Python 3.9 호환: PEP 604 (X | None) 유니온 어노테이션을 지연 평가
from __future__ import annotations

import hashlib
import io
import random
import re
import urllib.parse

import requests
import trafilatura
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFilter

from src.config import GENERATED_BG_PALETTE, IMAGE_SIZE

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
# 이 크기보다 작으면 로고/아이콘으로 보고 사진으로 안 씀 (짧은 변 기준)
_MIN_IMAGE_DIM = 400


# ---------------------------------------------------------------------------
# 기사 fetch (본문 + 대표 이미지)
# ---------------------------------------------------------------------------
def _download_html(url: str) -> str | None:
    try:
        resp = requests.get(url, headers={"User-Agent": _UA}, timeout=30)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or resp.encoding
        return resp.text
    except requests.RequestException as e:
        print(f"[background] HTML 다운로드 실패: {e}")
        return None


def _extract_og_image_url(html: str, base_url: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for selector, attr in (
        ('meta[property="og:image"]', "content"),
        ('meta[name="og:image"]', "content"),
        ('meta[name="twitter:image"]', "content"),
        ('meta[property="twitter:image"]', "content"),
        ("link[rel='image_src']", "href"),
    ):
        tag = soup.select_one(selector)
        if tag and tag.get(attr):
            return urllib.parse.urljoin(base_url, tag[attr].strip())
    return None


def _candidate_image_urls(og_url: str) -> list[str]:
    """og:image URL 후보 목록. 한국 뉴스 CMS 공통 패턴(작은 썸네일)을 원본으로 승격.

    예: .../news/thumbnail/.../39383_..._v150.jpg → .../news/photo/.../39383_....jpg
    원본을 먼저 시도하고, 실패하면 원래 og:image 로 폴백.
    """
    candidates: list[str] = []
    full = og_url.replace("/thumbnail/", "/photo/")
    full = re.sub(r"_v\d+(\.\w+)(\?.*)?$", r"\1\2", full)
    if full != og_url:
        candidates.append(full)
    candidates.append(og_url)
    return candidates


def _fetch_image(img_url: str) -> Image.Image | None:
    """이미지 URL 다운로드·디코딩. 실패 시 None (크기 검증/크롭은 호출자가)."""
    try:
        resp = requests.get(img_url, headers={"User-Agent": _UA}, timeout=30)
        resp.raise_for_status()
        if "image" not in resp.headers.get("Content-Type", "image"):
            return None
        return Image.open(io.BytesIO(resp.content)).convert("RGB")
    except (requests.RequestException, OSError, ValueError) as e:
        print(f"[background] 이미지 다운로드/디코딩 실패: {e}")
        return None


def _to_square(img: Image.Image) -> Image.Image:
    """center-crop 정사각 후 IMAGE_SIZE 리사이즈."""
    w, h = img.size
    side = min(w, h)
    left, top = (w - side) // 2, (h - side) // 2
    img = img.crop((left, top, left + side, top + side))
    return img.resize((IMAGE_SIZE, IMAGE_SIZE), Image.LANCZOS)


def _resolve_article_image(og_url: str) -> Image.Image | None:
    """og:image 후보들을 순회하며 충분히 큰 이미지를 정사각으로 반환. 없으면 None."""
    for url in _candidate_image_urls(og_url):
        img = _fetch_image(url)
        if img is None:
            continue
        w, h = img.size
        if min(w, h) < _MIN_IMAGE_DIM:
            print(f"[background] 이미지가 작음 ({w}x{h}) → 다음 후보/폴백")
            continue
        print(f"[background] 기사 이미지 사용: {w}x{h} ({url})")
        return _to_square(img)
    return None


def fetch_article(url: str) -> tuple[str, Image.Image | None]:
    """기사 URL에서 (본문 텍스트, 대표 이미지|None) 추출."""
    html = _download_html(url)
    if not html:
        return "", None

    body = (
        trafilatura.extract(
            html, include_comments=False, include_tables=False, favor_precision=True
        )
        or ""
    ).strip()

    image = None
    og_url = _extract_og_image_url(html, url)
    if og_url:
        image = _resolve_article_image(og_url)

    return body, image


# ---------------------------------------------------------------------------
# 색 추출 + mesh 배경 생성
# ---------------------------------------------------------------------------
def dominant_palette(image: Image.Image, n: int = 5) -> list[tuple[int, int, int]]:
    """이미지에서 빈도순 대표색 추출 (어두운 mesh 배경 톤으로 약간 보정)."""
    small = image.convert("RGB").resize((120, 120))
    q = small.quantize(colors=max(n, 3), method=Image.MEDIANCUT)
    pal = q.getpalette()
    colors: list[tuple[int, int, int]] = []
    for _count, idx in sorted(q.getcolors(), reverse=True):
        rgb = tuple(pal[idx * 3 : idx * 3 + 3])
        colors.append(rgb)  # type: ignore[arg-type]
    return colors[:n] or list(GENERATED_BG_PALETTE)


def _shade(c: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return tuple(max(0, min(255, int(v * factor))) for v in c)  # type: ignore[return-value]


def _mix(a, b, t):
    return tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3))


def _vertical_gradient(size: int, top, bottom) -> Image.Image:
    """수평선 드로잉 기반 세로 그라데이션 (per-pixel 루프 없이 빠르게)."""
    img = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(img)
    for y in range(size):
        t = y / size
        draw.line([(0, y), (size, y)], fill=_mix(top, bottom, t))
    return img


def _add_grain(img: Image.Image, sigma: float = 10.0, alpha: float = 0.05) -> Image.Image:
    """미세 노이즈 그레인 — 평평한 그라데이션에 질감 부여 (PIL C 구현, 빠름)."""
    noise = Image.effect_noise((img.width, img.height), sigma).convert("RGB")
    return Image.blend(img, noise, alpha)


def generate_mesh_background(
    palette: list[tuple[int, int, int]], seed: int, size: int = IMAGE_SIZE
) -> Image.Image:
    """팔레트 기반 세련된 mesh 그라데이션 배경.

    어두운 대각 그라데이션 위에 팔레트 색의 부드러운 blob 여러 개를 깔고 강하게
    블러해 mesh 느낌을 낸 뒤, 미세 그레인과 비네팅을 더한다. seed로 매번 구도가 다르다.
    """
    rng = random.Random(seed)
    pal = list(palette) or list(GENERATED_BG_PALETTE)

    # 텍스트 가독성을 위해 전체 톤을 어둡게 깐다
    dark = _shade(min(pal, key=sum), 0.45)
    base = _vertical_gradient(size, _shade(dark, 1.25), dark)

    # 팔레트 색 blob 여러 개 → 강한 블러로 mesh
    layer = base.copy()
    d = ImageDraw.Draw(layer)
    for _ in range(rng.randint(5, 7)):
        color = _shade(pal[rng.randrange(len(pal))], rng.uniform(0.55, 0.9))
        r = rng.randint(size // 4, size // 2)
        cx = rng.randint(-size // 6, size + size // 6)
        cy = rng.randint(-size // 6, size + size // 6)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    layer = layer.filter(ImageFilter.GaussianBlur(radius=size // 5))

    img = Image.blend(base, layer, 0.82)

    # 가장자리 비네팅 (중앙은 살리고 모서리만 어둡게)
    vignette = Image.new("L", (size, size), 0)
    vd = ImageDraw.Draw(vignette)
    vd.ellipse([-size // 4, -size // 4, size + size // 4, size + size // 4], fill=255)
    vignette = vignette.filter(ImageFilter.GaussianBlur(radius=size // 6))
    darkened = _shade_image(img, 0.6)
    img = Image.composite(img, darkened, vignette)

    return _add_grain(img)


def _shade_image(img: Image.Image, factor: float) -> Image.Image:
    from PIL import ImageEnhance

    return ImageEnhance.Brightness(img).enhance(factor)


def _seed(text: str) -> int:
    return int(hashlib.md5(text.encode("utf-8")).hexdigest()[:8], 16)


def build_backgrounds(article_url: str, image: Image.Image | None) -> dict:
    """카드별 배경 묶음 생성.

    반환: {"cover": Image, "content": Image, "outro": Image, "source": "photo"|"generated"}
    - 이미지 있으면 cover=실제 사진, content/outro=사진 색 기반 mesh
    - 이미지 없으면 전부 브랜드 팔레트 mesh
    """
    seed = _seed(article_url)
    if image is not None:
        palette = dominant_palette(image)
        return {
            "cover": image,
            "content": generate_mesh_background(palette, seed + 7),
            "outro": generate_mesh_background(palette, seed + 13),
            "source": "photo",
        }

    palette = list(GENERATED_BG_PALETTE)
    return {
        "cover": generate_mesh_background(palette, seed),
        "content": generate_mesh_background(palette, seed + 7),
        "outro": generate_mesh_background(palette, seed + 13),
        "source": "generated",
    }


if __name__ == "__main__":
    import sys

    from src.config import OUTPUT_DIR

    if len(sys.argv) > 1:
        test_url = sys.argv[1]
        body, image = fetch_article(test_url)
        print(f"[background] 본문 {len(body)}자, 이미지 {'있음' if image else '없음'}")
        bgs = build_backgrounds(test_url, image)
    else:
        print("[background] URL 미지정 → 생성 배경 데모만 출력")
        bgs = build_backgrounds("demo://deepx", None)

    print(f"[background] source={bgs['source']}")
    for name in ("cover", "content", "outro"):
        p = OUTPUT_DIR / f"_bg_{name}.png"
        bgs[name].save(p, "PNG")
        print(f"  → {p}")
