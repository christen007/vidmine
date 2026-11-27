# Video mined cards: import spec for Kaeru

Format version: `vid-jp-card/1`

This describes what the video mining player (VidMine) produces, so Kaeru's Mine tab can import it next to Chrono Trigger cards. It is a sibling of `ct-jp-card/1`: **every lesson field has the same name, type and meaning**, so the card back Kaeru already renders for CT cards works unchanged. The differences are an audio clip, timing information, and a few fields that only make sense for video.

As with CT exports, all the analysis (readings, word breakdown, grammar, translations) is already in the file, so importing needs no Claude calls.

## What a video card looks like

- **Front:** `images.scene`, a frame from the moment the line is spoken, with the Japanese line drawn onto it as a subtitle. This plays the role of the CT screenshot with its text box. Play `audio` on the front or on reveal (a user setting is ideal).
- **Back:** the same panel as CT cards: sentence with furigana, words, grammar, meaning, official English, note, plus an audio replay button.
- **Optional listening mode:** `images.scene_original` (the same frame without text) plus `audio` on the front, sentence revealed on the back.

## How it's delivered

```
VID_Cards/
  cards.jsonl          UTF-8, one JSON object per line
  images/
    vid_<hash>_<start_ms>_scene.jpg
    vid_<hash>_<start_ms>_scene_raw.jpg
  audio/
    vid_<hash>_<start_ms>.mp3
```

Exports are named `VID_Cards_export_<date-time>.zip` and contain a top-level `VID_Cards/` folder. Media paths in each record are relative to `cards.jsonl`. An export normally contains only cards that are new or changed since the previous export; the user can re-export everything.

**Import by upserting on `id`**, exactly like CT cards: a known `id` means new content for an existing card (keep its review history); an unknown `id` means a new card. **Dispatch on `schema`**: `ct-jp-card/1` and `vid-jp-card/1` records can live in the same deck.

## Sample record

```json
{
  "schema": "vid-jp-card/1",
  "id": "vid-jp:9f2c41d07ab3e815:752340",
  "source": "embedded-subs",
  "mined_at": "2026-11-26T21:14:03",
  "location": "Frieren S01E03 @ 12:32",
  "speaker": "フリーレン",
  "speech_style": "standard",
  "sentence": "人間の寿命は短いってわかっていたのに…",
  "choices": [],
  "furigana": "人間[にんげん]の 寿命[じゅみょう]は 短い[みじかい]ってわかっていたのに…",
  "meaning": "Even though I knew human lives are short…",
  "official_english": "I knew human lifespans were short, and yet…",
  "english_source": "subtitle-track",
  "context_before": ["もう五十年も経ったんだね。"],
  "tokens": [
    {"surface": "人間", "reading": "にんげん", "dictionary_form": "人間", "gloss": "humans", "pos": "noun", "game_term": false},
    {"surface": "の", "reading": "", "dictionary_form": "の", "gloss": "(possessive)", "pos": "particle", "game_term": false},
    {"surface": "寿命", "reading": "じゅみょう", "dictionary_form": "寿命", "gloss": "lifespan", "pos": "noun", "game_term": false},
    {"surface": "は", "reading": "", "dictionary_form": "は", "gloss": "(topic)", "pos": "particle", "game_term": false},
    {"surface": "短い", "reading": "みじかい", "dictionary_form": "短い", "gloss": "short", "pos": "adj", "game_term": false},
    {"surface": "って", "reading": "", "dictionary_form": "って", "gloss": "(quoting: that…)", "pos": "particle", "game_term": false},
    {"surface": "わかっていた", "reading": "", "dictionary_form": "分かる", "gloss": "knew", "pos": "verb", "game_term": false},
    {"surface": "のに", "reading": "", "dictionary_form": "のに", "gloss": "even though", "pos": "conj", "game_term": false}
  ],
  "grammar": [
    {"id": "tte-quote", "pattern": "～って", "explanation": "Casual quotation marker, like と: 短いって = \"that (they) are short\"."},
    {"id": "te-ita", "pattern": "～ていた", "explanation": "Past continuing state: わかっていた, \"had known (all along)\"."},
    {"id": "noni", "pattern": "～のに", "explanation": "\"Even though…\", with a sense of regret or frustration."}
  ],
  "note": "The trailing … leaves the regret unspoken; the English subtitle adds \"and yet\" to carry it.",
  "images": {
    "card": null,
    "scene": "images/vid_9f2c41d07ab3e815_752340_scene.jpg",
    "scene_original": "images/vid_9f2c41d07ab3e815_752340_scene_raw.jpg"
  },
  "audio": "audio/vid_9f2c41d07ab3e815_752340.mp3",
  "media": {
    "title": "Frieren S01E03",
    "file_name": "[Group] Sousou no Frieren - 03 (1080p).mkv",
    "file_hash": "9f2c41d07ab3e815",
    "start_ms": 752340,
    "end_ms": 755910,
    "audio_padding_ms": 250
  }
}
```

## Field reference

Fields marked **same as CT** have exactly the meaning given in the `ct-jp-card/1` spec.

| Field | Type | Notes |
|---|---|---|
| `schema` | string | Always `vid-jp-card/1` for this version. |
| `id` | string | Stable unique ID: `vid-jp:<file_hash>:<start_ms>`. The hash comes from the video file's contents, not its name, so renaming or moving a file does not create duplicates. Re-mining the same line from the same subtitles gives the same `id`. |
| `source` | string | Where the sentence text came from: `embedded-subs` (a subtitle track inside the video file), `external-subs` (a subtitle file next to the video), `asr` (speech recognition by Whisper; **text may contain mishearings**, consider marking these cards). Planned: `screen-capture`. |
| `mined_at` | string | Same as CT: local time, ISO 8601 without timezone. |
| `location` | string | Show/episode and timestamp, e.g. `Frieren S01E03 @ 12:32`. Plays the role of CT's scene name. |
| `speaker` | string | Same as CT. Often `""` for video: filled only when the subtitles name the speaker (e.g. `（フリーレン）` in Japanese closed captions) or the line makes it unambiguous. |
| `speech_style` | string | Same values as CT: `standard`, `casual-feminine`, `child`, `archaic-formal`, `rough-masculine`, plus new `keigo` (honorific/humble business speech). Same rule: anything other than `standard`/`casual-feminine` is fine to recognize but shouldn't be drilled for production. |
| `sentence` | string | The line as the subtitles show it, without speaker labels. Multi-line subtitles are joined with a full-width space (`　`), the same pause marker CT uses. |
| `choices` | string[] | Always `[]`. Kept for compatibility. |
| `furigana` | string | Same as CT: Anki-style, reading covers the whole token. |
| `meaning` | string | Same as CT. |
| `official_english` | string | Same role as CT: the English subtitle track's text for the same moment, when the video has one. May be `""`. May be a fansub rather than an official translation; see `english_source`. |
| `english_source` | string | **New.** `subtitle-track` when `official_english` came from the file's English subtitles, `""` when there is none. |
| `context_before` | string[] | **New.** Up to two Japanese lines spoken just before this one, oldest first. Optional context for the back of the card. |
| `tokens` | object[] | Same as CT, including `game_term`, which here marks character names and invented in-world terms (always present on video cards). |
| `grammar` | object[] | Same as CT. **Grammar `id`s are shared with CT cards**: the miner is given every `id` already used (including the CT export) and reuses them, so one grammar index covers both. |
| `note` | string | Same as CT. For `asr` cards it may also flag a likely mishearing. |
| `images.scene` | string | Card front: a frame (JPEG, at most 1280 px wide) with the sentence drawn on it. |
| `images.scene_original` | string | The same frame without text. |
| `images.card` | null | Always `null`: Kaeru renders the card back from the data. |
| `audio` | string | **New.** MP3 of the line, with `media.audio_padding_ms` of extra audio before and after. |
| `media.title` | string | Show/episode title as the player reported it. |
| `media.file_name` | string | Video file name at mining time (informational only). |
| `media.file_hash` | string | 16 hex characters, same as in `id`. Groups cards by episode. |
| `media.start_ms`, `media.end_ms` | integer | When the line is on screen, in milliseconds from the start of the video. |
| `media.audio_padding_ms` | integer | Padding included in the audio clip on each side. |

## Notes for Kaeru's features

- **Everything in "Notes for Kaeru's features" of the CT spec applies unchanged**: JLPT matching on `dictionary_form`, skipping `game_term` tokens for difficulty, fill-in-the-blank drills from conjugated `verb`/`adj` tokens, showing standard spellings for kana-heavy words.
- **Audio:** MP3 plays everywhere. A replay button on both sides of the card, plus an optional auto-play, covers most use.
- **Listening drills:** video cards make a natural listening deck: front = `scene_original` + `audio`, back = full card.
- **Episode grouping:** `media.file_hash` (or `location` minus the timestamp) groups cards from the same episode, if Kaeru wants a per-show view.

## Compatibility promise

Within `vid-jp-card/1`, fields will only be added, never renamed or removed. A breaking change would get a new `schema` value.
