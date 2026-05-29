"""
🥕 Animated Vegetable Love Story Pipeline  (Reel Edition v5)
=============================================================
Portrait 720×1280  |  No title card  |  No flash transitions
Moral text at top of final scene  |  JSON metadata alongside video

Changes in v5:
- Switched from deprecated google.generativeai → google.genai (new SDK)
- Fixed story/metadata generation (was silently falling back to demo)
- Audio generation retries up to 3 times per line
- Video assembly retries up to 3 times
- Better error logging throughout
"""

import os
import json
import asyncio
import random
import subprocess
import math
import struct
import wave
import time
import numpy as np
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

# ── Optional imports ──────────────────────────────────────────────────────────
try:
    from google import genai as google_genai
    from google.genai import types as genai_types
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False
    print("  ⚠️  google-genai not installed. Run: pip install google-genai")

try:
    import edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False

try:
    from moviepy.editor import (
        AudioFileClip, ImageSequenceClip, concatenate_videoclips,
        CompositeAudioClip,
    )
    HAS_MOVIEPY = True
except ImportError:
    HAS_MOVIEPY = False

try:
    from scipy.io import wavfile
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG  — edit before running
# ─────────────────────────────────────────────────────────────────────────────
GEMINI_API_KEY        = os.environ.get("GEMINI_API_KEY", "")
GOOGLE_DRIVE_FOLDER   = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "")
METADATA_DRIVE_FOLDER = os.environ.get("METADATA_DRIVE_FOLDER_ID", "")
UPLOAD_TO_DRIVE       = os.environ.get("UPLOAD_TO_DRIVE", "false").lower() == "true"
BG_MUSIC_PATH         = os.environ.get("BG_MUSIC_PATH", "")
OUTPUT_DIR            = "output"
METADATA_DIR          = "metadata"
AUDIO_DIR             = "audio"

W, H = 720, 1280   # Portrait / reel
FPS = 24

VOICE_1 = "en-US-AriaNeural"
VOICE_2 = "en-US-GuyNeural"

GEMINI_MODEL = "gemini-2.5-flash"

MAX_RETRIES = 3   # retries for audio lines and video assembly

# ─────────────────────────────────────────────────────────────────────────────
# GEMINI HELPER  (google.genai — new SDK)
# ─────────────────────────────────────────────────────────────────────────────
def _gemini(prompt: str, max_tokens: int = 800) -> str:
    """Call Gemini via the new google.genai SDK and return the text response."""
    if not HAS_GEMINI:
        raise RuntimeError("google-genai package not installed.")

    client = google_genai.Client(api_key=GEMINI_API_KEY)
    cfg    = genai_types.GenerateContentConfig(
        max_output_tokens=max_tokens,
        temperature=0.9,
    )
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=cfg,
    )
    return response.text.strip()


# ─────────────────────────────────────────────────────────────────────────────
# STORY GENERATION
# ─────────────────────────────────────────────────────────────────────────────
VEGETABLES = [
    "potato", "carrot", "broccoli", "tomato",
    "onion", "eggplant", "pumpkin", "corn",
    "cucumber", "pepper", "zucchini", "radish",
]

DEMO_STORY = {
    "veg1": "carrot",
    "veg2": "potato",
    "dialogues": [
        "CARROT: Oh Potato, your golden eyes sparkle like the autumn sun!",
        "POTATO: And your bright orange glow warms my heart every morning, dear Carrot.",
        "CARROT: Together in this garden, nothing feels impossible.",
        "POTATO: Let us grow side by side forever, roots intertwined.",
        "CARROT: No storm or frost could ever keep us apart, my love.",
    ],
    "moral": "True love grows stronger when you stand by each other through every season.",
}


def generate_story() -> dict:
    if not HAS_GEMINI:
        print("  ⚠️  google-genai not available — using built-in demo story.\n")
        return DEMO_STORY

    veg1, veg2 = random.sample(VEGETABLES, 2)
    prompt = f"""Write a short children's love story between a {veg1} and a {veg2}.
Rules:
- Exactly 5 lines of dialogue, no narration.
- Each line spoken by ONE character, labelled {veg1.upper()}: or {veg2.upper()}:
- One final line starting with MORAL: (one sentence only, no label inside the sentence)
- Max 200 words total, G-rated, for children aged 3-8.
Output only the dialogue lines and the MORAL line, nothing else."""

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"  🤖 Gemini story attempt {attempt}/{MAX_RETRIES}...")
            text  = _gemini(prompt, max_tokens=500)
            lines = [l.strip() for l in text.split("\n") if l.strip()]

            moral_raw = next(
                (l for l in lines if l.upper().startswith("MORAL:")),
                "MORAL: Love makes every garden bloom."
            )
            moral     = moral_raw.split(":", 1)[1].strip()
            dialogues = [
                l for l in lines
                if ":" in l and not l.upper().startswith("MORAL:")
            ][:5]

            if len(dialogues) < 2:
                raise ValueError(f"Too few dialogue lines parsed: {dialogues}")

            story = {"veg1": veg1, "veg2": veg2, "dialogues": dialogues, "moral": moral}
            print(f"  ✅ Story generated: {veg1.title()} & {veg2.title()}")
            return story

        except Exception as e:
            print(f"  ❌ Attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(2)

    print("  ⚠️  All Gemini story attempts failed — using demo story.")
    return DEMO_STORY


# ─────────────────────────────────────────────────────────────────────────────
# METADATA / JSON GENERATION  (Gemini)
# ─────────────────────────────────────────────────────────────────────────────
DEMO_METADATA = {
    "youtube_title":
        "🥕❤️🥔 The Carrot & Potato Love Story | Cute Veggie Tales #Shorts",
    "youtube_description": (
        "Watch as Carrot and Potato discover the magic of friendship and love in their "
        "cozy little garden! 🌻✨\n\n"
        "This sweet animated short reminds us that true love grows stronger through "
        "every season. Perfect for kids and anyone who loves adorable veggie adventures!\n\n"
        "💬 Tell us in the comments: which vegetable couple would you like to see next?\n\n"
        "#Shorts #KidsAnimation #VeggieStory #CarrotAndPotato #CuteCartoon #AnimatedShorts"
    ),
    "instagram_caption": (
        "🥕💛🥔 When Carrot met Potato, the whole garden bloomed! 🌸🌻\n\n"
        "Sometimes the most unlikely friendships grow into the most beautiful love stories 💕\n\n"
        "Swipe up to watch the full reel! 🎬✨\n\n"
        "#VeggieLife #KidsAnimation #CuteCartoon #AnimatedReel #GardenLove #CarrotLove "
        "#PotatoLove #ChildrensContent #FunForKids #AnimatedShorts #ReelViral #CuteFoodArt "
        "#VegetableLove #KidsCartoon #FoodieArt #GardenVibes #InstagramReels #ShortFilm "
        "#AnimationArt #LoveStory"
    ),
}


def generate_metadata(story: dict) -> dict:
    if not HAS_GEMINI:
        print("  ⚠️  google-genai not available — using demo metadata.\n")
        return _swap_demo_metadata(story)

    v1, v2 = story["veg1"].title(), story["veg2"].title()
    prompt = f"""Create social-media metadata for a children's animated YouTube Short about a
love story between {v1} and {v2}. The moral is: "{story['moral']}"

Return ONLY valid JSON (absolutely no markdown fences, no extra text) with these three keys:
{{
  "youtube_title": "<catchy title ≤100 chars, include #Shorts at end>",
  "youtube_description": "<2-3 paragraph description with relevant hashtags>",
  "instagram_caption": "<engaging caption + exactly 20 SEO hashtags>"
}}"""

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"  🤖 Gemini metadata attempt {attempt}/{MAX_RETRIES}...")
            raw = _gemini(prompt, max_tokens=600)
            raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            result = json.loads(raw)
            print("  ✅ Metadata generated.")
            return result
        except Exception as e:
            print(f"  ❌ Metadata attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(2)

    print("  ⚠️  All metadata attempts failed — using demo metadata.")
    return _swap_demo_metadata(story)


def _swap_demo_metadata(story: dict) -> dict:
    meta = dict(DEMO_METADATA)
    v1, v2 = story["veg1"].title(), story["veg2"].title()
    for k in meta:
        meta[k] = (meta[k]
                   .replace("Carrot", v1).replace("Potato", v2)
                   .replace("carrot", v1.lower()).replace("potato", v2.lower()))
    return meta


def save_metadata(story: dict, meta: dict, base_name: str) -> str:
    os.makedirs(METADATA_DIR, exist_ok=True)
    path = os.path.join(METADATA_DIR, base_name + ".json")
    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "characters": {"veg1": story["veg1"], "veg2": story["veg2"]},
        "moral": story["moral"],
        **meta,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"  📄 Metadata → {path}")
    return path


# ─────────────────────────────────────────────────────────────────────────────
# VOICE GENERATION  (3 retries per line)
# ─────────────────────────────────────────────────────────────────────────────
async def _speak(text, voice, path):
    tts = edge_tts.Communicate(text, voice)
    await tts.save(path)


def _generate_line_audio(text: str, voice: str, path: str) -> bool:
    """Try to generate a single audio line up to MAX_RETRIES times. Returns True on success."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            asyncio.run(_speak(text, voice, path))
            if os.path.exists(path) and os.path.getsize(path) > 0:
                return True
            raise RuntimeError("Output file empty or missing")
        except Exception as e:
            print(f"      ⚠️  Audio attempt {attempt}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(1.5)
    return False


def generate_all_audio(story: dict) -> list:
    os.makedirs(AUDIO_DIR, exist_ok=True)
    audio_files = []

    if not HAS_EDGE_TTS:
        print("  ⚠️  edge-tts not installed — silent placeholders.\n")
        for i, line in enumerate(story["dialogues"]):
            speaker, text = line.split(":", 1)
            path = f"{AUDIO_DIR}/line_{i}.wav"
            _write_silent_wav(path, duration=3)
            audio_files.append({"path": path,
                                 "speaker": speaker.lower().strip(),
                                 "text": text.strip()})
        return audio_files

    for i, line in enumerate(story["dialogues"]):
        speaker, text = line.split(":", 1)
        speaker = speaker.lower().strip()
        voice   = VOICE_1 if speaker == story["veg1"] else VOICE_2
        path    = f"{AUDIO_DIR}/line_{i}.mp3"
        print(f"    🎙️  Line {i+1}: {speaker} — {text.strip()[:50]}...")

        success = _generate_line_audio(text.strip(), voice, path)
        if not success:
            print(f"    ⚠️  All retries failed for line {i+1}. Using silent placeholder.")
            path = f"{AUDIO_DIR}/line_{i}.wav"
            _write_silent_wav(path, duration=3)

        audio_files.append({"path": path, "speaker": speaker, "text": text.strip()})

    return audio_files


def _write_silent_wav(path, duration=3, rate=22050):
    n = rate * duration
    with wave.open(path, "w") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(rate)
        wf.writeframes(struct.pack("<" + "h" * n, *([0] * n)))


# ─────────────────────────────────────────────────────────────────────────────
# FONT HELPER
# ─────────────────────────────────────────────────────────────────────────────
def _get_font(size, bold=False):
    suffix = "-Bold" if bold else ""
    candidates = [
        f"/usr/share/fonts/truetype/dejavu/DejaVuSans{suffix}.ttf",
        f"/usr/share/fonts/truetype/liberation/LiberationSans{suffix}.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _wrap_text(text, max_chars=26):
    words = text.split()
    lines, line = [], []
    for w in words:
        if len(" ".join(line + [w])) <= max_chars:
            line.append(w)
        else:
            if line:
                lines.append(" ".join(line))
            line = [w]
    if line:
        lines.append(" ".join(line))
    return lines


# ─────────────────────────────────────────────────────────────────────────────
# CHARACTER DRAWING  (reference-style cartoon vegetables)
# ─────────────────────────────────────────────────────────────────────────────
VEG_COLORS = {
    "potato":   {"body":"#D4922A","light":"#E8B86D","shadow":"#A86E1A",
                 "freckle":"#8B5E1A","eye":"#1A0A00","cheek":"#E07050","outline":"#8B5C14"},
    "carrot":   {"body":"#FF6B1A","light":"#FF9955","shadow":"#CC4400",
                 "eye":"#1A0800","cheek":"#FF8060","outline":"#B84000","leaf":"#2E8B2E"},
    "broccoli": {"body":"#3A9A3A","light":"#5DC45D","shadow":"#1F6B1F",
                 "trunk":"#8B6340","eye":"#1B3E1B","cheek":"#80C080","outline":"#1A5C1A"},
    "tomato":   {"body":"#E03030","light":"#FF6060","shadow":"#AA1A1A",
                 "highlight":"#FFFFFF","eye":"#1A0A0A","cheek":"#D06060","outline":"#880000",
                 "stem":"#2A7A2A"},
    "onion":    {"body":"#CE93D8","light":"#E8C0F0","shadow":"#9C27B0",
                 "eye":"#1A0030","cheek":"#DDA0DD","outline":"#7B1FA2"},
    "eggplant": {"body":"#6A1B9A","light":"#9C4DC0","shadow":"#4A148C",
                 "eye":"#F0D0FF","cheek":"#9B4FBF","outline":"#3A0070",
                 "stem":"#2E7D32","arm":"#2A0050"},
    "pumpkin":  {"body":"#FF8C00","light":"#FFB84D","shadow":"#CC5500",
                 "rib":"#E06600","eye":"#0A0A1A","cheek":"#FFB0A0","outline":"#CC4400",
                 "stem":"#5D3A1A","leaf":"#2E7D32"},
    "corn":     {"body":"#FDD835","light":"#FFF176","shadow":"#F57F17",
                 "eye":"#2C1A00","cheek":"#FFE082","outline":"#E65100","husk":"#558B2F"},
    "cucumber": {"body":"#5A9A3A","light":"#80C060","shadow":"#2E6A1A",
                 "stripe":"#3A7A1A","eye":"#0A2A0A","cheek":"#90D070","outline":"#1A4A00"},
    "pepper":   {"body":"#FFCC00","light":"#FFE066","shadow":"#CC9900",
                 "eye":"#1A1A3A","cheek":"#FFD060","outline":"#996600","stem":"#3A7A2A"},
    "zucchini": {"body":"#4A8A2A","light":"#70B050","shadow":"#2A5A10",
                 "stripe":"#2A6A10","eye":"#0A200A","cheek":"#80C060","outline":"#1A4000"},
    "radish":   {"body":"#E83060","light":"#FF6090","shadow":"#C01040",
                 "root":"#F0F0F0","eye":"#2A000A","cheek":"#FF90A0","outline":"#A00030",
                 "leaf":"#2E7D32"},
}


def _oval(draw, cx, cy, rx, ry, fill, outline=None, width=2):
    draw.ellipse([cx-rx, cy-ry, cx+rx, cy+ry], fill=fill, outline=outline, width=width)


def _kawaii_eyes(draw, cx, cy, scale, eye_color="#1A0A0A", big=True):
    er = int((13 if big else 9) * scale)
    ex = int(18 * scale)
    ey_off = int(6 * scale)
    for sign in [-1, 1]:
        ox, oy = cx + sign * ex, cy - ey_off
        draw.ellipse([ox-er, oy-er, ox+er, oy+er], fill="white")
        ir = int(er * 0.72)
        draw.ellipse([ox-ir, oy-ir, ox+ir, oy+ir], fill=eye_color)
        sr = max(2, int(er * 0.28))
        draw.ellipse([ox-er//2, oy-er//2, ox-er//2+sr*2, oy-er//2+sr*2], fill="white")


def _normal_eyes(draw, cx, cy, scale, eye_color="#1A1A3A"):
    er = int(9 * scale)
    ex = int(16 * scale)
    ey_off = int(4 * scale)
    for sign in [-1, 1]:
        ox, oy = cx + sign * ex, cy - ey_off
        draw.ellipse([ox-er, oy-er, ox+er, oy+er], fill="white", outline="#333", width=2)
        ir = int(er * 0.62)
        draw.ellipse([ox-ir, oy-ir*2//3, ox+ir, oy+ir*2//3], fill=eye_color)
        sr = max(2, int(er * 0.28))
        draw.ellipse([ox-er//2, oy-er//2, ox-er//2+sr*2, oy-er//2+sr*2], fill="white")


def _cheeks(draw, cx, cy, scale, color, spread=28):
    ck = int(10 * scale)
    sp = int(spread * scale)
    for sign in [-1, 1]:
        draw.ellipse([cx+sign*sp-ck, cy-ck//2, cx+sign*sp+ck, cy+ck//2], fill=color)


def _mouth_open(draw, cx, cy, scale, color="#CC2222"):
    mw = int(16 * scale)
    my = cy + int(14 * scale)
    draw.ellipse([cx-mw, my-int(10*scale), cx+mw, my+int(6*scale)],
                 fill=color, outline="#880000", width=2)
    draw.rectangle([cx-mw+4, my-int(9*scale), cx+mw-4, my-int(3*scale)], fill="white")


def _mouth_smile(draw, cx, cy, scale):
    mw = int(16 * scale)
    my = cy + int(10 * scale)
    draw.arc([cx-mw, my-int(8*scale), cx+mw, my+int(8*scale)],
             start=0, end=180, fill="#333333", width=max(2, int(3*scale)))


def _legs(draw, cx, bot_y, scale, color):
    lw = max(3, int(7 * scale))
    lx = int(14 * scale)
    ly = int(28 * scale)
    for sign in [-1, 1]:
        draw.line([cx+sign*lx//2, bot_y, cx+sign*lx, bot_y+ly],
                  fill=color, width=lw)
        draw.ellipse([cx+sign*lx-int(10*scale), bot_y+ly-int(6*scale),
                      cx+sign*lx+int(12*scale), bot_y+ly+int(8*scale)], fill="#333333")


def _simple_arm(draw, x1, y1, x2, y2, color, scale):
    w = max(3, int(7 * scale))
    draw.line([(x1, y1), (x2, y2)], fill=color, width=w)
    hr = max(4, int(8 * scale))
    draw.ellipse([x2-hr, y2-hr, x2+hr, y2+hr], fill="white", outline=color, width=2)


# ── Individual vegetable drawers ──────────────────────────────────────────────

def _draw_potato(draw, cx, cy, scale, c, mouth_open, talking):
    rx, ry = int(52*scale), int(62*scale)
    draw.ellipse([cx-rx, cy+ry-4, cx+rx, cy+ry+int(10*scale)], fill="#00000022")
    rng = random.Random(7)
    pts = []
    for a in range(0, 360, 15):
        rad = math.radians(a)
        lump = rng.uniform(0.88, 1.12)
        pts.append((cx+int(rx*lump*math.cos(rad)), cy+int(ry*lump*math.sin(rad))))
    draw.polygon(pts, fill=c["body"], outline=c["outline"], width=3)
    draw.ellipse([cx-int(28*scale), cy-int(40*scale),
                  cx+int(4*scale),  cy+int(10*scale)], fill=c["light"])
    freckles = [(-20,-15),(-8,-30),(18,-20),(22,5),(-25,10),(5,25),(-15,30),(22,28)]
    for fx, fy in freckles:
        fr = max(2, int(3.5*scale))
        draw.ellipse([cx+int(fx*scale)-fr, cy+int(fy*scale)-fr,
                      cx+int(fx*scale)+fr, cy+int(fy*scale)+fr], fill=c["freckle"])
    _simple_arm(draw, cx-rx+10, cy-int(10*scale), cx-rx-int(22*scale), cy+int(18*scale), c["outline"], scale*0.8)
    _simple_arm(draw, cx+rx-10, cy-int(10*scale), cx+rx+int(22*scale), cy+int(18*scale), c["outline"], scale*0.8)
    _legs(draw, cx, cy+ry-6, scale, c["outline"])
    face_cy = cy - int(8*scale)
    _normal_eyes(draw, cx, face_cy, scale, c["eye"])
    _cheeks(draw, cx, face_cy+int(16*scale), scale, c["cheek"], spread=24)
    if mouth_open: _mouth_open(draw, cx, face_cy+int(8*scale), scale)
    else: _mouth_smile(draw, cx, face_cy+int(8*scale), scale)
    brow_y = face_cy - int(14*scale)
    for sign in [-1, 1]:
        bx2 = cx + sign*int(16*scale)
        draw.arc([bx2-int(9*scale), brow_y-int(4*scale),
                  bx2+int(9*scale), brow_y+int(4*scale)],
                 start=200 if sign==-1 else 340, end=340 if sign==-1 else 500,
                 fill="#5C3D1A", width=max(2, int(3*scale)))


def _draw_carrot(draw, cx, cy, scale, c, mouth_open, talking):
    rx, ry = int(36*scale), int(68*scale)
    bot, top = cy+ry, cy-ry
    draw.ellipse([cx-rx, bot-4, cx+rx, bot+int(10*scale)], fill="#00000022")
    pts = [(cx-rx, top+int(20*scale)), (cx+rx, top+int(20*scale)),
           (cx+int(18*scale), bot), (cx-int(18*scale), bot)]
    draw.polygon(pts, fill=c["body"], outline=c["outline"], width=3)
    draw.ellipse([cx-rx, top, cx+rx, top+int(40*scale)], fill=c["body"], outline=c["outline"], width=3)
    draw.ellipse([cx-int(14*scale), top+int(8*scale),
                  cx+int(2*scale),  cy+int(20*scale)], fill=c["light"])
    for frac in [0.35, 0.55, 0.72]:
        ty2 = int(top+(bot-top)*frac)
        half_w = int(rx*(1-(frac-0.2)))
        draw.arc([cx-half_w, ty2-3, cx+half_w, ty2+3], start=0, end=180, fill=c["shadow"], width=2)
    leaf_cy = top - int(4*scale)
    for angle, llen in [(-50,28),(-20,36),(0,40),(20,36),(50,28)]:
        rad = math.radians(angle-90)
        lx2 = cx+int(llen*scale*math.cos(rad))
        ly2 = leaf_cy+int(llen*scale*math.sin(rad))
        draw.line([(cx, leaf_cy), (lx2, ly2)], fill=c["leaf"], width=max(3,int(4*scale)))
    arm_base_y = cy-int(20*scale)
    _simple_arm(draw, cx-rx+8, arm_base_y, cx-rx-int(24*scale), arm_base_y-int(30*scale), c["outline"], scale*0.85)
    _simple_arm(draw, cx+rx-8, arm_base_y, cx+rx+int(24*scale), arm_base_y-int(30*scale), c["outline"], scale*0.85)
    _legs(draw, cx, bot-6, scale, c["outline"])
    face_cy = cy-int(14*scale)
    _normal_eyes(draw, cx, face_cy, scale, c["eye"])
    _cheeks(draw, cx, face_cy+int(16*scale), scale, c["cheek"], spread=22)
    if mouth_open: _mouth_open(draw, cx, face_cy+int(8*scale), scale, "#CC3300")
    else: _mouth_smile(draw, cx, face_cy+int(8*scale), scale)


def _draw_tomato(draw, cx, cy, scale, c, mouth_open, talking):
    r = int(58*scale)
    draw.ellipse([cx-r, cy+r-4, cx+r, cy+r+int(10*scale)], fill="#00000022")
    draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=c["body"], outline=c["outline"], width=4)
    draw.ellipse([cx-int(30*scale), cy-int(40*scale),
                  cx-int(6*scale),  cy-int(20*scale)], fill="white")
    draw.ellipse([cx-int(22*scale), cy-int(30*scale),
                  cx-int(10*scale), cy-int(22*scale)], fill="white")
    draw.rectangle([cx-int(5*scale), cy-r-int(20*scale),
                    cx+int(5*scale), cy-r+4], fill=c["stem"])
    for angle in [-50,-20,10,40]:
        rad = math.radians(angle-90)
        lx2 = cx+int(22*scale*math.cos(rad))
        ly2 = cy-r-2+int(18*scale*math.sin(rad))
        draw.line([(cx, cy-r), (lx2, ly2)], fill=c["stem"], width=max(3,int(4*scale)))
        draw.ellipse([lx2-int(5*scale), ly2-int(5*scale),
                      lx2+int(5*scale), ly2+int(5*scale)], fill=c["stem"])
    face_cy = cy+int(6*scale)
    _kawaii_eyes(draw, cx, face_cy, scale, c["eye"], big=True)
    _cheeks(draw, cx, face_cy+int(18*scale), scale, c["cheek"], spread=26)
    if mouth_open: _mouth_open(draw, cx, face_cy+int(10*scale), scale, "#CC0000")
    else:
        mw = int(14*scale); my = face_cy+int(20*scale)
        draw.arc([cx-mw, my-int(8*scale), cx+mw, my+int(8*scale)],
                 start=0, end=180, fill="#AA0000", width=max(2,int(3*scale)))


def _draw_pumpkin(draw, cx, cy, scale, c, mouth_open, talking):
    ry = int(56*scale)
    draw.ellipse([cx-int(62*scale), cy+ry-4, cx+int(62*scale), cy+ry+int(10*scale)], fill="#00000022")
    lobe_data = [(-int(44*scale),int(34*scale),c["shadow"]),
                 (-int(22*scale),int(44*scale),c["body"]),
                 (0,             int(48*scale),c["light"]),
                 ( int(22*scale),int(44*scale),c["body"]),
                 ( int(44*scale),int(34*scale),c["shadow"])]
    for ox, lrx, col in lobe_data:
        draw.ellipse([cx+ox-lrx, cy-ry, cx+ox+lrx, cy+ry],
                     fill=col, outline=c["outline"], width=2)
    for ox in [-int(22*scale), 0, int(22*scale)]:
        draw.arc([cx+ox-int(8*scale), cy-ry+4, cx+ox+int(8*scale), cy+ry-4],
                 start=60, end=300, fill=c["rib"], width=3)
    draw.rectangle([cx-int(8*scale), cy-ry-int(22*scale),
                    cx+int(8*scale), cy-ry+4], fill=c["stem"])
    leaf_pts = [(cx+int(8*scale), cy-ry-int(16*scale)),
                (cx+int(32*scale), cy-ry-int(28*scale)),
                (cx+int(36*scale), cy-ry-int(8*scale))]
    draw.polygon(leaf_pts, fill=c["leaf"], outline="#1B5E20", width=2)
    draw.line([(cx+int(8*scale), cy-ry-int(16*scale)),
               (cx+int(30*scale), cy-ry-int(14*scale))], fill="#1B5E20", width=2)
    face_cy = cy+int(8*scale)
    _kawaii_eyes(draw, cx, face_cy, scale, c["eye"], big=True)
    _cheeks(draw, cx, face_cy+int(20*scale), scale, c["cheek"], spread=30)
    if mouth_open: _mouth_open(draw, cx, face_cy+int(12*scale), scale, "#993300")
    else:
        mw = int(16*scale); my = face_cy+int(22*scale)
        draw.arc([cx-mw, my-int(8*scale), cx+mw, my+int(8*scale)],
                 start=0, end=180, fill="#884400", width=max(2,int(3*scale)))


def _draw_pepper(draw, cx, cy, scale, c, mouth_open, talking):
    rx, ry = int(50*scale), int(56*scale)
    bot = cy+ry
    draw.ellipse([cx-rx, bot-4, cx+rx, bot+int(10*scale)], fill="#00000022")
    pts = [(cx-rx, cy-int(30*scale)), (cx+rx, cy-int(30*scale)),
           (cx+rx, cy+int(20*scale)),
           (cx+int(32*scale), bot), (cx, bot-int(10*scale)),
           (cx-int(32*scale), bot), (cx-rx, cy+int(20*scale))]
    draw.polygon(pts, fill=c["body"], outline=c["outline"], width=3)
    draw.ellipse([cx-rx, cy-int(50*scale), cx+rx, cy-int(10*scale)],
                 fill=c["body"], outline=c["outline"], width=3)
    draw.ellipse([cx-int(28*scale), cy-int(42*scale),
                  cx-int(6*scale),  cy-int(16*scale)], fill=c["light"])
    for ox in [-int(20*scale), 0, int(20*scale)]:
        draw.arc([cx+ox-int(12*scale), cy+int(22*scale),
                  cx+ox+int(12*scale), cy+ry+int(6*scale)],
                 start=0, end=180, fill=c["outline"], width=2)
    draw.line([(cx, cy-int(50*scale)), (cx, cy-int(64*scale))],
              fill=c["stem"], width=max(3,int(4*scale)))
    draw.arc([cx, cy-int(74*scale), cx+int(22*scale), cy-int(52*scale)],
             start=200, end=360, fill=c["stem"], width=max(3,int(4*scale)))
    face_cy = cy-int(6*scale)
    _normal_eyes(draw, cx, face_cy, scale, c["eye"])
    _cheeks(draw, cx, face_cy+int(18*scale), scale, c["cheek"], spread=28)
    if mouth_open: _mouth_open(draw, cx, face_cy+int(10*scale), scale, "#886600")
    else: _mouth_smile(draw, cx, face_cy+int(10*scale), scale)


def _draw_eggplant(draw, cx, cy, scale, c, mouth_open, talking):
    rx, ry = int(38*scale), int(68*scale)
    top, bot = cy-ry, cy+ry
    draw.ellipse([cx-rx, bot-4, cx+rx, bot+int(10*scale)], fill="#00000022")
    pts = [(cx-int(22*scale), top+int(20*scale)), (cx+int(22*scale), top+int(20*scale)),
           (cx+rx, cy+int(20*scale)), (cx+rx, bot),
           (cx-rx, bot), (cx-rx, cy+int(20*scale))]
    draw.polygon(pts, fill=c["body"], outline=c["outline"], width=3)
    draw.ellipse([cx-int(22*scale), top, cx+int(22*scale), top+int(40*scale)],
                 fill=c["body"], outline=c["outline"], width=3)
    draw.arc([cx-int(14*scale), top+int(8*scale), cx+int(2*scale), cy+int(20*scale)],
             start=200, end=340, fill=c["light"], width=max(3,int(5*scale)))
    draw.rectangle([cx-int(5*scale), top-int(18*scale),
                    cx+int(5*scale), top+4], fill=c["stem"])
    for angle in [-40,-15,15,40]:
        rad = math.radians(angle-90)
        lx2 = cx+int(18*scale*math.cos(rad))
        ly2 = top-2+int(14*scale*math.sin(rad))
        draw.line([(cx, top+2), (lx2, ly2)], fill=c["stem"], width=max(2,int(3*scale)))
    arm_y = cy+int(10*scale)
    for sign in [-1,1]:
        base_x  = cx+sign*(rx-8)
        elbow_x = cx+sign*(rx+int(20*scale))
        elbow_y = arm_y+int(18*scale)
        hand_x  = cx+sign*(rx-int(10*scale))
        hand_y  = arm_y+int(36*scale)
        draw.line([(base_x, arm_y), (elbow_x, elbow_y)], fill=c["arm"], width=max(4,int(7*scale)))
        draw.line([(elbow_x, elbow_y), (hand_x, hand_y)], fill=c["arm"], width=max(4,int(7*scale)))
        hr = max(5, int(9*scale))
        draw.ellipse([hand_x-hr, hand_y-hr, hand_x+hr, hand_y+hr],
                     fill="white", outline=c["arm"], width=2)
    _legs(draw, cx, bot-6, scale, "#333333")
    face_cy = cy-int(20*scale)
    _normal_eyes(draw, cx, face_cy, scale, c["eye"])
    _cheeks(draw, cx, face_cy+int(16*scale), scale, c["cheek"], spread=22)
    if mouth_open: _mouth_open(draw, cx, face_cy+int(8*scale), scale, "#AA2288")
    else: _mouth_smile(draw, cx, face_cy+int(8*scale), scale)


def _draw_broccoli(draw, cx, cy, scale, c, mouth_open, talking):
    trunk_w  = int(20*scale)
    canopy_cy = cy - int(48*scale)
    canopy_base_r = int(38*scale)
    trunk_top = canopy_cy + canopy_base_r - int(6*scale)
    trunk_bot = cy + int(70*scale)

    draw.ellipse([cx-int(55*scale), trunk_bot-4, cx+int(55*scale), trunk_bot+int(10*scale)],
                 fill="#00000022")
    draw.rectangle([cx-trunk_w, trunk_top, cx+trunk_w, trunk_bot],
                   fill=c["trunk"], outline="#5D3A1A", width=2)
    for lx in [cx-trunk_w//3, cx+trunk_w//3]:
        draw.line([lx, trunk_top+8, lx, trunk_bot-8], fill="#6D4A2A", width=2)

    for sign in [-1, 1]:
        rx0 = min(cx+sign*int(4*scale), cx+sign*int(28*scale))
        rx1 = max(cx+sign*int(4*scale), cx+sign*int(28*scale))
        draw.arc([rx0, trunk_bot-int(8*scale), rx1, trunk_bot+int(12*scale)],
                 start=0 if sign==1 else 180, end=180 if sign==1 else 360,
                 fill=c["trunk"], width=3)

    bumps = [
        (0,              0,              int(38*scale)),
        (-int(34*scale), int(14*scale),  int(26*scale)),
        ( int(34*scale), int(14*scale),  int(26*scale)),
        (-int(18*scale), -int(26*scale), int(24*scale)),
        ( int(18*scale), -int(26*scale), int(24*scale)),
        (-int(46*scale), int(4*scale),   int(20*scale)),
        ( int(46*scale), int(4*scale),   int(20*scale)),
    ]
    for ox, oy, r in bumps:
        draw.ellipse([cx+ox-r+4, canopy_cy+oy-r+4,
                      cx+ox+r+4, canopy_cy+oy+r+4], fill=c["shadow"])
    for ox, oy, r in bumps:
        draw.ellipse([cx+ox-r, canopy_cy+oy-r, cx+ox+r, canopy_cy+oy+r],
                     fill=c["body"], outline=c["outline"], width=2)
    draw.ellipse([cx-int(22*scale), canopy_cy-int(30*scale),
                  cx+int(2*scale),  canopy_cy-int(10*scale)], fill=c["light"])

    for gx in range(-int(30*scale), int(35*scale), int(14*scale)):
        draw.line([cx+gx, trunk_bot+2, cx+gx-int(4*scale), trunk_bot+int(14*scale)],
                  fill="#2E7D32", width=3)
        draw.line([cx+gx, trunk_bot+2, cx+gx+int(4*scale), trunk_bot+int(14*scale)],
                  fill="#2E7D32", width=3)

    face_cy = cy + int(20*scale)
    _normal_eyes(draw, cx, face_cy, scale*0.9, c["eye"])
    _cheeks(draw, cx, face_cy+int(16*scale), scale*0.9, c["cheek"], spread=18)
    if mouth_open: _mouth_open(draw, cx, face_cy+int(8*scale), scale*0.9)
    else: _mouth_smile(draw, cx, face_cy+int(8*scale), scale*0.9)


def _draw_onion(draw, cx, cy, scale, c, mouth_open, talking):
    rx, ry = int(46*scale), int(54*scale)
    draw.ellipse([cx-rx, cy-ry, cx+rx, cy+ry], fill=c["body"], outline=c["outline"], width=3)
    draw.ellipse([cx-int(24*scale), cy-int(40*scale),
                  cx+int(10*scale), cy+int(10*scale)], fill=c["light"])
    for offset in [int(14*scale), int(26*scale), int(38*scale)]:
        draw.arc([cx-offset, cy-int(38*scale)+offset//3,
                  cx+offset, cy+int(38*scale)-offset//3],
                 start=20, end=160, fill=c["shadow"], width=2)
    draw.line([(cx, cy-ry), (cx, cy-ry-int(18*scale))],
              fill=c["outline"], width=max(2,int(3*scale)))
    face_cy = cy-int(6*scale)
    _normal_eyes(draw, cx, face_cy, scale, c["eye"])
    _cheeks(draw, cx, face_cy+int(16*scale), scale, c["cheek"])
    if mouth_open: _mouth_open(draw, cx, face_cy+int(8*scale), scale)
    else: _mouth_smile(draw, cx, face_cy+int(8*scale), scale)


def _draw_corn(draw, cx, cy, scale, c, mouth_open, talking):
    cw, ct, cb = int(30*scale), cy-int(60*scale), cy+int(60*scale)
    for sign in [-1,1]:
        pts = [(cx, cb+int(8*scale)),
               (cx+sign*int(48*scale), cb-int(18*scale)),
               (cx+sign*int(34*scale), cb-int(48*scale))]
        draw.polygon(pts, fill=c["husk"], outline="#2E7D32", width=2)
    draw.rounded_rectangle([cx-cw, ct, cx+cw, cb],
                            radius=int(cw), fill=c["body"], outline=c["outline"], width=3)
    for ky in range(ct+int(8*scale), cb-int(8*scale), int(10*scale)):
        for kx in range(cx-cw+int(8*scale), cx+cw-int(4*scale), int(10*scale)):
            kr = int(3.5*scale)
            draw.ellipse([kx-kr, ky-kr, kx+kr, ky+kr],
                         fill=c["light"], outline=c["shadow"], width=1)
    for i in range(-2,3):
        draw.line([(cx+i*int(4*scale), ct), (cx+i*int(6*scale), ct-int(16*scale))],
                  fill="#BC8F5F", width=max(1,int(2*scale)))
    face_cy = cy-int(12*scale)
    _normal_eyes(draw, cx, face_cy, scale, c["eye"])
    _cheeks(draw, cx, face_cy+int(16*scale), scale, c["cheek"])
    if mouth_open: _mouth_open(draw, cx, face_cy+int(8*scale), scale)
    else: _mouth_smile(draw, cx, face_cy+int(8*scale), scale)


def _draw_cucumber(draw, cx, cy, scale, c, mouth_open, talking):
    cw, ct, cb = int(28*scale), cy-int(64*scale), cy+int(64*scale)
    draw.rounded_rectangle([cx-cw, ct, cx+cw, cb],
                            radius=int(cw), fill=c["body"], outline=c["outline"], width=3)
    for i in [-1,0,1]:
        draw.line([(cx+i*int(10*scale), ct+8), (cx+i*int(10*scale), cb-8)],
                  fill=c["stripe"], width=2)
    draw.rectangle([cx-int(4*scale), ct-int(14*scale),
                    cx+int(4*scale), ct+2], fill="#5D4037")
    draw.ellipse([cx-int(6*scale), ct-int(20*scale),
                  cx+int(6*scale), ct-int(8*scale)], fill="#388E3C")
    face_cy = cy
    _normal_eyes(draw, cx, face_cy, scale, c["eye"])
    _cheeks(draw, cx, face_cy+int(16*scale), scale, c["cheek"])
    if mouth_open: _mouth_open(draw, cx, face_cy+int(8*scale), scale)
    else: _mouth_smile(draw, cx, face_cy+int(8*scale), scale)


def _draw_zucchini(draw, cx, cy, scale, c, mouth_open, talking):
    cw, ct, cb = int(26*scale), cy-int(66*scale), cy+int(66*scale)
    draw.rounded_rectangle([cx-cw, ct, cx+cw, cb],
                            radius=int(cw*0.9), fill=c["body"], outline=c["outline"], width=3)
    for i in [-1,0,1]:
        draw.line([(cx+i*int(9*scale), ct+8), (cx+i*int(9*scale), cb-8)],
                  fill=c["stripe"], width=1)
    draw.ellipse([cx-cw+2, cb-int(18*scale), cx+cw-2, cb+int(6*scale)],
                 fill="#FDD835", outline=c["outline"], width=2)
    draw.rectangle([cx-int(4*scale), ct-int(14*scale),
                    cx+int(4*scale), ct+2], fill="#5D4037")
    draw.ellipse([cx-int(8*scale), ct-int(22*scale),
                  cx+int(8*scale), ct-int(6*scale)], fill="#FFEB3B")
    face_cy = cy
    _normal_eyes(draw, cx, face_cy, scale, c["eye"])
    _cheeks(draw, cx, face_cy+int(16*scale), scale, c["cheek"])
    if mouth_open: _mouth_open(draw, cx, face_cy+int(8*scale), scale)
    else: _mouth_smile(draw, cx, face_cy+int(8*scale), scale)


def _draw_radish(draw, cx, cy, scale, c, mouth_open, talking):
    r = int(46*scale)
    root_pts = [(cx-int(12*scale), cy+int(34*scale)),
                (cx+int(12*scale), cy+int(34*scale)),
                (cx, cy+int(70*scale))]
    draw.polygon(root_pts, fill=c["root"], outline="#BDBDBD", width=2)
    draw.ellipse([cx-r, cy-r, cx+r, cy+int(36*scale)],
                 fill=c["body"], outline=c["outline"], width=3)
    draw.ellipse([cx-int(14*scale), cy-int(34*scale),
                  cx+int(4*scale),  cy-int(12*scale)], fill=c["light"])
    for angle in [-40,-15,15,40]:
        rad = math.radians(angle-90)
        lx2 = cx+int(16*scale*math.cos(rad))
        ly2 = cy-r-2+int(18*scale*math.sin(rad))
        draw.line([(cx, cy-r), (lx2, ly2)], fill=c["leaf"], width=max(2,int(3*scale)))
    face_cy = cy-int(4*scale)
    _normal_eyes(draw, cx, face_cy, scale, c["eye"])
    _cheeks(draw, cx, face_cy+int(16*scale), scale, c["cheek"])
    if mouth_open: _mouth_open(draw, cx, face_cy+int(8*scale), scale)
    else: _mouth_smile(draw, cx, face_cy+int(8*scale), scale)


SHAPE_DRAWERS = {
    "potato": _draw_potato,   "carrot": _draw_carrot,
    "broccoli": _draw_broccoli, "tomato": _draw_tomato,
    "onion": _draw_onion,     "eggplant": _draw_eggplant,
    "pumpkin": _draw_pumpkin, "corn": _draw_corn,
    "cucumber": _draw_cucumber, "pepper": _draw_pepper,
    "zucchini": _draw_zucchini, "radish": _draw_radish,
}


def draw_character(draw, veg_name, cx, cy, scale=1.0, mouth_open=False, talking=False):
    c  = VEG_COLORS.get(veg_name, VEG_COLORS["potato"])
    fn = SHAPE_DRAWERS.get(veg_name, _draw_potato)
    fn(draw, cx, cy, scale, c, mouth_open, talking)


# ─────────────────────────────────────────────────────────────────────────────
# BACKGROUND EXTRA VEGETABLES  (small, faded, non-main-character)
# ─────────────────────────────────────────────────────────────────────────────
_BG_EXTRAS = [
    ("onion",    0.10, -30, 0.38),
    ("radish",   0.22, -20, 0.32),
    ("corn",     0.72,  10, 0.40),
    ("cucumber", 0.85, -15, 0.35),
    ("zucchini", 0.16,  -5, 0.30),
    ("tomato",   0.78, -28, 0.34),
]


def _draw_bg_extras(img_rgba, story, ground_y, alpha_frac=0.38):
    skip = {story["veg1"], story["veg2"]}
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d     = ImageDraw.Draw(layer)
    for veg, xf, cy_off, sc in _BG_EXTRAS:
        if veg in skip:
            continue
        cx2 = int(xf * W)
        cy2 = ground_y + cy_off
        draw_character(d, veg, cx2, cy2, scale=sc)

    r, g, b, a = layer.split()
    a = a.point(lambda x: int(x * alpha_frac))
    layer = Image.merge("RGBA", (r, g, b, a))
    img_rgba.alpha_composite(layer)


# ─────────────────────────────────────────────────────────────────────────────
# GARDEN TREE + BIRD
# ─────────────────────────────────────────────────────────────────────────────
def _draw_garden_tree(draw, tx, ty, scale=1.0, bird_phase=0.0):
    s = scale
    trunk_w = int(22*s)
    trunk_h = int(110*s)
    canopy_lift = int(55*s)
    trunk_top_y = ty - trunk_h
    canopy_cy   = trunk_top_y - canopy_lift

    draw.rectangle([tx-trunk_w, trunk_top_y, tx+trunk_w, ty],
                   fill="#8B6340", outline="#5D3A1A", width=2)
    for lx in [tx-trunk_w//3, tx+trunk_w//3]:
        draw.line([(lx, trunk_top_y+4), (lx, ty-4)], fill="#6D4A2A", width=2)

    draw.line([(tx-trunk_w+4, trunk_top_y+int(40*s)),
               (tx-int(60*s), trunk_top_y+int(8*s))],
              fill="#8B6340", width=max(5,int(8*s)))
    draw.line([(tx+trunk_w-4, trunk_top_y+int(30*s)),
               (tx+int(65*s), trunk_top_y+int(2*s))],
              fill="#8B6340", width=max(5,int(8*s)))

    bumps = [
        (0,              0,            int(52*s)),
        (-int(40*s),     int(18*s),    int(34*s)),
        ( int(40*s),     int(18*s),    int(34*s)),
        (-int(20*s),    -int(28*s),    int(30*s)),
        ( int(20*s),    -int(28*s),    int(30*s)),
        (-int(58*s),     int(6*s),     int(24*s)),
        ( int(58*s),     int(6*s),     int(24*s)),
    ]
    shadow_col = "#2E7D32"; main_col = "#43A047"; light_col = "#66BB6A"
    for ox, oy, r in bumps:
        draw.ellipse([tx+ox-r+4, canopy_cy+oy-r+4,
                      tx+ox+r+4, canopy_cy+oy+r+4], fill=shadow_col)
    for ox, oy, r in bumps:
        draw.ellipse([tx+ox-r, canopy_cy+oy-r, tx+ox+r, canopy_cy+oy+r],
                     fill=main_col, outline="#1B5E20", width=2)
    draw.ellipse([tx-int(18*s), canopy_cy-int(40*s),
                  tx+int(4*s),  canopy_cy-int(20*s)], fill=light_col)

    for gx in range(-int(30*s), int(35*s), int(14*s)):
        draw.line([(tx+gx, ty), (tx+gx-int(5*s), ty+int(14*s))],
                  fill="#388E3C", width=3)
        draw.line([(tx+gx, ty), (tx+gx+int(5*s), ty+int(14*s))],
                  fill="#388E3C", width=3)

    bx2 = tx + int(65*s)
    by2 = trunk_top_y + int(2*s) - int(28*s) + int(4*math.sin(bird_phase))
    _draw_blue_bird(draw, bx2, by2, s*0.55)


def _draw_blue_bird(draw, cx, cy, scale):
    s = scale
    br = int(18*s)
    body_col = "#4A90D9"; wing_col = "#3A78C0"
    light_col = "#7AB8F0"; beak_col = "#FFA726"; eye_col = "#1A1A2E"

    tail_pts = [(cx+br-4,          cy+int(6*s)),
                (cx+br+int(20*s),  cy+int(16*s)),
                (cx+br+int(14*s),  cy+int(4*s))]
    draw.polygon(tail_pts, fill=wing_col, outline="#2A5A90", width=1)
    wing_pts = [(cx-int(4*s),  cy+int(4*s)),
                (cx-int(22*s), cy+int(20*s)),
                (cx+int(6*s),  cy+int(22*s))]
    draw.polygon(wing_pts, fill=wing_col, outline="#2A5A90", width=1)
    draw.ellipse([cx-br, cy-br, cx+br, cy+br], fill=body_col, outline="#2A5A90", width=2)
    draw.ellipse([cx-int(10*s), cy, cx+int(10*s), cy+int(14*s)], fill=light_col)

    hr = int(14*s)
    hx2, hy2 = cx-int(8*s), cy-br+int(4*s)
    draw.ellipse([hx2-hr, hy2-hr, hx2+hr, hy2+hr], fill=body_col, outline="#2A5A90", width=2)
    for ca, cl in [(-80,14),(-65,18),(-50,14)]:
        rad = math.radians(ca)
        px2 = hx2+int(cl*s*math.cos(rad)); py2 = hy2+int(cl*s*math.sin(rad))
        draw.line([(hx2, hy2), (px2, py2)], fill="#3A78C0", width=max(2,int(3*s)))

    er = int(5*s); ex2, ey2 = hx2+int(6*s), hy2-int(2*s)
    draw.ellipse([ex2-er, ey2-er, ex2+er, ey2+er], fill="white")
    draw.ellipse([ex2-int(3*s), ey2-int(3*s), ex2+int(3*s), ey2+int(3*s)], fill=eye_col)
    draw.ellipse([ex2-er//2, ey2-er//2, ex2-er//2+int(2*s), ey2-er//2+int(2*s)], fill="white")

    beak_x2, beak_y2 = hx2+hr-2, hy2+int(2*s)
    draw.polygon([(beak_x2, beak_y2),
                  (beak_x2+int(10*s), beak_y2-int(2*s)),
                  (beak_x2+int(10*s), beak_y2+int(3*s))],
                 fill=beak_col, outline="#E65100", width=1)

    foot_y2 = cy+br-2
    for sign in [-1,1]:
        fx2 = cx+sign*int(6*s)
        draw.line([(fx2, foot_y2), (fx2+sign*int(6*s), foot_y2+int(10*s))],
                  fill="#FFA726", width=max(2,int(2*s)))
        for ta in [-1,0,1]:
            draw.line([(fx2+sign*int(6*s), foot_y2+int(10*s)),
                       (fx2+sign*int(6*s)+ta*int(6*s), foot_y2+int(18*s))],
                      fill="#FFA726", width=max(1,int(2*s)))


# ─────────────────────────────────────────────────────────────────────────────
# BACKGROUND  (pixel-row gradient sky + ground)
# ─────────────────────────────────────────────────────────────────────────────
def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


BACKGROUNDS = [
    {"sky_top":"#4FB8E8","sky_bot":"#B8E4F8",
     "gnd_top":"#6AAC68","gnd_bot":"#4A8C48",
     "sun":"#FFF176","sun2":"#FFD700"},
    {"sky_top":"#F5B830","sky_bot":"#FDE688",
     "gnd_top":"#8DC88F","gnd_bot":"#66A868",
     "sun":"#FF8F00","sun2":"#FFA000"},
    {"sky_top":"#E880A8","sky_bot":"#F8C8DC",
     "gnd_top":"#B878C8","gnd_bot":"#9050A8",
     "sun":"#FF80AB","sun2":"#FF4081"},
    {"sky_top":"#5AB4E0","sky_bot":"#C8EAF8",
     "gnd_top":"#C0D890","gnd_bot":"#9ABC68",
     "sun":"#FFCC02","sun2":"#FFB300"},
    {"sky_top":"#F8E060","sky_bot":"#FFF8C0",
     "gnd_top":"#A8D8A8","gnd_bot":"#80B880",
     "sun":"#FFCA28","sun2":"#FFA000"},
]

TREE_X  = W - 115
GROUND_Y = H * 3 // 5


def _draw_gradient_background(img_array, bg):
    sky_top = np.array(_hex_to_rgb(bg["sky_top"]), dtype=float)
    sky_bot = np.array(_hex_to_rgb(bg["sky_bot"]), dtype=float)
    gnd_top = np.array(_hex_to_rgb(bg["gnd_top"]), dtype=float)
    gnd_bot = np.array(_hex_to_rgb(bg["gnd_bot"]), dtype=float)

    for y in range(H):
        if y <= GROUND_Y:
            t = y / GROUND_Y
            col = sky_top + (sky_bot - sky_top) * t
        else:
            t = (y - GROUND_Y) / (H - GROUND_Y)
            blend = min(1.0, t / 0.05)
            col = gnd_top + (gnd_bot - gnd_top) * t * blend
        img_array[y, :] = col.astype(np.uint8)


def _draw_background(img, scene_idx, frame_num, story=None):
    bg = BACKGROUNDS[scene_idx % len(BACKGROUNDS)]

    arr = np.array(img)
    _draw_gradient_background(arr, bg)
    img.paste(Image.fromarray(arr.astype(np.uint8)))

    draw = ImageDraw.Draw(img)

    sx = W - 85 + int(5 * math.sin(frame_num / 40))
    sy = 55
    draw.ellipse([sx, sy, sx+70, sy+70], fill=bg["sun"], outline=bg["sun2"], width=2)
    scx, scy = sx+35, sy+35
    for angle in range(0, 360, 45):
        rad = math.radians(angle)
        draw.line([scx+int(40*math.cos(rad)), scy+int(40*math.sin(rad)),
                   scx+int(54*math.cos(rad)), scy+int(54*math.sin(rad))],
                  fill=bg["sun"], width=3)

    cx_base = int((frame_num * 0.25) % (W + 240)) - 120
    _draw_cloud(draw, cx_base,        100, scale=1.0)
    _draw_cloud(draw, cx_base + 280,   62, scale=0.60)
    _draw_cloud(draw, cx_base - 180,  140, scale=0.45)

    for x in range(0, W, 38):
        for dx in range(-8, 9, 5):
            draw.line([x+dx, GROUND_Y, x+dx+3,
                       GROUND_Y - int(14 + 5*math.sin(x))],
                      fill="#2E7D32", width=2)

    for fx in range(50, W-40, 95):
        _draw_flower(draw, fx, GROUND_Y + 18)

    if story is not None:
        img_rgba = img.convert("RGBA")
        _draw_bg_extras(img_rgba, story, GROUND_Y + 30, alpha_frac=0.38)
        img.paste(img_rgba.convert("RGB"))
        draw = ImageDraw.Draw(img)

    bird_phase = frame_num / 18.0
    _draw_garden_tree(draw, TREE_X, GROUND_Y, scale=1.0, bird_phase=bird_phase)

    return draw


def _draw_cloud(draw, x, y, scale=1.0):
    s = scale
    for ox, oy, r in [(0,0,int(24*s)), (int(22*s),-int(7*s),int(30*s)),
                      (int(52*s),0,int(24*s)), (int(78*s),int(4*s),int(18*s))]:
        draw.ellipse([x+ox-r, y+oy-r, x+ox+r, y+oy+r],
                     fill="white", outline="#D8D8D8", width=1)


def _draw_flower(draw, x, y):
    cols = ["#FF80AB","#FFCC02","#80DEEA","#EF9A9A","#B39DDB"]
    col  = cols[(x // 95) % len(cols)]
    for angle in range(0, 360, 60):
        rad = math.radians(angle)
        px2 = x+int(8*math.cos(rad)); py2 = y+int(8*math.sin(rad))
        draw.ellipse([px2-5, py2-5, px2+5, py2+5], fill=col)
    draw.ellipse([x-4, y-4, x+4, y+4], fill="#FDD835")


def _draw_heart(draw, cx, cy, size):
    if size <= 0: return
    s = max(1, size)
    draw.ellipse([cx-s, cy-s, cx, cy+s//2], fill="#FF4081")
    draw.ellipse([cx, cy-s, cx+s, cy+s//2], fill="#FF4081")
    draw.polygon([(cx-s,cy+s//3),(cx+s,cy+s//3),(cx,cy+int(1.6*s))], fill="#FF4081")


# ─────────────────────────────────────────────────────────────────────────────
# SPEECH BUBBLE
# ─────────────────────────────────────────────────────────────────────────────
def draw_speech_bubble_layer(text, speaker_name, appear_progress=1.0):
    if appear_progress <= 0:
        return None
    lines    = _wrap_text(text, max_chars=30)
    font     = _get_font(22)
    name_fnt = _get_font(20, bold=True)
    pad, lh  = 16, 28
    bw = W - 52
    bh = len(lines)*lh + pad*2 + 32

    bx = 26
    by = H - bh - 55

    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d     = ImageDraw.Draw(layer)
    a     = int(245 * min(1.0, appear_progress))

    d.rounded_rectangle([bx, by, bx+bw, by+bh],
                         radius=20, fill=(255,255,255,a), outline=(80,80,80,a), width=2)
    tab_w = max(80, len(speaker_name)*12 + 24)
    d.rounded_rectangle([bx+12, by-28, bx+12+tab_w, by+8],
                         radius=10, fill=(60,60,60,a))
    d.text((bx+12+tab_w//2, by-10), speaker_name.title(),
           fill=(255,255,255,a), font=name_fnt, anchor="mm")
    for i, ln in enumerate(lines):
        d.text((bx+pad, by+pad+10+i*lh), ln, fill=(30,30,30,a), font=font)
    return layer


# ─────────────────────────────────────────────────────────────────────────────
# AUDIO AMPLITUDE
# ─────────────────────────────────────────────────────────────────────────────
def _get_amplitudes(audio_path, fps=FPS):
    if not HAS_SCIPY:
        try:
            clip = AudioFileClip(audio_path)
            n    = int(clip.duration * fps)
            clip.close()
        except Exception:
            n = fps*4
        return [0.5]*n

    wav_path = audio_path.rsplit(".",1)[0] + "_amp.wav"
    try:
        subprocess.run(["ffmpeg","-y","-i",audio_path,"-ar","22050","-ac","1",wav_path],
                       capture_output=True, timeout=30)
        rate, data = wavfile.read(wav_path)
        if len(data.shape)>1: data = data.mean(axis=1)
        data  = data.astype(float)
        chunk = max(1, rate//fps)
        amps  = [float(np.abs(data[i:i+chunk]).mean()) for i in range(0,len(data),chunk)]
        mx    = max(amps) if amps else 1.0
        return [a/mx for a in amps]
    except Exception as e:
        print(f"    ⚠️  Amplitude analysis failed ({e})")
        return [0.5]*100


# ─────────────────────────────────────────────────────────────────────────────
# SCENE RENDERING
# ─────────────────────────────────────────────────────────────────────────────
VEG1_X = W // 4 - 10
VEG2_X = W // 2 + 30
CHAR_Y  = GROUND_Y + 60


def render_dialogue_scene(story, line_data, scene_idx, fps=FPS):
    speaker    = line_data["speaker"].strip().lower()
    text       = line_data["text"]
    veg1, veg2 = story["veg1"], story["veg2"]
    is_veg1    = (speaker == veg1)

    audio_clip = AudioFileClip(line_data["path"])
    duration   = max(audio_clip.duration, 2.5)
    n_frames   = int(duration * fps)
    amplitudes = _get_amplitudes(line_data["path"], fps)
    frames     = []

    for f in range(n_frames):
        t = f / fps

        base = Image.new("RGB", (W, H))
        _draw_background(base, scene_idx, f, story=story)
        draw = ImageDraw.Draw(base)

        bob1  = int(10 * math.sin(t*(2.8 if is_veg1 else 1.5)))
        bob2  = int(8  * math.sin(t*(1.5 if is_veg1 else 2.8) + 0.7))
        talk1 = int(4  * math.sin(t*9)) if is_veg1     else 0
        talk2 = int(4  * math.sin(t*9)) if not is_veg1 else 0

        amp_idx    = min(f, len(amplitudes)-1)
        mouth_open = amplitudes[amp_idx] > 0.25

        draw_character(draw, veg1, VEG1_X, CHAR_Y+bob1+talk1,
                       scale=1.1, mouth_open=mouth_open and is_veg1, talking=is_veg1)
        draw_character(draw, veg2, VEG2_X, CHAR_Y+bob2+talk2,
                       scale=1.1, mouth_open=mouth_open and not is_veg1, talking=not is_veg1)

        hx = VEG1_X if is_veg1 else VEG2_X
        hy = CHAR_Y + (bob1+talk1 if is_veg1 else bob2+talk2)
        draw.ellipse([hx-85, hy-85, hx+85, hy+85], outline="#FFD700", width=4)

        if t > 0.5:
            hrt_x = (VEG1_X+VEG2_X)//2
            hrt_y = CHAR_Y - 200 - int(30*((t*0.8) % 1.0))
            hrt_a = 1.0 - ((t*0.8) % 1.0)
            _draw_heart(draw, hrt_x, hrt_y, int(16*hrt_a))

        appear = min(1.0, max(0.0, (t-0.2)/0.35))
        bubble = draw_speech_bubble_layer(text, speaker, appear)
        if bubble:
            base = base.convert("RGBA")
            base = Image.alpha_composite(base, bubble)
            base = base.convert("RGB")

        frames.append(np.array(base))

    return frames, audio_clip


def render_moral_scene(story, fps=FPS, duration=4.5):
    scene_idx  = len(story["dialogues"]) - 1
    frames     = []
    n          = int(duration*fps)
    font_hdr   = _get_font(28, bold=True)
    font_moral = _get_font(22)
    moral_lines = _wrap_text(story["moral"], max_chars=28)

    for f in range(n):
        t    = f / fps
        base = Image.new("RGB", (W, H))
        _draw_background(base, scene_idx, f, story=story)
        draw = ImageDraw.Draw(base)

        bob1 = int(6*math.sin(t*1.8))
        bob2 = int(6*math.sin(t*1.8+1.0))
        draw_character(draw, story["veg1"], VEG1_X, CHAR_Y+bob1, scale=1.1)
        draw_character(draw, story["veg2"], VEG2_X, CHAR_Y+bob2, scale=1.1)

        for hrt_x, hrt_base, spd in [
            ((VEG1_X+VEG2_X)//2-25, CHAR_Y-140, 0.9),
            ((VEG1_X+VEG2_X)//2+25, CHAR_Y-170, 1.3),
            ((VEG1_X+VEG2_X)//2,    CHAR_Y-110, 1.1),
        ]:
            hy_ = hrt_base - int(40*((t*spd) % 1.0))
            ha  = 1.0 - ((t*spd) % 1.0)
            _draw_heart(draw, hrt_x, hy_, int(15*ha))

        fade = min(1.0, t/0.9)
        if fade > 0:
            panel_h = len(moral_lines)*30 + 76
            layer   = Image.new("RGBA", (W,H), (0,0,0,0))
            md      = ImageDraw.Draw(layer)
            ba      = int(215*fade); ta = int(255*fade)
            md.rounded_rectangle([20,20,W-20,20+panel_h], radius=22,
                                  fill=(255,215,0,ba), outline=(180,130,0,ba), width=3)
            md.text((W//2,46), "✨  Moral of the Story  ✨",
                    fill=(100,30,120,ta), font=font_hdr, anchor="mm")
            for i, ln in enumerate(moral_lines):
                md.text((W//2, 82+i*30), ln,
                        fill=(60,20,80,ta), font=font_moral, anchor="mm")
            base = base.convert("RGBA")
            base = Image.alpha_composite(base, layer)
            base = base.convert("RGB")

        frames.append(np.array(base))

    return frames


# ─────────────────────────────────────────────────────────────────────────────
# VIDEO ASSEMBLY  (with 3 retries)
# ─────────────────────────────────────────────────────────────────────────────
def _do_assemble(story, audio_files, base_name, fps):
    """Inner assembly logic — called up to MAX_RETRIES times."""
    all_clips = []
    for i, line_data in enumerate(audio_files):
        print(f"  🎬 Scene {i+1}/{len(audio_files)}: "
              f"{line_data['speaker']} — {line_data['text'][:50]}...")
        frames, audio_clip = render_dialogue_scene(story, line_data, i, fps)
        all_clips.append(ImageSequenceClip(frames, fps=fps).set_audio(audio_clip))

    print("  🎬 Rendering moral scene...")
    moral_frames = render_moral_scene(story, fps)
    all_clips.append(ImageSequenceClip(moral_frames, fps=fps))

    print("  🔗 Concatenating…")
    final = concatenate_videoclips(all_clips, method="compose")

    if BG_MUSIC_PATH and os.path.exists(BG_MUSIC_PATH):
        print("  🎵 Adding background music…")
        from moviepy.editor import AudioFileClip as AFC
        music = AFC(BG_MUSIC_PATH).volumex(0.15).audio_loop(duration=final.duration)
        final = final.set_audio(
            CompositeAudioClip([final.audio, music]) if final.audio else music
        )

    out_path = os.path.join(OUTPUT_DIR, base_name + ".mp4")
    print(f"  💾 Writing {out_path} …")
    final.write_videofile(out_path, fps=fps, codec="libx264",
                          audio_codec="aac", logger=None)
    final.close()
    return out_path


def assemble_video(story, audio_files, base_name, fps=FPS):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"\n  🎬 Video assembly attempt {attempt}/{MAX_RETRIES}...")
            path = _do_assemble(story, audio_files, base_name, fps)
            print(f"  ✅ Video ready: {path}")
            return path
        except Exception as e:
            print(f"  ❌ Video attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                print(f"  ⏳ Retrying in 3 seconds…")
                time.sleep(3)

    raise RuntimeError(f"Video assembly failed after {MAX_RETRIES} attempts.")


# ─────────────────────────────────────────────────────────────────────────────
# GOOGLE DRIVE UPLOAD
# ─────────────────────────────────────────────────────────────────────────────
def _drive_upload(file_path, folder_id, mime="video/mp4"):
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        from google.auth.transport.requests import Request
        import pickle, base64, json, tempfile
    except ImportError:
        print("  ⚠️  pip install google-api-python-client google-auth-oauthlib")
        return None

    SCOPES = ["https://www.googleapis.com/auth/drive.file"]
    creds  = None

    # ── Try loading token from env var (GitHub Actions) ──────────────────────
    token_b64 = os.environ.get("GDRIVE_TOKEN_BASE64", "")
    if token_b64:
        try:
            creds = pickle.loads(base64.b64decode(token_b64))
            print("  🔑 Loaded Drive token from environment.")
        except Exception as e:
            print(f"  ⚠️  Could not decode GDRIVE_TOKEN_BASE64: {e}")

    # ── Fall back to token.pickle on disk (local dev) ─────────────────────────
    if creds is None and os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as fh:
            creds = pickle.load(fh)
        print("  🔑 Loaded Drive token from token.pickle.")

    if creds is None:
        print("  ❌ No Drive credentials found. Skipping upload.")
        return None

    # ── Refresh if expired ────────────────────────────────────────────────────
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            # Need credentials.json to refresh — load from env or disk
            creds_json = os.environ.get("GDRIVE_CREDENTIALS_JSON", "")
            if creds_json:
                tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
                tmp.write(creds_json)
                tmp.close()
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = tmp.name

            try:
                creds.refresh(Request())
                print("  🔄 Drive token refreshed.")
            except Exception as e:
                print(f"  ❌ Token refresh failed: {e}. Skipping upload.")
                return None
        else:
            print("  ❌ Token invalid and cannot refresh. Skipping upload.")
            return None

    # ── Upload ────────────────────────────────────────────────────────────────
    try:
        svc   = build("drive", "v3", credentials=creds)
        meta  = {"name": os.path.basename(file_path),
                 "parents": [folder_id] if folder_id else []}
        media = MediaFileUpload(file_path, mimetype=mime, resumable=True)
        up    = svc.files().create(body=meta, media_body=media,
                                   fields="id,webViewLink").execute()
        link  = up.get("webViewLink")
        print(f"  ☁️  Uploaded: {link}")
        return link
    except Exception as e:
        print(f"  ❌ Drive upload failed: {e}")
        return None

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    print("\n🥕  Animated Vegetable Story Pipeline  (Reel Edition 720×1280 v5 — google.genai)")
    print("=" * 78)

    if not HAS_MOVIEPY:
        print("❌  MoviePy required:\n"
              "    pip install moviepy pillow numpy scipy edge-tts google-genai")
        return

    base_name = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"\n   Output base name: {base_name}")

    print("\n📖 Step 1 — Story (Gemini)…")
    story = generate_story()
    print(f"   Characters: {story['veg1'].title()} & {story['veg2'].title()}")
    for d in story["dialogues"]: print(f"   {d}")
    print(f"   MORAL: {story['moral']}")

    print("\n🏷️  Step 2 — Metadata (Gemini)…")
    meta      = generate_metadata(story)
    json_path = save_metadata(story, meta, base_name)
    print(f"   YouTube title: {meta['youtube_title']}")

    print("\n🎙️  Step 3 — Audio…")
    audio_files = generate_all_audio(story)

    print("\n🎬 Step 4 — Render & assemble…")
    video_path = assemble_video(story, audio_files, base_name)

    if UPLOAD_TO_DRIVE:
        print("\n☁️  Step 5 — Drive upload…")
        if GOOGLE_DRIVE_FOLDER:
            _drive_upload(video_path, GOOGLE_DRIVE_FOLDER, mime="video/mp4")
        if METADATA_DRIVE_FOLDER:
            _drive_upload(json_path, METADATA_DRIVE_FOLDER, mime="application/json")

    print(f"\n✅  Done!")
    print(f"   Video    → {video_path}")
    print(f"   Metadata → {json_path}\n")


if __name__ == "__main__":
    main()