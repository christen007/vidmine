# VidMine

A video player for sentence mining Japanese. It turns lines from anime, dramas and films into cards for Kaeru, with audio, a screenshot, and a full word and grammar breakdown.

## Getting started

1. Unzip `VidMine-win64.zip` somewhere permanent, e.g. `Documents\VidMine App`.
2. Open the folder and double-click **VidMine.exe**.
   - The first time, Windows may show "Windows protected your PC", because the app isn't signed by a publisher. Click **More info**, then **Run anyway**.
3. Click **Settings** and paste your **Claude API key**. Claude uses it to break each line down into words and grammar.
4. Click **Open video…**, or drag a video file onto the window.

## Mining

The right-hand **Lines** panel lists every Japanese subtitle line in the video, and the current one is highlighted as you watch.

- Press **M** (or **⛏ Mine line**) to turn the current line into a card. Mining takes a few seconds and happens in the background, so keep watching.
- Right-click any line in the list to mine it, or double-click it to jump to it.
- The **Cards** tab shows what you've mined, with a preview of each card.
- Click **Export for Kaeru** to save new cards as a zip, then import that zip in Kaeru's **Mine** tab.

| Key | Action |
|---|---|
| Space | Play / pause |
| ← / → | Back / forward 5 seconds |
| ↑ / ↓ | Previous / next line |
| R | Replay the current line |
| M | Mine the current line |
| E | Show / hide the English subtitle line |
| F / Esc | Full screen / exit full screen |

## Japanese subtitles

VidMine needs a Japanese subtitle track that it can read as text:

- **Inside the video:** many `.mkv` files include one. It's picked automatically, and you can switch tracks under the video.
- **A separate file:** put it next to the video with the same name plus `.ja`, e.g. `Episode 03.mkv` and `Episode 03.ja.srt`. `.srt`, `.ass` and `.vtt` files all work.

If the video also has an English track, its line is saved on the card as the official English.

## Where things are kept

- **Cards, images and audio:** `Documents\VidMine`. You can change this in Settings.
- **Exports:** `Documents\VidMine\exports`
- **Settings:** `%APPDATA%\VidMine\settings.json`
- **Error log:** `%APPDATA%\VidMine\vidmine.log`

## Coming next

- Speech recognition (Whisper) for videos without Japanese subtitles
- Screen recording, for content you can't open as a file
- Reading image-based subtitles (PGS/DVD)

---

The card format is documented in `KAERU_VIDEO_IMPORT_SPEC.md`. Each push to `main` builds the app on GitHub and publishes it under **Releases**.
