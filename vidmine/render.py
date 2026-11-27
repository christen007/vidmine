"""Card-front images: resize the frame and draw the Japanese line onto it."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .config import Config

FONT_CANDIDATES = [
    # Windows (bold first: reads better over video)
    "C:/Windows/Fonts/YuGothB.ttc",
    "C:/Windows/Fonts/BIZ-UDGothicB.ttc",
    "C:/Windows/Fonts/meiryob.ttc",
    "C:/Windows/Fonts/meiryo.ttc",
    "C:/Windows/Fonts/msgothic.ttc",
    # macOS / Linux
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
]

# Characters that must not start a line (kinsoku shori).
NO_LINE_START = set("、。，．！？!?）」』】〕〉》ーっゃゅょぁぃぅぇぉッャュョァィゥェォ…‥・ゝゞ々")


def find_font(cfg: Config) -> str:
    if cfg.image.font:
        return cfg.image.font
    from .config import bundled
    for c in [p for p in [bundled("NotoSansJP-Bold.otf")] if p] + FONT_CANDIDATES:
        if Path(c).exists():
            return c
    raise RuntimeError("No Japanese font found; set [image] font in config.toml")


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        cur = ""
        for ch in para:
            if cur and draw.textlength(cur + ch, font=font) > max_w and ch not in NO_LINE_START:
                lines.append(cur)
                cur = ch
            else:
                cur += ch
        if cur:
            lines.append(cur)
    return lines


def make_scene_images(cfg: Config, frame_png: Path, sentence: str,
                      out_scene: Path, out_raw: Path) -> None:
    img = Image.open(frame_png).convert("RGB")
    if img.width > cfg.image.max_width:
        h = round(img.height * cfg.image.max_width / img.width)
        img = img.resize((cfg.image.max_width, h), Image.LANCZOS)
    img.save(out_raw, "JPEG", quality=cfg.image.jpeg_quality)

    subtitled = Image.alpha_composite(img.convert("RGBA"), subtitle_overlay(cfg, img.size, sentence))
    subtitled.convert("RGB").save(out_scene, "JPEG", quality=cfg.image.jpeg_quality)


def subtitle_overlay(cfg: Config, size: tuple[int, int], sentence: str) -> Image.Image:
    """Transparent image of the given size with the line drawn as a bottom subtitle."""
    w, h = size
    font_size = max(18, round(h / 13))
    font = ImageFont.truetype(find_font(cfg), font_size)
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    # Full-width spaces are pauses; show them as line breaks if the line is long.
    text = sentence.replace("　", "\n") if len(sentence) > 22 else sentence
    lines = _wrap(draw, text, font, int(w * 0.9))
    line_h = round(font_size * 1.3)
    block_h = line_h * len(lines)
    top = h - block_h - round(h * 0.06)
    # Soft dark band behind the text so it stays readable on bright scenes.
    band_top = max(0, top - round(font_size * 0.6))
    for y in range(band_top, h):
        alpha = min(150, int(150 * (y - band_top) / max(1, font_size)))
        draw.line([(0, y), (w, y)], fill=(0, 0, 0, alpha))
    stroke = max(2, font_size // 12)
    for i, line in enumerate(lines):
        tw = draw.textlength(line, font=font)
        draw.text(((w - tw) / 2, top + i * line_h), line, font=font,
                  fill=(255, 255, 255, 255), stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
    return overlay
