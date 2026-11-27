"""Render a card's lesson panel as an image, in the style of the Chrono Trigger cards:
sentence with furigana and part-of-speech underlines, word tiles, grammar, meaning,
English and note. Used for the bottom half of card videos."""
from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .config import Config, bundled

BG = (16, 21, 46)
TILE = (24, 31, 64)
NOTE_BG = (38, 32, 70)
NOTE_TEXT = (217, 202, 252)
LABEL = (138, 147, 184)
TEXT = (240, 242, 250)
SOFT = (200, 205, 224)
DIM = (163, 172, 201)
YELLOW = (255, 213, 79)

POS_COLORS = {
    "adv": "#f48fb1", "noun": "#6cb6ff", "verb": "#ff8a65", "adj": "#81c784", "aux": "#ce93d8",
    "expr": "#80cbc4", "particle": "#b0bec5", "conj": "#bcaaa4", "pron": "#4dd0e1",
    "name": "#ffcc80", "suffix": "#b0bec5",
}
POS_LABELS = {
    "adv": "ADVERB", "noun": "NOUN", "verb": "VERB", "adj": "ADJECTIVE", "aux": "AUXILIARY",
    "expr": "EXPRESSION", "particle": "PARTICLE", "conj": "CONJUNCTION", "pron": "PRONOUN",
    "name": "NAME", "suffix": "SUFFIX",
}
NO_LINE_START = set("、。，．！？!?）」』】〕〉》ーっゃゅょぁぃぅぇぉッャュョァィゥェォ…‥・々,.;:)]")

FONT_SETS = [  # (regular, bold)
    (lambda: bundled("NotoSansJP-Regular.otf"), lambda: bundled("NotoSansJP-Bold.otf")),
    (lambda: "C:/Windows/Fonts/YuGothM.ttc", lambda: "C:/Windows/Fonts/YuGothB.ttc"),
    (lambda: "C:/Windows/Fonts/meiryo.ttc", lambda: "C:/Windows/Fonts/meiryob.ttc"),
    (lambda: "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
     lambda: "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
]


def _hex(c: str) -> tuple[int, int, int]:
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


class Fonts:
    def __init__(self, cfg: Config | None = None):
        reg = bold = None
        for r, b in FONT_SETS:
            rp, bp = r(), b()
            if rp and Path(rp).exists():
                reg = rp
                bold = bp if bp and Path(bp).exists() else rp
                break
        if reg is None:
            fallback = (cfg.image.font if cfg and cfg.image.font else None) or bundled("NotoSansJP-Bold.otf")
            if not fallback:
                raise RuntimeError("No Japanese font found for card videos")
            reg = bold = fallback
        self.reg, self.bold = reg, bold
        self._cache: dict = {}

    def get(self, size: int, bold: bool = False):
        key = (size, bold)
        if key not in self._cache:
            self._cache[key] = ImageFont.truetype(self.bold if bold else self.reg, size)
        return self._cache[key]


def wrap(draw: ImageDraw.ImageDraw, text: str, font, width: int) -> list[str]:
    """Wrap mixed English/Japanese: Latin words stay whole, Japanese breaks per character."""
    pieces = re.findall(r"[A-Za-z0-9'’\-.,!?;:\"()\[\]/&%$#@+=*_~]+\s*|\s+|.", text.replace("\n", " "))
    lines, cur = [], ""
    for p in pieces:
        if cur and draw.textlength(cur + p.rstrip(), font=font) > width and p[0] not in NO_LINE_START:
            lines.append(cur.rstrip())
            cur = p.lstrip()
        else:
            cur += p
    if cur.strip():
        lines.append(cur.rstrip())
    return lines


def _segments(sentence: str, tokens: list[dict]) -> list[tuple[str, dict | None]]:
    """Split the sentence into token segments and the punctuation between them."""
    segs, cur = [], 0
    for t in tokens:
        surf = t.get("surface", "")
        idx = sentence.find(surf, cur) if surf else -1
        if idx < 0:
            continue
        if idx > cur:
            segs.append((sentence[cur:idx], None))
        segs.append((surf, t))
        cur = idx + len(surf)
    if cur < len(sentence):
        segs.append((sentence[cur:], None))
    return segs or [(sentence, None)]


def render_panel(card: dict, fonts: Fonts, width: int = 1024, english_label: str = "ENGLISH SUBTITLES") -> Image.Image:
    M = 48
    inner = width - 2 * M
    # Draw on a tall canvas, then crop to the used height.
    img = Image.new("RGB", (width, 6000), BG)
    d = ImageDraw.Draw(img)
    y = 40

    # Header: speaker left, location right
    loc = card.get("location", "")
    f_loc = fonts.get(14)
    if loc:
        d.text((width - M - d.textlength(loc, font=f_loc), y + 4), loc, font=f_loc, fill=LABEL)
    if card.get("speaker"):
        d.text((M, y), card["speaker"], font=fonts.get(19, True), fill=TEXT)
    y += 44

    def label(text: str):
        nonlocal y
        d.text((M, y), text, font=fonts.get(13), fill=LABEL)
        y += 28

    # Sentence with furigana and underlines
    label("SENTENCE")
    f_main, f_furi = fonts.get(38), fonts.get(16)
    furi_h, main_h = 22, 50
    line_h = furi_h + main_h + 22
    x = M
    y += 4
    for text, tok in _segments(card.get("sentence", ""), card.get("tokens") or []):
        text = text.replace("　", " ")
        w = d.textlength(text, font=f_main)
        gap = 9 if tok else 1
        if x > M and x + w > M + inner:
            x = M
            y += line_h
        if tok and tok.get("reading"):
            fw = d.textlength(tok["reading"], font=f_furi)
            d.text((x + (w - fw) / 2, y), tok["reading"], font=f_furi, fill=DIM)
        d.text((x, y + furi_h), text, font=f_main, fill=TEXT)
        if tok:
            color = _hex(POS_COLORS.get(tok.get("pos"), "#b0bec5"))
            uy = y + furi_h + main_h + 6
            d.rounded_rectangle([x, uy, x + w, uy + 4], radius=2, fill=color)
        x += w + gap
    y += line_h + 18

    # Word tiles
    tokens = card.get("tokens") or []
    if tokens:
        label("WORDS")
        f_pos, f_surf, f_read, f_gloss = fonts.get(11, True), fonts.get(26, True), fonts.get(13), fonts.get(14)
        tile_h, pad, gap = 112, 16, 10
        x = M
        for t in tokens:
            gloss = t.get("gloss", "")
            while gloss and d.textlength(gloss, font=f_gloss) > 330:
                gloss = gloss[:-2].rstrip() + "…"
            posl = POS_LABELS.get(t.get("pos"), (t.get("pos") or "").upper())
            w = max(d.textlength(t["surface"], font=f_surf), d.textlength(gloss, font=f_gloss),
                    d.textlength(posl, font=f_pos), d.textlength(t.get("reading", ""), font=f_read))
            w = int(max(w + 2 * pad + 4, 96))
            if x > M and x + w > M + inner:
                x = M
                y += tile_h + 12
            color = _hex(POS_COLORS.get(t.get("pos"), "#b0bec5"))
            d.rounded_rectangle([x, y, x + w, y + tile_h], radius=8, fill=TILE)
            d.rounded_rectangle([x, y, x + 4, y + tile_h], radius=2, fill=color)
            tx = x + 4 + pad
            d.text((tx, y + 12), posl, font=f_pos, fill=color)
            d.text((tx, y + 28), t["surface"], font=f_surf, fill=TEXT)
            if t.get("reading"):
                d.text((tx, y + 64), t["reading"], font=f_read, fill=DIM)
            d.text((tx, y + 84), gloss, font=f_gloss, fill=SOFT)
            x += w + gap
        y += tile_h + 30

    # Grammar
    grammar = card.get("grammar") or []
    if grammar:
        label("GRAMMAR")
        f_pat, f_exp = fonts.get(19, True), fonts.get(16)
        for g in grammar:
            lines = wrap(d, g.get("explanation", ""), f_exp, inner - 40)
            h = 18 + 28 + 24 * len(lines) + 14
            d.rounded_rectangle([M, y, M + inner, y + h], radius=10, fill=TILE)
            d.text((M + 20, y + 14), g.get("pattern", ""), font=f_pat, fill=YELLOW)
            for i, line in enumerate(lines):
                d.text((M + 20, y + 46 + 24 * i), line, font=f_exp, fill=TEXT)
            y += h + 10
        y += 20

    def paragraph(title: str, text: str, size: int, color):
        nonlocal y
        if not text:
            return
        label(title)
        f = fonts.get(size)
        for line in wrap(d, text, f, inner):
            d.text((M, y), line, font=f, fill=color)
            y += int(size * 1.5)
        y += 22

    paragraph("MEANING", card.get("meaning", ""), 22, TEXT)
    paragraph(english_label, card.get("official_english", ""), 18, DIM)

    if card.get("note"):
        f = fonts.get(15)
        lines = wrap(d, card["note"], f, inner - 40)
        h = 16 + 23 * len(lines) + 14
        d.rounded_rectangle([M, y, M + inner, y + h], radius=10, fill=NOTE_BG)
        for i, line in enumerate(lines):
            d.text((M + 20, y + 15 + 23 * i), line, font=f, fill=NOTE_TEXT)
        y += h + 10

    y += 30
    return img.crop((0, 0, width, y + (y % 2)))
