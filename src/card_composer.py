from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from src.config import (
    BRAND_ACCENT,
    BRAND_ACCENT_INK,
    BRAND_BG,
    BRAND_NAME,
    BRAND_PRIMARY,
    BRAND_SUBTEXT,
    BRAND_TAGLINE,
    BRAND_TEXT,
    FONT_DIR,
    IMAGE_SIZE,
    INSTAGRAM_HANDLE,
    LOGO_PATH,
    OUTPUT_DIR,
)
from src.summarizer import ContentCard


def _circular_logo(size: int) -> Optional[Image.Image]:
    """로고를 정사각형으로 리사이즈 후 원형 마스크 적용. 파일 없으면 None."""
    if not LOGO_PATH.exists():
        return None
    logo = Image.open(LOGO_PATH).convert("RGBA")
    logo = logo.resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    logo.putalpha(mask)
    return logo


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    """폰트 로드. 없으면 fallback 체인을 따라감."""
    fallback_chain = {
        "Jalnan2TTF.ttf": ["Pretendard-Black.ttf", "Pretendard-ExtraBold.ttf", "Pretendard-Bold.ttf"],
        "MaruBuri-Bold.ttf": ["Pretendard-Bold.ttf"],
        "MaruBuri-SemiBold.ttf": ["Pretendard-Bold.ttf", "Pretendard-Medium.ttf"],
        "MaruBuri-Regular.ttf": ["Pretendard-Medium.ttf", "Pretendard-Regular.ttf"],
        "MaruBuri-Light.ttf": ["Pretendard-Light.ttf", "Pretendard-Regular.ttf"],
        "Pretendard-Black.ttf": ["Pretendard-ExtraBold.ttf", "Pretendard-Bold.ttf"],
        "Pretendard-ExtraBold.ttf": ["Pretendard-Bold.ttf"],
        "Pretendard-Light.ttf": ["Pretendard-Regular.ttf"],
        "Pretendard-Medium.ttf": ["Pretendard-Regular.ttf"],
    }
    candidates = [name] + fallback_chain.get(name, [])
    for candidate in candidates:
        path = FONT_DIR / candidate
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default(size=size)


def _apply_bg_light(bg: Image.Image, white_amount: float = 0.68) -> Image.Image:
    """본문 카드용 배경 처리: 강한 블러 + 약하게 밝게 + 흰색 오버레이.
    어두운 mesh/사진 배경을 밝은 틴트로 만들어 어두운 본문 텍스트 가독성 확보."""
    bg = bg.copy().resize((IMAGE_SIZE, IMAGE_SIZE), Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(radius=28))
    bg = ImageEnhance.Brightness(bg).enhance(1.15)
    overlay = Image.new("RGB", bg.size, (255, 255, 255))
    return Image.blend(bg, overlay, white_amount)


def _apply_bg_dark(bg: Image.Image, dark_amount: float = 0.76) -> Image.Image:
    """아웃트로 카드용 배경 처리: 강한 블러 + 어둡게 + 어두운 오버레이."""
    bg = bg.copy().resize((IMAGE_SIZE, IMAGE_SIZE), Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(radius=22))
    bg = ImageEnhance.Brightness(bg).enhance(0.5)
    overlay = Image.new("RGB", bg.size, BRAND_PRIMARY)
    return Image.blend(bg, overlay, dark_amount)


def _text_width(text: str, font: ImageFont.FreeTypeFont) -> int:
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0]


def _wrap(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """어절(띄어쓰기) 기준 wrap. 한 단어가 max_width보다 길면 글자 단위로 폴백.
    명시적 줄바꿈 \\n 존중."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        current = ""
        for word in paragraph.split(" "):
            sep = " " if current else ""
            trial = current + sep + word
            if _text_width(trial, font) <= max_width:
                current = trial
                continue
            if current:
                lines.append(current)
                current = ""
            if _text_width(word, font) <= max_width:
                current = word
            else:
                char_buf = ""
                for ch in word:
                    if _text_width(char_buf + ch, font) > max_width and char_buf:
                        lines.append(char_buf)
                        char_buf = ch
                    else:
                        char_buf += ch
                current = char_buf
        if current:
            lines.append(current)
    return lines


def _draw_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    color: tuple[int, int, int],
    x: int,
    y: int,
    line_spacing: int,
    paragraph_gap: Optional[int] = None,
) -> int:
    line_height = font.size + line_spacing
    if paragraph_gap is None:
        paragraph_gap = line_height // 2
    for line in lines:
        if line == "":
            y += paragraph_gap
        else:
            draw.text((x, y), line, font=font, fill=color)
            y += line_height
    return y


def _fit_text(
    text: str,
    font_path: str,
    sizes: list[int],
    max_width: int,
    max_height: int,
    line_spacing: int,
    paragraph_gap_ratio: float = 0.5,
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    chosen_font = _font(font_path, sizes[-1])
    chosen_lines: list[str] = []
    for size in sizes:
        font = _font(font_path, size)
        lines = _wrap(text, font, max_width)
        line_height = size + line_spacing
        para_gap = int(line_height * paragraph_gap_ratio)
        total = sum(line_height if line else para_gap for line in lines)
        if total <= max_height:
            return font, lines
        chosen_font, chosen_lines = font, lines
    line_height = chosen_font.size + line_spacing
    para_gap = int(line_height * paragraph_gap_ratio)
    truncated: list[str] = []
    used = 0
    for line in chosen_lines:
        h = line_height if line else para_gap
        if used + h > max_height:
            if truncated and truncated[-1]:
                truncated[-1] = truncated[-1][:-1] + "…"
            break
        truncated.append(line)
        used += h
    return chosen_font, truncated


def _draw_centered_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    color: tuple[int, int, int],
    y_center: int,
    line_spacing: int = 16,
) -> None:
    line_heights = [font.getbbox(line)[3] - font.getbbox(line)[1] for line in lines]
    total = sum(line_heights) + line_spacing * (len(lines) - 1)
    y = y_center - total // 2
    for line, h in zip(lines, line_heights):
        bbox = font.getbbox(line)
        w = bbox[2] - bbox[0]
        draw.text(((IMAGE_SIZE - w) // 2, y), line, font=font, fill=color)
        y += h + line_spacing


# ===========================================================================
# 마크업 강조 (`**키워드**` → 색상 다른 텍스트로 렌더)
# ===========================================================================

def _parse_markup_to_chars(text: str) -> list[tuple[str, bool]]:
    chars: list[tuple[str, bool]] = []
    is_h = False
    i = 0
    while i < len(text):
        if text[i : i + 2] == "**":
            is_h = not is_h
            i += 2
        else:
            chars.append((text[i], is_h))
            i += 1
    return chars


def _line_width(line: list[tuple[str, bool]], font: ImageFont.FreeTypeFont) -> float:
    if not line:
        return 0.0
    return font.getlength("".join(c for c, _ in line))


def _wrap_marked(
    chars: list[tuple[str, bool]],
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> list[list[tuple[str, bool]]]:
    lines: list[list[tuple[str, bool]]] = []
    current: list[tuple[str, bool]] = []

    i = 0
    while i < len(chars):
        ch, h = chars[i]
        if ch == "\n":
            lines.append(current)
            current = []
            i += 1
            continue
        if ch == " ":
            if current and _line_width(current, font) + font.getlength(" ") <= max_width:
                current.append((" ", h))
            i += 1
            continue
        word: list[tuple[str, bool]] = []
        while i < len(chars) and chars[i][0] not in (" ", "\n"):
            word.append(chars[i])
            i += 1
        word_w = sum(font.getlength(c) for c, _ in word)
        cur_w = _line_width(current, font)
        if cur_w + word_w <= max_width:
            current.extend(word)
        elif word_w <= max_width:
            lines.append(current)
            current = list(word)
        else:
            for c, hh in word:
                cw = font.getlength(c)
                if _line_width(current, font) + cw > max_width and current:
                    lines.append(current)
                    current = []
                current.append((c, hh))
    if current:
        lines.append(current)
    return lines


def _fit_text_marked(
    text: str,
    font_path: str,
    sizes: list[int],
    max_width: int,
    max_height: int,
    line_spacing: int,
    paragraph_gap_ratio: float = 0.5,
) -> tuple[ImageFont.FreeTypeFont, list[list[tuple[str, bool]]], int]:
    chars = _parse_markup_to_chars(text)
    last_font = _font(font_path, sizes[-1])
    last_lines: list[list[tuple[str, bool]]] = []
    last_gap = 0
    for size in sizes:
        font = _font(font_path, size)
        lines = _wrap_marked(chars, font, max_width)
        line_height = size + line_spacing
        para_gap = int(line_height * paragraph_gap_ratio)
        total = sum(line_height if line else para_gap for line in lines)
        if total <= max_height:
            return font, lines, para_gap
        last_font, last_lines, last_gap = font, lines, para_gap
    return last_font, last_lines, last_gap


def _draw_marked_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[list[tuple[str, bool]]],
    font: ImageFont.FreeTypeFont,
    plain_color: tuple[int, int, int],
    highlight_color: tuple[int, int, int],
    x: int,
    y: int,
    line_spacing: int,
    paragraph_gap: int,
) -> int:
    line_height = font.size + line_spacing
    for chars in lines:
        if not chars:
            y += paragraph_gap
            continue
        cx = x
        i = 0
        while i < len(chars):
            j = i
            while j < len(chars) and chars[j][1] == chars[i][1]:
                j += 1
            segment = "".join(c for c, _ in chars[i:j])
            color = highlight_color if chars[i][1] else plain_color
            draw.text((cx, y), segment, font=font, fill=color)
            cx += font.getlength(segment)
            i = j
        y += line_height
    return y


def _draw_centered_marked_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[list[tuple[str, bool]]],
    font: ImageFont.FreeTypeFont,
    plain_color: tuple[int, int, int],
    highlight_color: tuple[int, int, int],
    y: int,
    line_spacing: int,
) -> int:
    line_height = font.size + line_spacing
    for chars in lines:
        if not chars:
            y += line_height // 2
            continue
        total_w = sum(font.getlength(c) for c, _ in chars)
        cx = (IMAGE_SIZE - total_w) // 2
        i = 0
        while i < len(chars):
            j = i
            while j < len(chars) and chars[j][1] == chars[i][1]:
                j += 1
            segment = "".join(c for c, _ in chars[i:j])
            color = highlight_color if chars[i][1] else plain_color
            draw.text((cx, y), segment, font=font, fill=color)
            cx += font.getlength(segment)
            i = j
        y += line_height
    return y


def compose_title_card(
    background: Image.Image,
    headline: str,
    subheadline: str,
    source: str,
) -> Image.Image:
    img = background.copy().resize((IMAGE_SIZE, IMAGE_SIZE), Image.LANCZOS)
    # 실제 사진이 와도 텍스트가 읽히도록 가벼운 블러 + 어둡게
    img = img.filter(ImageFilter.GaussianBlur(radius=4))
    img = ImageEnhance.Brightness(img).enhance(0.62)
    # 상하단 그라디언트 오버레이 — 중앙 배경은 살림
    overlay = Image.new("RGBA", (IMAGE_SIZE, IMAGE_SIZE), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for y in range(IMAGE_SIZE):
        if y < 300:
            alpha = int(190 * (1 - y / 300))
        elif y > IMAGE_SIZE - 240:
            t = (y - (IMAGE_SIZE - 240)) / 240
            alpha = int(190 * t)
        else:
            alpha = 0
        od.line([(0, y), (IMAGE_SIZE, y)], fill=(0, 0, 0, alpha))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(img)
    subheadline_font = _font("Pretendard-Medium.ttf", 42)
    source_font = _font("Pretendard-Light.ttf", 28)
    brand_label_font = _font("Pretendard-Light.ttf", 26)
    brand_font = _font("Pretendard-Black.ttf", 60)

    margin = 80
    max_width = IMAGE_SIZE - margin * 2

    # 상단 — 원형 로고 + 태그라인 + 브랜드 pill
    logo_size = 100
    logo = _circular_logo(logo_size)
    if logo is not None:
        img.paste(logo, ((IMAGE_SIZE - logo_size) // 2, 60), logo)

    label_text = BRAND_TAGLINE
    bbox = brand_label_font.getbbox(label_text)
    lw = bbox[2] - bbox[0]
    draw.text(
        ((IMAGE_SIZE - lw) // 2, 175),
        label_text,
        font=brand_label_font,
        fill=(200, 214, 230),
    )
    bbox = brand_font.getbbox(BRAND_NAME)
    bw = bbox[2] - bbox[0]
    bh = bbox[3] - bbox[1]
    pill_pad_x, pill_pad_y = 32, 14
    pill_x = (IMAGE_SIZE - bw) // 2 - pill_pad_x
    pill_y = 212
    draw.rounded_rectangle(
        (pill_x, pill_y, pill_x + bw + pill_pad_x * 2, pill_y + bh + pill_pad_y * 2),
        radius=18,
        fill=BRAND_ACCENT,
    )
    draw.text(
        ((IMAGE_SIZE - bw) // 2, pill_y + pill_pad_y - 4),
        BRAND_NAME,
        font=brand_font,
        fill=BRAND_PRIMARY,
    )

    # 헤드라인 — 잘난체 + 마크업 강조(시안)
    headline_font, headline_marked_lines, _ = _fit_text_marked(
        headline,
        font_path="Jalnan2TTF.ttf",
        sizes=[92, 84, 76, 68, 60],
        max_width=max_width,
        max_height=380,
        line_spacing=14,
    )
    line_height = headline_font.size + 14
    total_h = line_height * len(headline_marked_lines)
    y_start = (IMAGE_SIZE - total_h) // 2 + 20
    headline_highlight = (125, 211, 252)  # sky-300
    y = _draw_centered_marked_lines(
        draw, headline_marked_lines, headline_font,
        plain_color=(255, 255, 255),
        highlight_color=headline_highlight,
        y=y_start, line_spacing=14,
    )

    sub_lines = _wrap(subheadline, subheadline_font, max_width)
    _draw_centered_lines(
        draw, sub_lines, subheadline_font, (215, 225, 238), y + 60
    )

    src_text = f"via {source}"
    bbox = source_font.getbbox(src_text)
    sw = bbox[2] - bbox[0]
    draw.text(
        ((IMAGE_SIZE - sw) // 2, IMAGE_SIZE - 80),
        src_text,
        font=source_font,
        fill=(170, 184, 200),
    )

    return img


def compose_content_card(
    index: int, total: int, card: ContentCard, background: Optional[Image.Image] = None
) -> Image.Image:
    if background is not None:
        img = _apply_bg_light(background)
    else:
        img = Image.new("RGB", (IMAGE_SIZE, IMAGE_SIZE), BRAND_BG)
    draw = ImageDraw.Draw(img)

    section_font = _font("Pretendard-Bold.ttf", 30)
    brand_font = _font("Pretendard-Bold.ttf", 30)
    footer_font = _font("Pretendard-Regular.ttf", 26)

    margin = 80
    max_width = IMAGE_SIZE - margin * 2

    # 좌상단: 섹션 라벨
    section_text = f"{index:02d}  ·  {card.section}"
    draw.text((margin, 80), section_text, font=section_font, fill=BRAND_ACCENT_INK)

    # 우상단: 브랜드
    bbox = brand_font.getbbox(BRAND_NAME)
    bw = bbox[2] - bbox[0]
    draw.text(
        (IMAGE_SIZE - margin - bw, 80),
        BRAND_NAME,
        font=brand_font,
        fill=BRAND_ACCENT_INK,
    )

    # 액센트 바
    draw.rectangle((margin, 130, margin + 80, 138), fill=BRAND_ACCENT_INK)

    # 타이틀 — 마루 부리 Bold
    title_y_start = 210
    title_max_height = 200
    title_font, title_lines = _fit_text(
        card.title,
        font_path="MaruBuri-Bold.ttf",
        sizes=[68, 60, 54, 48],
        max_width=max_width,
        max_height=title_max_height,
        line_spacing=10,
    )
    title_y = _draw_lines(
        draw, title_lines, title_font, BRAND_TEXT,
        x=margin, y=title_y_start, line_spacing=10,
    )

    # 본문 — 마루 부리 Regular + 마크업 강조
    body_y_start = title_y + 50
    body_y_end = IMAGE_SIZE - 110
    body_available = body_y_end - body_y_start
    body_font, body_marked_lines, body_para_gap = _fit_text_marked(
        card.body,
        font_path="MaruBuri-Regular.ttf",
        sizes=[38, 36, 34, 32, 30],
        max_width=max_width,
        max_height=body_available,
        line_spacing=14,
        paragraph_gap_ratio=0.45,
    )
    _draw_marked_lines(
        draw, body_marked_lines, body_font,
        plain_color=BRAND_TEXT,
        highlight_color=BRAND_ACCENT_INK,
        x=margin, y=body_y_start,
        line_spacing=14, paragraph_gap=body_para_gap,
    )

    draw.text(
        (margin, IMAGE_SIZE - 80),
        f"@{INSTAGRAM_HANDLE}",
        font=footer_font,
        fill=BRAND_SUBTEXT,
    )

    page_text = f"{index} / {total}"
    bbox = footer_font.getbbox(page_text)
    pw = bbox[2] - bbox[0]
    draw.text(
        (IMAGE_SIZE - margin - pw, IMAGE_SIZE - 80),
        page_text,
        font=footer_font,
        fill=BRAND_SUBTEXT,
    )

    return img


def compose_outro_card(
    hashtags: list[str], background: Optional[Image.Image] = None
) -> Image.Image:
    if background is not None:
        img = _apply_bg_dark(background)
    else:
        img = Image.new("RGB", (IMAGE_SIZE, IMAGE_SIZE), BRAND_PRIMARY)
    draw = ImageDraw.Draw(img)

    pitch_label_font = _font("Pretendard-Medium.ttf", 30)
    pitch_font = _font("Pretendard-ExtraBold.ttf", 46)
    brand_font = _font("Pretendard-Black.ttf", 92)
    follow_font = _font("Pretendard-Bold.ttf", 44)
    handle_font = _font("Pretendard-Bold.ttf", 40)
    secondary_font = _font("Pretendard-Light.ttf", 26)
    tag_font = _font("Pretendard-Medium.ttf", 28)

    margin = 80
    max_width = IMAGE_SIZE - margin * 2

    # 상단 — 정체성
    _draw_centered_lines(
        draw, ["딥엑스(DeepX)의 새 소식을"], pitch_label_font, (200, 214, 230), 80,
    )
    _draw_centered_lines(
        draw, ["카드뉴스로 빠르게 정리해드려요"], pitch_font, (255, 255, 255), 130,
    )

    # 중앙 — 원형 로고
    logo_size = 220
    logo = _circular_logo(logo_size)
    logo_y = 250
    if logo is not None:
        img.paste(logo, ((IMAGE_SIZE - logo_size) // 2, logo_y), logo)

    # 로고 아래 — 브랜드 pill
    bbox = brand_font.getbbox(BRAND_NAME)
    bw = bbox[2] - bbox[0]
    bh = bbox[3] - bbox[1]
    pill_pad_x, pill_pad_y = 44, 22
    pill_x = (IMAGE_SIZE - bw) // 2 - pill_pad_x
    pill_y = logo_y + logo_size + 36
    draw.rounded_rectangle(
        (pill_x, pill_y, pill_x + bw + pill_pad_x * 2, pill_y + bh + pill_pad_y * 2),
        radius=28,
        fill=BRAND_ACCENT,
    )
    draw.text(
        ((IMAGE_SIZE - bw) // 2, pill_y + pill_pad_y - 8),
        BRAND_NAME,
        font=brand_font,
        fill=BRAND_PRIMARY,
    )

    follow_y = pill_y + bh + pill_pad_y * 2 + 44
    _draw_centered_lines(
        draw, ["팔로우하고 딥엑스 소식 챙겨받기"], follow_font, (255, 255, 255), follow_y,
    )
    _draw_centered_lines(
        draw, [f"@{INSTAGRAM_HANDLE}"], handle_font, BRAND_ACCENT, follow_y + 70,
    )

    _draw_centered_lines(
        draw, ["좋아요  ·  저장  ·  공유 환영"], secondary_font, (160, 174, 192),
        IMAGE_SIZE - 160,
    )

    tag_text = "  ".join(hashtags[:6])
    tag_lines = _wrap(tag_text, tag_font, max_width)[:2]
    _draw_centered_lines(draw, tag_lines, tag_font, BRAND_ACCENT, IMAGE_SIZE - 90)

    return img


def compose_all(
    backgrounds: dict,
    headline: str,
    subheadline: str,
    source: str,
    cards: list[ContentCard],
    hashtags: list[str],
    out_dir: Path = OUTPUT_DIR,
) -> list[Path]:
    """backgrounds: {"cover": Image, "content": Image, "outro": Image} (background.build_backgrounds 결과)."""
    paths: list[Path] = []

    title = compose_title_card(backgrounds["cover"], headline, subheadline, source)
    p = out_dir / "card_00_title.png"
    title.save(p, "PNG", optimize=True)
    paths.append(p)

    total = len(cards)
    for i, card in enumerate(cards, start=1):
        composed = compose_content_card(i, total, card, background=backgrounds["content"])
        p = out_dir / f"card_{i:02d}_content.png"
        composed.save(p, "PNG", optimize=True)
        paths.append(p)

    outro = compose_outro_card(hashtags, background=backgrounds["outro"])
    p = out_dir / "card_99_outro.png"
    outro.save(p, "PNG", optimize=True)
    paths.append(p)

    return paths


if __name__ == "__main__":
    from src.background import build_backgrounds

    sample_cards = [
        ContentCard(
            section="핵심",
            title="딥엑스, 대만 에이온과\n사업 협력 MOU",
            body="AI 반도체 스타트업 **딥엑스(DeepX)**가 대만 기업 에이온과 업무협약(MOU)을 맺었다.\n\n온디바이스 AI 칩을 산업 현장과 로봇 등 '피지컬 AI' 영역으로 확대하기 위한 협력이다.",
        ),
        ContentCard(
            section="배경",
            title="클라우드 아닌\n기기에서 돌리는 AI",
            body="기존 AI 연산은 대부분 거대한 데이터센터(클라우드)에서 처리됐다.\n\n딥엑스는 이를 **기기 자체**에서 처리하는 NPU(AI 연산 전용 칩)에 집중한다. 전력을 적게 쓰고 응답이 빠른 것이 강점이다.",
        ),
        ContentCard(
            section="기술",
            title="저전력 엣지 AI에\n특화된 NPU",
            body="딥엑스의 NPU는 카메라·로봇·가전 같은 기기에 들어가 **실시간 추론**을 담당한다.\n\n클라우드로 데이터를 보내지 않아 지연이 적고, 개인정보가 기기 밖으로 나가지 않는다는 장점도 있다.",
        ),
        ContentCard(
            section="의미",
            title="엔비디아가 비운\n엣지 시장을 겨냥",
            body="엔비디아가 데이터센터용 고성능 칩을 장악한 가운데, 딥엑스는 **엣지(현장) 시장**을 노린다.\n\n저전력·저비용이 중요한 산업 현장에서는 다른 게임의 규칙이 적용되기 때문이다.",
        ),
        ContentCard(
            section="전망",
            title="한국 팹리스의\n글로벌 확장 시험대",
            body="이번 협력은 딥엑스가 해외 고객을 확보하는 사례로 주목된다.\n\n설계만 하고 생산은 위탁하는 **팹리스** 기업인 딥엑스가 양산과 글로벌 수주를 이어갈 수 있을지가 관건이다.",
        ),
    ]

    bgs = build_backgrounds("demo://deepx-sample", None)
    sample_paths = compose_all(
        backgrounds=bgs,
        headline="딥엑스, **대만**과 손잡았다",
        subheadline="에이온과 피지컬 AI 협력 MOU",
        source="news.einfomax.co.kr",
        cards=sample_cards,
        hashtags=["#딥엑스", "#DeepX", "#AI반도체", "#NPU", "#엣지AI", "#반도체"],
    )
    for path in sample_paths:
        print(f"[ok] {path}")
