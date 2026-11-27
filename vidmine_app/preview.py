"""HTML preview of a mined card, styled after Kaeru's card back."""
from __future__ import annotations

import html
from pathlib import Path

POS_COLORS = {
    "noun": "#5b8def", "verb": "#ee7a52", "adj": "#e0b341", "adv": "#e8689a",
    "particle": "#9aa0ad", "aux": "#b483e0", "expr": "#4fc3a1", "conj": "#a99f93",
    "pron": "#5bb5d6", "name": "#d6a35b", "suffix": "#9aa0ad",
}


def _e(s) -> str:
    return html.escape(str(s or ""))


def card_html(card: dict, library_root: Path, width: int = 420) -> str:
    meta = card.get("_vidmine", {})
    status = meta.get("status", "pending")
    parts = ['<div style="font-family:\'Segoe UI\',\'Yu Gothic UI\',sans-serif;">']
    scene = card.get("images", {}).get("scene")
    if scene:
        uri = (library_root / scene).resolve().as_uri()
        parts.append(f'<img src="{uri}" width="{width}"><br>')
    head = _e(card.get("speaker") or "")
    parts.append(f'<p style="color:#8890a6;font-size:11px;">{head}{" · " if head else ""}{_e(card.get("location"))}</p>')
    if status == "failed":
        parts.append(f'<p style="color:#e06c6c;"><b>Analysis failed:</b> {_e(meta.get("error"))}<br>'
                     'Use “Retry analysis” once the problem is fixed.</p>')
    elif status != "ready":
        parts.append('<p style="color:#e0b341;">Analyzing…</p>')

    tokens = card.get("tokens") or []
    if tokens:
        row = []
        for t in tokens:
            color = POS_COLORS.get(t.get("pos"), "#9aa0ad")
            reading = f'<br><span style="font-size:10px;color:#8890a6;">{_e(t["reading"])}</span>' if t.get("reading") else ""
            row.append(f'<span style="font-size:22px;border-bottom:3px solid {color};">{_e(t["surface"])}</span>'
                       f'{reading}')
        parts.append('<table cellspacing="6"><tr>' + "".join(f'<td align="center" valign="bottom">{c}</td>' for c in row) + "</tr></table>")
    else:
        parts.append(f'<p style="font-size:22px;">{_e(card.get("sentence"))}</p>')

    if card.get("meaning"):
        parts.append(f'<p><b style="color:#8890a6;font-size:11px;">MEANING</b><br>{_e(card["meaning"])}</p>')
    if card.get("official_english"):
        parts.append(f'<p><b style="color:#8890a6;font-size:11px;">ENGLISH SUBTITLE</b><br>{_e(card["official_english"])}</p>')
    if tokens:
        parts.append('<p><b style="color:#8890a6;font-size:11px;">WORDS</b></p><table cellspacing="2">')
        for t in tokens:
            color = POS_COLORS.get(t.get("pos"), "#9aa0ad")
            dict_form = t.get("dictionary_form") or ""
            extra = f' ← {_e(dict_form)}' if dict_form and dict_form != t["surface"] else ""
            parts.append(f'<tr><td style="color:{color};font-size:10px;">{_e(t.get("pos","")).upper()}</td>'
                         f'<td><b>{_e(t["surface"])}</b>{extra}</td><td>{_e(t.get("gloss"))}</td></tr>')
        parts.append("</table>")
    for g in card.get("grammar") or []:
        parts.append(f'<p><b style="color:#e0b341;">{_e(g["pattern"])}</b><br>{_e(g["explanation"])}</p>')
    if card.get("note"):
        parts.append(f'<p style="background:#2a2f45;padding:6px;">{_e(card["note"])}</p>')
    parts.append("</div>")
    return "".join(parts)
