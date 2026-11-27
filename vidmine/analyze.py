"""Sentence analysis with Claude: word breakdown, readings, grammar, translation.

Produces the same lesson fields as the Chrono Trigger pipeline (ct-jp-card/1),
so Kaeru renders video cards with the same card back.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from .config import Config

API_URL = "https://api.anthropic.com/v1/messages"
POS = ["noun", "verb", "adj", "adv", "particle", "aux", "pron", "name", "expr", "conj", "suffix"]
STYLES = ["standard", "casual-feminine", "rough-masculine", "child", "archaic-formal", "keigo"]


class AnalysisError(RuntimeError):
    pass


SYSTEM = """You build sentence-mining flashcards for an English-speaking learner of Japanese. \
The learner mined one subtitle line from a Japanese TV show, anime or film. Break it down \
by calling record_card. Your output is rendered directly as the back of a flashcard, so be \
accurate, concise and natural.

Rules for each field:
- tokens: the sentence split into words, in order, covering every word. Omit punctuation \
(、。！？…「」 etc.) and spaces. Concatenating the surfaces must reproduce the sentence \
with punctuation and spaces removed. Keep useful chunks together the way a learner thinks \
of them: a conjugated verb with its endings is one token (わかっていた, 寝付けなかった), and \
sentence-final endings like んでしょ or んじゃないわよ are one token.
- tokens[].surface: exactly as written in the sentence.
- tokens[].reading: hiragana reading of the whole surface, including okurigana \
(回ろう -> まわろう). Empty string when the surface contains no kanji.
- tokens[].dictionary_form: the lemma in its standard dictionary spelling, even when the \
line writes it in kana (いっしょに -> 一緒に, わかって -> 分かる). Empty string for \
multi-word endings with no single lemma.
- tokens[].gloss: a short English meaning in this context (a few words).
- tokens[].pos: one of the allowed values. Use "aux" for auxiliary endings like でしょ, \
"expr" for set phrases, "name" for personal and place names.
- tokens[].game_term: true for character names, place names and invented in-world terms \
that have no ordinary dictionary entry; false otherwise.
- grammar: the 1-5 grammar points a learner should take away from this line. Each has a \
stable slug id, a display pattern (e.g. ～ても) and a one or two sentence explanation \
that uses the words of this line as its example. When a point in KNOWN_GRAMMAR_IDS \
applies, reuse its id exactly. New ids are short lowercase hyphenated slugs \
(te-cause, nasai, tte-quote).
- meaning: a natural English translation of the line. Use the context lines to resolve \
who and what is being talked about, but translate only this line.
- speaker: the speaker's name only if the line or captions make it unambiguous; \
otherwise an empty string. Never guess.
- speech_style: "standard" for neutral or polite speech; "casual-feminine", \
"rough-masculine", "child", "archaic-formal" (samurai/old-fashioned), or "keigo" \
(honorific/humble business speech) when the line is clearly marked as such.
- note: one sentence of extra context worth knowing, or an empty string. Good notes: words \
written in kana whose usual spelling uses kanji; where the English subtitle departs from \
the Japanese meaning; slang or dialect. If SOURCE is asr the text came from speech \
recognition: if a word looks misheard, say so here and suggest what was probably said."""

TOOL = {
    "name": "record_card",
    "description": "Record the analysis of the mined line.",
    "input_schema": {
        "type": "object",
        "properties": {
            "speaker": {"type": "string"},
            "speech_style": {"type": "string", "enum": STYLES},
            "meaning": {"type": "string"},
            "note": {"type": "string"},
            "tokens": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "surface": {"type": "string"},
                        "reading": {"type": "string"},
                        "dictionary_form": {"type": "string"},
                        "gloss": {"type": "string"},
                        "pos": {"type": "string", "enum": POS},
                        "game_term": {"type": "boolean"},
                    },
                    "required": ["surface", "reading", "dictionary_form", "gloss", "pos", "game_term"],
                },
            },
            "grammar": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "pattern": {"type": "string"},
                        "explanation": {"type": "string"},
                    },
                    "required": ["id", "pattern", "explanation"],
                },
            },
        },
        "required": ["speaker", "speech_style", "meaning", "note", "tokens", "grammar"],
    },
}


def build_user_message(card: dict, known: dict[str, str]) -> str:
    payload = {
        "SENTENCE": card["sentence"],
        "SPEAKER_FROM_CAPTIONS": card.get("speaker", ""),
        "CONTEXT_BEFORE": card.get("context_before", []),
        "ENGLISH_SUBTITLE": card.get("official_english", ""),
        "SHOW": card.get("media", {}).get("title", ""),
        "SOURCE": card.get("source", ""),
    }
    known_lines = "\n".join(f"{k} = {v}" for k, v in sorted(known.items())) or "(none yet)"
    return (json.dumps(payload, ensure_ascii=False, indent=1)
            + "\n\nKNOWN_GRAMMAR_IDS:\n" + known_lines)


def fake_result(user_message: str) -> dict:
    """Offline stand-in used by the app's self-test (VIDMINE_FAKE_ANALYSIS=1)."""
    sentence = json.loads(user_message.split("\n\nKNOWN_GRAMMAR_IDS")[0])["SENTENCE"]
    words = "".join(c for c in sentence if c.isalnum())
    return {"speaker": "", "speech_style": "standard", "meaning": "(self-test)", "note": "",
            "tokens": [{"surface": words, "reading": "", "dictionary_form": "", "gloss": "test",
                        "pos": "expr", "game_term": False}],
            "grammar": [{"id": "self-test", "pattern": "～", "explanation": "Self-test."}]}


def clean_key(key: str) -> str:
    """Tidy a pasted key: whitespace, quotes, a leading 'Bearer ' or 'x-api-key:'."""
    key = key.strip().strip('"\'').strip()
    for prefix in ("Bearer ", "x-api-key:", "ANTHROPIC_API_KEY="):
        if key.lower().startswith(prefix.lower()):
            key = key[len(prefix):].strip().strip('"\'')
    return "".join(key.split())


def api_headers(key: str, workspace_id: str = "") -> dict:
    h = {"authorization": f"Bearer {key}", "anthropic-version": "2023-06-01",
         "content-type": "application/json"}
    if workspace_id:
        h["anthropic-workspace-id"] = workspace_id
    return h


def _error_message(e: urllib.error.HTTPError) -> str:
    try:
        return json.loads(e.read().decode("utf-8", "replace"))["error"]["message"]
    except Exception:
        return f"HTTP {e.code}"


def check_key(key: str, workspace_id: str = "", model: str = "claude-sonnet-5-5") -> tuple[bool | None, str]:
    """(True, '') if Anthropic accepts the key, (False, why) if rejected, (None, why) if unreachable.
    Uses the free token-counting endpoint, which is authorized exactly like a real request."""
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": "こんにちは"}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages/count_tokens", data=body,
                                 headers=api_headers(key, workspace_id), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15):
            return True, ""
    except urllib.error.HTTPError as e:
        msg = _error_message(e)
        if e.code in (400, 401, 403, 404):
            return False, f"Anthropic rejected this key: {msg}"
        return None, f"Couldn't check the key right now ({msg})."
    except Exception as e:
        return None, f"Couldn't reach Anthropic to check the key ({e})."


def list_workspaces(key: str) -> list[tuple[str, str]]:
    """(id, name) of the workspaces a personal key can use, Default Workspace first.
    Empty if the key isn't allowed to list them."""
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/organizations/workspaces?include_default=true&limit=100",
        headers=api_headers(key))
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8")).get("data", [])
    except Exception:
        return []
    out = [(w["id"], w.get("name") or w["id"]) for w in data if w.get("id") and not w.get("archived_at")]
    out.sort(key=lambda w: 0 if "default" in w[1].lower() else 1)
    return out


def find_working_setup(key: str, workspace_id: str = "", model: str = "claude-sonnet-5-5"
                       ) -> tuple[bool | None, str, str]:
    """Check a key; if it needs a workspace, find one it works with.
    Returns (ok, workspace_id_to_use, message)."""
    ok, why = check_key(key, workspace_id, model)
    if ok is not False:
        return ok, workspace_id, why
    for ws_id, name in list_workspaces(key):
        if ws_id != workspace_id and check_key(key, ws_id, model)[0]:
            return True, ws_id, f"Using workspace “{name}”."
    return False, workspace_id, why


def call_claude(cfg: Config, user_message: str) -> dict:
    if os.environ.get("VIDMINE_FAKE_ANALYSIS"):
        return fake_result(user_message)
    key = cfg.claude.resolved_key()
    if not key:
        raise AnalysisError("No Claude API key: set ANTHROPIC_API_KEY or [claude] api_key in config.toml")
    body = json.dumps({
        "model": cfg.claude.model,
        "max_tokens": cfg.claude.max_tokens,
        "system": SYSTEM,
        "tools": [TOOL],
        "tool_choice": {"type": "tool", "name": "record_card"},
        "messages": [{"role": "user", "content": user_message}],
    }).encode("utf-8")
    headers = api_headers(key, cfg.claude.workspace_id)
    last = ""
    for attempt in range(4):
        req = urllib.request.Request(API_URL, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            for block in data.get("content", []):
                if block.get("type") == "tool_use":
                    return block["input"]
            raise AnalysisError("Claude returned no card data")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            last = f"HTTP {e.code}: {detail[:300]}"
            if e.code == 401 or (e.code == 400 and "workspace" in detail.lower()):
                try:
                    msg = json.loads(detail)["error"]["message"]
                except Exception:
                    msg = detail[:200]
                raise AnalysisError(f"Your Claude API key was rejected ({msg}). Open Settings and "
                                    "click Save: VidMine re-checks the key and finds your workspace. "
                                    "Then use Retry analysis.")
            if e.code == 400 and "credit balance" in detail.lower():
                raise AnalysisError("Your Claude API account is out of credits. Add credits at "
                                    "platform.claude.com/settings/billing, then use Retry analysis.")
            if e.code not in (429, 500, 502, 503, 529):
                break
        except (urllib.error.URLError, TimeoutError) as e:
            last = f"Network error: {e}"
        time.sleep(2 * (attempt + 1))
    raise AnalysisError(last or "Claude request failed")


# ---- post-processing --------------------------------------------------------

def has_kanji(s: str) -> bool:
    return any("一" <= c <= "鿿" or "㐀" <= c <= "䶿" or c in "々〆ヶ" for c in s)


def to_hiragana(s: str) -> str:
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in s)


def build_furigana(sentence: str, tokens: list[dict]) -> str:
    """Anki-style furigana: ' 漢字[よみ]' with the reading covering the whole token."""
    out, cur = [], 0
    for t in tokens:
        surf = t["surface"]
        idx = sentence.find(surf, cur) if surf else -1
        if idx < 0:
            continue
        out.append(sentence[cur:idx])
        if t.get("reading"):
            out.append(f" {surf}[{t['reading']}]")
        else:
            out.append(surf)
        cur = idx + len(surf)
    out.append(sentence[cur:])
    return "".join(out).lstrip(" ")


def coverage_problem(sentence: str, tokens: list[dict]) -> str:
    """Return a warning if the tokens don't reproduce the sentence's words in order."""
    cur, missing = 0, []
    for t in tokens:
        idx = sentence.find(t["surface"], cur) if t["surface"] else -1
        if idx < 0:
            missing.append(t["surface"])
            continue
        gap = sentence[cur:idx]
        if any(c.isalnum() for c in gap):
            missing.append(f"gap:{gap}")
        cur = idx + len(t["surface"])
    if any(c.isalnum() for c in sentence[cur:]):
        missing.append(f"gap:{sentence[cur:]}")
    return ", ".join(missing)


def apply_analysis(card: dict, result: dict) -> list[str]:
    """Merge Claude's result into the card. Returns warnings."""
    warnings = []
    tokens = []
    for t in result.get("tokens", []):
        surface = t.get("surface", "")
        reading = to_hiragana(t.get("reading", "")) if has_kanji(surface) else ""
        if has_kanji(surface) and not reading:
            warnings.append(f"no reading for {surface}")
        tokens.append({
            "surface": surface,
            "reading": reading,
            "dictionary_form": t.get("dictionary_form", ""),
            "gloss": t.get("gloss", ""),
            "pos": t.get("pos") if t.get("pos") in POS else "expr",
            "game_term": bool(t.get("game_term", False)),
        })
    problem = coverage_problem(card["sentence"], tokens)
    if problem:
        warnings.append(f"tokens don't cover sentence: {problem}")
    card["tokens"] = tokens
    card["grammar"] = [{"id": g["id"], "pattern": g["pattern"], "explanation": g["explanation"]}
                       for g in result.get("grammar", []) if g.get("id")]
    card["furigana"] = build_furigana(card["sentence"], tokens)
    card["meaning"] = result.get("meaning", "")
    card["note"] = result.get("note", "")
    style = result.get("speech_style", "standard")
    card["speech_style"] = style if style in STYLES else "standard"
    if not card.get("speaker"):
        card["speaker"] = result.get("speaker", "")
    return warnings
