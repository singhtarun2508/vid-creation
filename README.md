# 🥕 Animated Vegetable Love Story Pipeline

Generates a short animated children's video with AI-written story,
text-to-speech voices, and programmatic 2D character animation.
**100% free to run** (Claude API is optional — a demo story is built in).

---

## What You Get

A ~35–55 second MP4 video with:
- Animated title card (characters bounce, title slides in)
- 5 dialogue scenes — speaking character bounces faster, mouth opens/closes with audio amplitude, speech bubble pops in
- Final moral card with floating hearts and sparkles
- Short white-flash transitions between scenes

---

## Quick Start

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

Or manually:

```bash
pip install moviepy Pillow numpy scipy edge-tts anthropic \
            google-api-python-client google-auth-oauthlib
```

> **Windows note:** MoviePy needs FFmpeg. Download from https://ffmpeg.org/download.html
> and add to PATH, or install via `pip install imageio[ffmpeg]`.

> **macOS note:** `brew install ffmpeg` is the easiest path.

> **Linux note:** `sudo apt install ffmpeg` (Debian/Ubuntu).

---

### 2. Configure pipeline.py

Open `pipeline.py` and edit the CONFIG section at the top:

```python
ANTHROPIC_API_KEY   = "YOUR_ANTHROPIC_API_KEY"   # from console.anthropic.com
GOOGLE_DRIVE_FOLDER = ""                          # Drive folder ID (optional)
UPLOAD_TO_DRIVE     = False                       # set True to enable
BG_MUSIC_PATH       = ""                          # path to an MP3 (optional)
```

**No API key?** Leave it as-is. The pipeline falls back to a built-in
demo story with Carrot and Potato, so you can test the animation
without any API credentials.

---

### 3. Run

```bash
python pipeline.py
```

Output video saved to `output/<veg1>_<veg2>_story.mp4`.

---

## Feature Breakdown

| Feature | Required package | Fallback if missing |
|---|---|---|
| Unique AI stories | `anthropic` | Built-in demo story |
| Real TTS voices | `edge-tts` | Silent placeholder audio |
| Mouth amplitude sync | `scipy` + `ffmpeg` | Flat 50% amplitude |
| Google Drive upload | `google-*` | Skipped, video saved locally |
| Background music | any MP3 + `moviepy` | Silent background |

---

## Google Drive Setup (optional)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → Enable **Google Drive API**
3. Create OAuth 2.0 credentials (Desktop app) → Download as `credentials.json`
4. Place `credentials.json` in the same folder as `pipeline.py`
5. Set `UPLOAD_TO_DRIVE = True` and paste your folder ID in `GOOGLE_DRIVE_FOLDER`

First run will open a browser for OAuth consent. Token is saved to `token.pickle`
for subsequent runs.

---

## Supported Vegetables

potato · carrot · broccoli · tomato · onion · eggplant · pumpkin · corn ·
cucumber · pepper · zucchini · radish

Each has a unique colour palette and custom topping drawing.

---

## Optional Upgrades (all free)

- **Background music** — drop any royalty-free MP3 into the folder and set `BG_MUSIC_PATH`
- **New vegetables** — add an entry to `VEG_COLORS` in `pipeline.py`
- **Different voices** — change `VOICE_1` / `VOICE_2` to any [Edge TTS voice](https://speech.microsoft.com/portal/voicegallery)
- **Longer stories** — increase `max_tokens` and the dialogue count in the prompt

---

## File Structure

```
veggie_story/
├── pipeline.py          ← Main script (all-in-one)
├── requirements.txt     ← Python dependencies
├── README.md            ← This file
├── credentials.json     ← (optional) Google OAuth credentials
├── audio/               ← Generated MP3 files per dialogue line
└── output/              ← Final MP4 videos
```
