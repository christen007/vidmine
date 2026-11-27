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
| Z / X | Shift subtitles 0.1 s earlier / later |
| F / Esc | Full screen / exit full screen |

## Japanese subtitles

VidMine gets the Japanese text from one of three places:

- **Inside the video:** many `.mkv` files include a Japanese track. It's picked automatically, and you can switch tracks under the video.
- **A separate file:** put it next to the video with the same name plus `.ja`, e.g. `Episode 03.mkv` and `Episode 03.ja.srt`. `.srt`, `.ass` and `.vtt` files all work. [Jimaku](https://jimaku.cc) has Japanese subtitles for many anime and dramas.
- **Whisper:** for any video with no Japanese subtitles, click **🎙 Transcribe audio**. Whisper listens to the Japanese audio and writes Japanese subtitles (it transcribes; it doesn't translate). On an NVIDIA graphics card, a 24-minute episode takes a few minutes, and you can keep watching while it works.
  - The first time, it downloads the Whisper model (about 3 GB for the most accurate one) and, on NVIDIA PCs, NVIDIA's GPU libraries. Downloads are saved, so this only happens once.
  - The transcript is saved next to the video as `<name>.ja.whisper.srt` and loads automatically next time.
  - Whisper is very good at Japanese but can occasionally mishear a word. Cards mined from it are marked as speech recognition, and Claude flags words that look misheard.

If the video also has an English track, its line is saved on the card as the official English.

**Subtitles out of sync?** Downloaded subtitle files are sometimes made for a slightly different release. Adjust **Subtitle timing** under the video, or press **Z** / **X** to shift them 0.1 s earlier or later.

## Where things are kept

- **Cards, images and audio:** `Documents\VidMine`. You can change this in Settings.
- **Exports:** `Documents\VidMine\exports`
- **Settings:** `%APPDATA%\VidMine\settings.json`
- **Whisper model and GPU libraries:** `%LOCALAPPDATA%\VidMine`
- **Error log:** `%APPDATA%\VidMine\vidmine.log`

## Coming next

- Screen recording, for content you can't open as a file
- Reading image-based subtitles (PGS/DVD)

---

The card format is documented in `KAERU_VIDEO_IMPORT_SPEC.md`. Each push to `main` builds the app on GitHub and publishes it under **Releases**.
