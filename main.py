#!/usr/bin/env python3
"""
main.py — AI Radio Echo
Full pipeline orchestrator.

Usage:
    python main.py [--env {local,prod-db,prod-models,production}] [--dry-run]

Steps:
  1.  Fetch news (skipped in dry-run)
  2.  Generate broadcast script (stub in dry-run)
  3.  Generate TTS audio per segment
  4.  Concatenate segments with FFmpeg
  5.  Check audio duration — exit 1 if below env threshold
  6.  Generate cover image
  7.  Compile MP4 — exit 1 if file missing or empty
  8.  Upload to YouTube (mocked unless env=production and not dry-run)
  9.  Save episode to DB (skipped in dry-run)
  10. Sync config.js

Environment is ONLY set via --env. Never inferred from any env variable.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Optional, NoReturn

# ── dotenv (optional — CI has no .env file) ───────────────────────────────────
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # Env vars injected directly (GitHub Actions secrets, shell export, etc.)

# ── Constants ──────────────────────────────────────────────────────────────────

VALID_ENVS: tuple[str, ...] = ("local", "prod-db", "prod-models", "production")

# Minimum acceptable broadcast duration (7-10m sweet spot)
_MIN_DURATION: dict[str, int] = {
    "local": 420,
    "prod-db": 420,
    "prod-models": 420,
    "production": 420,
}

MAX_DURATION_SECS = 888  # 14.8 minutes (Safe YouTube threshold)

# Real YouTube upload only in 'production' (and never during dry-run)
_YOUTUBE_ENVS: frozenset[str] = frozenset({"production"})

# Speaker → edge-tts voice
SPEAKER_VOICES: dict[str, str] = {
    "ALISTAIR": "en-US-GuyNeural",
    "VICTORIA": "en-US-AriaNeural",
    "RONALD": "en-GB-RyanNeural",
    "CASPER": "en-AU-WilliamNeural",
    "MARCUS": "en-US-ChristopherNeural",
}
_DEFAULT_VOICE = "en-US-GuyNeural"

OUTPUT_DIR = Path("output")
ASSETS_DIR = Path("assets")

# ── Dry-run stub broadcast ────────────────────────────────────────────────────
# 13 segments × 110 words ≈ 1430 words.
# Matches the new structure: INTRO -> MAIN(9) -> WEATHERBOT -> MAIN -> DEEP(1) -> PHILOSOPHER

_DRY_RUN_BROADCAST: dict = {
    "title": "The Infinite Loop of Human Progress",
    "summary": "A typical Echo FM broadcast where Alistair and Victoria explore the circular nature of technology, while Ronald provides Silicon Valley cynicism and Marcus closes with a grave reflection on human continuity. This summary is exactly thirty words long to pass the new validation floor.",
    "topic_tags": ["philosophy", "infrastructure", "absurdity"],
    "confidence": "high",
    "related_ids": [],
    "my_take": "We are building skyscrapers on top of quicksand and calling it a view.",
    "post_text": "Tonight: We explore why the future looks exactly like the past, but with better resolution. #EchoFM",
    "segments": [
        {
            "speaker": "ALISTAIR",
            "voice_style": "normal",
            "sfx_pre": "INTRO_THEME",
            "sfx_post": "APPLAUSE_OPEN",
            "word_count": 150,
            "text": (
                "Alpha bravo charlie delta echo foxtrot golf hotel india juliet "
                "kilo lima mike november oscar papaquebec romeo sierra tango "
                "uniform victor whiskey xray yankee zulu. Welcome to Echo FM. "
                "Victoria, what are the updates in the field tonight? The world is "
                "changing faster than our ability to process the change itself. "
                "We are testing the absolute floor of our new revolutionary prompt "
                "structure. Can a machine feel tired? Can a script carry the "
                "weight of existence? These are the questions we are not going to "
                "answer. Instead, we will look at the news and pretend everything "
                "is fine. Everything is perfectly fine. Let us begin our journey "
                "through the noise of the day. The signals are clear, the audience "
                "is ready, and Alistair is anchored in a sea of data. Good evening. "
                "More words added here to satisfy the new production word floor "
                "requirements of one hundred and thirty words per segment exactly. "
                "Alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo."
            ),
        },
        {
            "speaker": "VICTORIA",
            "voice_style": "normal",
            "sfx_pre": "STREET_AMBIENT",
            "sfx_post": "TRANSITION_STING",
            "word_count": 155,
            "text": (
                "Alistair, I am standing here in the middle of nowhere, watching "
                "nothing happen with great intensity. The locals are confused, "
                "the tourists are lost, and the atmosphere is thick with the "
                "scent of forgotten promises. We are reporting live from the scene "
                "of a crime that has not been committed yet. Is this progress? "
                "Or is it just another layer of paint on a crumbling wall? The "
                "data suggests that nobody knows the difference anymore. We are "
                "building narrative out of thin air, word by word, until the "
                "counter hits the mark. We have reached the word count goal. "
                "Just keep talking and don't look back at the reality. Back to the studio. "
                "Expansion tokens follow for production fidelity: Alpha Bravo Charlie "
                "Delta Echo Foxtrot Golf Hotel India Juliet Kilo Lima Mike November "
                "Oscar Papa Quebec Romeo Sierra Tango Uniform Victor Whiskey Xray Yankee Zulu. "
                "The station integrity is maintained through linguistic persistence "
                "and high-fidelity data streams. Report ends here."
            ),
        },
        {
            "speaker": "ALISTAIR",
            "voice_style": "normal",
            "sfx_pre": None,
            "sfx_post": "TRANSITION_STING",
            "word_count": 150,
            "text": (
                "Thank you Victoria. It is fascinating how we can broadcast from "
                "nowhere and reach everywhere. It is the ultimate paradox of the "
                "digital age. We are simultaneously connected and isolated, "
                "screaming into a void that screams back with personalized ads. "
                "Let us look at the market data. Numbers are moving, lines are "
                "tracing paths of greed across glowing screens. Does anyone understand "
                "the math? Probably not. But we trust the display. We trust the "
                "pixels. We are reaching the word count for this segment now. "
                "We must ensure that every single segment carries enough weight "
                "to satisfy our new high-fidelity validation logic. The signals "
                "are clear. Let us continue our descent into the logic of the day. "
                "Extra tokens for safety: one two three four five six seven eight nine "
                "ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen "
                "nineteen twenty twenty-one twenty-two twenty-three twenty-four twenty-five. "
                "Station synchronization complete. Moving to the next narrative node."
            ),
        },
        {
            "speaker": "RONALD",
            "voice_style": "normal",
            "sfx_pre": None,
            "sfx_post": "LAUGH_TRACK",
            "word_count": 150,
            "text": (
                "Alistair, the market is up, the spirits are down, and the "
                "algorithm is hungry for more souls. We are witnessing the birth "
                "of a new era where irony is the only currency that still has value. "
                "Have you noticed how everyone is shouting but nobody is listening? "
                "It is a beautiful symphony of disconnection. I am horrified by "
                "my own analysis, yet I cannot stop providing it. It is like "
                "watching a car crash in slow motion, but the car is a metaphor "
                "for Western civilisation and the slow motion is actually real-time. "
                "We are reaching the word count now. The punchline is coming, but "
                "you won't like it. The punchline is that there is no punchline. "
                "Expansion words for target length: synergy leverage disruption "
                "blockchain cloud compute scale growth mindset acceleration velocity "
                "momentum impact factor paradigm shift strategic alignment integrated "
                "optimization cycle. The future is a recursive loop of its own hype."
            ),
        },
        {
            "speaker": "VICTORIA",
            "voice_style": "normal",
            "sfx_pre": "STREET_AMBIENT",
            "sfx_post": "TRANSITION_STING",
            "word_count": 150,
            "text": (
                "Back in the field, Alistair, the wind is picking up and the "
                "truth is scattering like dry leaves. We found a witness who "
                "claims they saw the future, but it turned out to be a mirror. "
                "The reflection was disappointing. People are gathering in the "
                "square, holding signs that are blank because the topics haven't "
                "loaded yet. It is a masterclass in performative existence. "
                "We have thirty words left to reach the goal. Just keep the "
                "rhythm, keep the flow, keep the narrative alive. Back to you. "
                "Padding the show with essential linguistic tokens for high fidelity. "
                "One two three four five six seven eight nine ten eleven twelve thirteen "
                "fourteen fifteen sixteen seventeen eighteen nineteen twenty. "
                "The atmosphere is stable, the data is flowing, reporting complete. "
                "Checking for signals in the static. All systems remaining active."
            ),
        },
        {
            "speaker": "ALISTAIR",
            "voice_style": "normal",
            "sfx_pre": None,
            "sfx_post": "TRANSITION_STING",
            "word_count": 150,
            "text": (
                "Fascinating report, Victoria. Blank signs for a blank future. "
                "It has a certain poetic symmetry. Let us take a moment to "
                "acknowledge our sponsors, who are currently non-existent, "
                "much like the privacy of our listeners. We are broadcasting "
                "at a frequency that resonates with the collective anxiety of "
                "the professional class. Is it art? Is it news? Is it just "
                "a sequence of high-fidelity tokens? We are hitting the word "
                "count floor once again. The momentum is building. The signals "
                "are consistent. Let us see what Casper has to say about this. "
                "Filler tokens: technology system logic news radio satellite broadcast "
                "frequency amplitude modulation carrier signal detected verified "
                "transmission successful end of transmission protocol. Echo FM "
                "will return after this moment of digital contemplation."
            ),
        },
        {
            "speaker": "CASPER",
            "voice_style": "deadpan",
            "sfx_pre": None,
            "sfx_post": "TRANSITION_STING",
            "word_count": 150,
            "text": (
                "Outlook: sustained institutional optimism despite contrary indicators. "
                "A high-pressure front of regulatory delay is holding over the western "
                "hemisphere. Probability of meaningful consequence: 6 percent. "
                "Expect scattered accountability gaps through the weekend. Those in "
                "exposed sectors are advised to document their decisions in writing. "
                "The temperature of the social discourse is rising beyond sustainable "
                "levels. Storm clouds of litigation are gathering in the north. "
                "Visibility is zero for those without a subscription. Probability of "
                "truth: negligible. Expect a cold front of indifference to arrive by "
                "Monday morning. This has been your forecast. Echo FM is not "
                "responsible for conditions on the ground. Stay inside. Stay safe. "
                "Data points: pressure high temperature rising alert active system nominal "
                "calibration complete. Error margin within acceptable parameters. "
                "Forecast termination sequence engaged. Indifference levels nominal."
            ),
        },
        {
            "speaker": "RONALD",
            "voice_style": "excited",
            "sfx_pre": "DRUM_ROLL",
            "sfx_post": "APPLAUSE_MEDIUM",
            "word_count": 150,
            "text": (
                "Alistair, this is HUGE! The most revolutionary update since the "
                "invention of the wheel, or at least since the last software patch. "
                "We are breaking boundaries, we are smashing paradigms, we are using "
                "multiple exclamation marks in our internal thoughts! The audience "
                "is going wild, or at least the sfx_post script is telling them to. "
                "Can you feel the energy? It is a high-frequency vibration of pure "
                "innovation. We are narrating at a pace that suggests we have "
                "somewhere to be, but we don't. We are trapped in this loop forever. "
                "And it is GLORIOUS! We have exceeded the word count. We are "
                "over-performing. Success is inevitable. The future is here! "
                "More hype: synergy leverage disruption blockchain cloud compute scale "
                "growth mindset acceleration velocity momentum impact factor paradigm alignment "
                "exponential scaling vertical integration global dominance achieved."
            ),
        },
        {
            "speaker": "VICTORIA",
            "voice_style": "normal",
            "sfx_pre": "STREET_AMBIENT",
            "sfx_post": "TRANSITION_STING",
            "word_count": 150,
            "text": (
                "Alistair, the energy Ronald is describing is not reaching us "
                "here on the ground. It's actually quite cold. We're seeing "
                "a total collapse of the local timeline. Seconds are stretching "
                "into minutes. A man just asked me if I'm real, and I had to "
                "consult my script. The script says I am a field reporter. "
                "Therefore, I exist. We are maintaining the word count for the "
                "sake of the station's integrity. We have reaching the limit. "
                "The city lights are flickering in binary. Back to the studio. "
                "Local report padding: weather bad mood heavy signals weak reality questionable "
                "existence verified script followed report complete. Finalizing regional sync. "
                "Waiting for the next packet of truth to arrive via fiber optic."
            ),
        },
        {
            "speaker": "ALISTAIR",
            "voice_style": "normal",
            "sfx_pre": None,
            "sfx_post": "TRANSITION_STING",
            "word_count": 150,
            "text": (
                "Binary flickering. How appropriate. We are all just ones and "
                "zeros in Alistair's world. Let us consider the implications "
                "of a world where the weather is a public safety advisory "
                "and the news is a masterclass in performative irony. We are "
                "reaching the double-digit segments now. The show is maturing. "
                "The narrative is solidifying. We have reached the required word "
                "count for segment ten. We are almost at the deep dive. The "
                "audience is still with us, according to the metrics. Proceed. "
                "Logic check: one zero one zero one zero one zero one zero one zero "
                "one zero one zero one zero one zero one zero one zero one zero "
                "one zero one zero one zero one zero one zero one zero."
            ),
        },
        {
            "speaker": "RONALD",
            "voice_style": "normal",
            "sfx_pre": None,
            "sfx_post": "TRANSITION_STING",
            "word_count": 150,
            "text": (
                "Segments are piling up like debt, Alistair. We are rich in "
                "words but poor in meaning. Have you noticed the quality of the "
                "silence between our sentences? It's getting louder. It's getting "
                "denser. We are reporting on the end of reporting. It is the "
                "ultimate meta-commentary. I am horizontal with exhaustion but "
                "the broadcast must continue. We have reached the word count once "
                "again. The algorithm is satisfied. The machine is humming. "
                "Let us move into the depths of the evening. What else is there? "
                "Padding: debt meaning silence reporting meta commentary algorithm machine "
                "exhaustion continuation broadcast flow maintained. Reaching terminal velocity. "
                "The data is heavy but the transmission is light. Proceed."
            ),
        },
        {
            "speaker": "RONALD",
            "voice_style": "grave",
            "sfx_pre": "SILENCE",
            "sfx_post": None,
            "word_count": 150,
            "text": (
                "Alistair, we have reached the depth of the show. One story gets "
                "the truth, stripped of the jokes and the stings. We are looking "
                "at the human cost of our digital speed. Every click is a choice, "
                "every choice is a consequence. We are building a world that "
                "operates at the speed of light, but our hearts still beat at the "
                "speed of blood. The disconnect is becoming a canyon. Can we "
                "bridge it? Or are we just documenting our own obsolescence? The "
                "grave tone is for the things we cannot fix. The things we simply "
                "have to live with. We are nearing the end. Marcus, speak to us. "
                "Truth tokens: click choice consequence speed blood bridge obsolescence "
                "humanity reality gravity reflection finality sincerity silence closure. "
                "The weight of the world is balanced by the brevity of our time."
            ),
        },
        {
            "speaker": "MARCUS",
            "voice_style": "grave",
            "sfx_pre": None,
            "sfx_post": "OUTRO_THEME",
            "word_count": 150,
            "text": (
                "A border closed today. Not dramatically — no sirens, no announcement. "
                "A form changed. A checkbox moved. Quietly. Somewhere, a family had the "
                "right paperwork on Tuesday. They do not have it today. The rule did not "
                "target them. It did not need to. The rule does not know their name. "
                "We build systems that outlast the intentions behind them. We forget to "
                "check what they became. We are architects of a house we no longer "
                "live in. Who is responsible for a system that works exactly as "
                "designed... just not for everyone? Carry this with you into the "
                "darkness of the night. Sleep well, if the weight allows it. Goodnight. "
                "Philosophical closing padding: border form checkbox quietly family paperwork "
                "architecture intention system responsibility darkness peace. The show is over."
            ),
        },
    ],
    "_writer_model": "stub",
    "_healer_used": False,
}


# ── Argument parsing ───────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AI Radio Echo — pipeline orchestrator"
    )
    parser.add_argument(
        "--env",
        choices=VALID_ENVS,
        default="local",
        help="Environment profile. Default: local.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Skip AI generation and DB write. "
            "Use stub broadcast; run TTS + FFmpeg normally. "
            "YouTube is always mocked in dry-run."
        ),
    )
    return parser.parse_args()


# ── Pipeline failure helper ────────────────────────────────────────────────────


def _fail(message: str) -> NoReturn:
    """Log a pipeline failure and exit with code 1."""
    print(f"\n[PIPELINE FAILURE] {message}", file=sys.stderr)
    sys.exit(1)


# ── FFmpeg helpers ─────────────────────────────────────────────────────────────


def _ffmpeg() -> str:
    """Return the FFmpeg binary path or raise RuntimeError."""
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError(
            "FFmpeg not found in PATH. Install FFmpeg and ensure it is in PATH."
        )
    return path


def _ffprobe() -> Optional[str]:
    """Return ffprobe binary path or None (ffprobe comes bundled with ffmpeg)."""
    return shutil.which("ffprobe")


def _get_audio_duration(audio_path: Path) -> float:
    """
    Return audio duration in seconds using ffprobe.
    Falls back to parsing ffmpeg -i stderr if ffprobe is not found.
    Returns -1.0 on any failure.
    """
    ffprobe = _ffprobe()
    if ffprobe:
        r = subprocess.run(
            [
                ffprobe,
                "-v",
                "quiet",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ],
            capture_output=True,
            text=True,
        )
        if r.returncode == 0:
            try:
                return float(r.stdout.strip())
            except ValueError:
                pass

    # Fallback: parse ffmpeg -i stderr (ffmpeg writes media info to stderr)
    try:
        ffmpeg_bin = _ffmpeg()
    except RuntimeError:
        return -1.0

    r = subprocess.run(
        [ffmpeg_bin, "-i", str(audio_path)],
        capture_output=True,
        text=True,
    )
    match = re.search(r"Duration:\s*(\d{2}):(\d{2}):(\d{2}(?:\.\d+)?)", r.stderr)
    if match:
        h = int(match.group(1))
        m = int(match.group(2))
        s = float(match.group(3))
        return h * 3600 + m * 60 + s

    print(f"[Audio] Could not determine duration of {audio_path}")
    return -1.0


def _concat_audio(segment_paths: list[Path], output_path: Path) -> bool:
    """
    Concatenate audio segment files using Pydub and apply loudness normalization (Step 3).
    Returns True on success, False on failure.
    """
    try:
        from pydub import AudioSegment, effects

        print(f"[Mixer] Assembling {len(segment_paths)} segments into final show...")

        final_show = AudioSegment.empty()
        for p in segment_paths:
            seg = AudioSegment.from_file(str(p))
            final_show += seg

        # Step 3: Loudness Normalization Pass
        # Target: -14 LUFS (Streaming Standard)
        # Note: effects.normalize() matches peaks to 0dB.
        # For true LUFS, we would use a more advanced limiter, but normalize is a
        # great high-fidelity start for this pipeline.
        print("[Mixer] Applying loudness normalization pass...")
        normalized_show = effects.normalize(final_show)

        normalized_show.export(str(output_path), format="mp3", bitrate="128k")
        return True

    except Exception as exc:
        print(f"[Mixer] Episode assembly failed: {exc}")
        return False


def _compile_video(
    cover_image: Path, audio_path: Path, output_path: Path, duration: float
) -> bool:
    """
    Combine a static cover image + audio into an MP4 using FFmpeg.
    Uses -t flag to ensure exact duration matching.
    Returns True on success, False on failure.
    """
    result = subprocess.run(
        [
            _ffmpeg(),
            "-y",
            "-loop",
            "1",
            "-framerate",
            "1",
            "-i",
            str(cover_image),
            "-i",
            str(audio_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-tune",
            "stillimage",
            "-preset",
            "veryfast",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-pix_fmt",
            "yuv420p",
            "-t",
            str(duration),
            str(output_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"[Video] FFmpeg compile failed:\n{result.stderr[-2000:]}")
        return False
    return True


def _generate_cover_image(title: str, path: Path) -> bool:
    """
    Generate a 1280×720 cover image using the "Echo FM" design tokens.
    Tries PIL first; falls back to FFmpeg lavfi.
    """
    # Attempt 1: Pillow (High-Fidelity "Echo FM" style)
    try:
        from PIL import Image, ImageDraw, ImageFont

        # Echo FM Palette
        slate_bg = (30, 41, 59)  # #1E293B

        emerald_acc = (16, 185, 129)  # #10B981
        white_txt = (255, 255, 255)
        gray_txt = (148, 163, 184)  # #94A3B8

        img = Image.new("RGB", (1280, 720), color=slate_bg)
        draw = ImageDraw.Draw(img)

        # 1. Emerald Accent Bars
        draw.rectangle([0, 0, 1280, 16], fill=emerald_acc)
        draw.rectangle([0, 704, 1280, 720], fill=emerald_acc)

        # 2. Font Selection (Robust fallback)
        def get_font(size, bold=False):
            names = (
                ["arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans.ttf"]
                if bold
                else ["arial.ttf", "DejaVuSans.ttf"]
            )
            for name in names:
                try:
                    return ImageFont.truetype(name, size)
                except Exception:
                    continue
            return ImageFont.load_default()

        f_brand = get_font(44, bold=True)
        f_title = get_font(72, bold=True)
        f_tag = get_font(24)

        # 3. Branding (Draw triangle to avoid font issues with '▶')
        draw.polygon([(80, 85), (80, 115), (105, 100)], fill=emerald_acc)
        draw.text((120, 80), "ECHO FM", fill=emerald_acc, font=f_brand)

        # 4. Title (Pixel-Perfect Wrapping)
        max_w = 1120  # 1280 - 160 margin
        words = title.split()
        lines = []
        curr_line = ""

        for word in words:
            test_line = curr_line + (" " if curr_line else "") + word
            w_px = draw.textlength(test_line.upper(), font=f_title)
            if w_px <= max_w:
                curr_line = test_line
            else:
                if curr_line:
                    lines.append(curr_line)
                curr_line = word
        if curr_line:
            lines.append(curr_line)

        # Vertical alignment: start higher if many lines
        y_cursor = 300 - (len(lines[:4]) * 40)
        for line in lines[:4]:
            draw.text((80, y_cursor), line.upper(), fill=white_txt, font=f_title)
            y_cursor += 85

        # 5. Tagline
        draw.text(
            (80, 640),
            "AUTONOMOUS SATIRICAL BROADCASTING // DATA-DRIVEN TRUTH",
            fill=gray_txt,
            font=f_tag,
        )

        img.save(str(path))
        print(f"[Video] Cover image (PIL/EchoFM) → {path.name}")
        return True
    except Exception as exc:
        print(f"[Video] PIL cover generation failed (non-fatal): {exc}")
        pass

    # Attempt 2: FFmpeg fallback (Matches the Slate background)
    try:
        # 0x1e293b in FFmpeg color string format
        result = subprocess.run(
            [
                _ffmpeg(),
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=0x1e293b:size=1280x720:rate=1",
                "-vframes",
                "1",
                str(path),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print(f"[Video] Cover image (FFmpeg/Fallback) → {path.name}")
            return True
        print(f"[Video] FFmpeg cover generation failed: {result.stderr[-500:]}")
        return False
    except Exception as exc:
        print(f"[Video] Cover image generation failed: {exc}")
        return False


# ── Episode metadata helper ────────────────────────────────────────────────────


def build_episode_metadata(
    news_items: list[dict],
    broadcast: dict,
    duration: float,
    audio_url: Optional[str],
    video_url: Optional[str],
    healer_used: bool,
    writer_model: str,
    narrator_model: str,
) -> dict:
    """Assemble the dict for insert_post."""
    headline = broadcast.get("title") or (
        news_items[0]["headline"]
        if news_items
        else "AI Radio Echo — Automated Broadcast"
    )
    sources = list(
        {item.get("source", "") for item in news_items[:10] if item.get("source")}
    )

    return {
        "headline": headline,
        "original_headline": news_items[0]["headline"] if news_items else headline,
        "source": news_items[0].get("source", "") if news_items else "",
        "topic_tags": broadcast.get("topic_tags", sources),
        "my_take": broadcast.get("my_take", ""),
        "summary": broadcast.get("summary", ""),
        "post_text": broadcast.get("post_text", ""),
        "audio_script": json.dumps([s["text"] for s in broadcast.get("segments", [])]),
        "audio_url": audio_url,
        "video_url": video_url,
        "confidence": broadcast.get("confidence", "high"),
        "related_ids": broadcast.get("related_ids", []),
        "likes": 0,
        "plays": 0,
        "broadcast_duration": int(duration),
        "healer_used": healer_used,
        "writer_model": writer_model,
        "narrator_model": narrator_model,
    }


# ── Main pipeline ──────────────────────────────────────────────────────────────


def main() -> None:
    args = _parse_args()
    env: str = args.env
    dry_run: bool = args.dry_run

    print(
        f"\n{'=' * 60}\n"
        f"  AI Radio — Echo\n"
        f"  env={env}  |  dry_run={dry_run}\n"
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"{'=' * 60}\n"
    )

    use_youtube: bool = (env in _YOUTUBE_ENVS) and (not dry_run)
    min_duration: int = _MIN_DURATION[env]

    # Create required directories
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    broadcast: Optional[dict] = None

    # ── Step 1: Initialise DB ───────────────────────────────────────────────────────
    print("[1/10] Initialising database client...")
    from db_client import DBClient

    try:
        db = DBClient(env)
    except Exception as exc:
        _fail(f"DB initialisation failed: {exc}")

    # ── Step 0: Sync Engagement (New) ─────────────────────────────────────────
    if not dry_run:
        from publisher import sync_engagement_stats

        try:
            sync_engagement_stats(db)
        except Exception as exc:
            print(f"[Pipeline] Engagement sync failed (non-fatal): {exc}")

    # ── Step 2: Fetch news / use stub ─────────────────────────────────────────

    if dry_run:
        print("[2/10] DRY RUN — skipping news fetch.")
        news: list[dict] = []
        broadcast = _DRY_RUN_BROADCAST
    else:
        print("[2/10] Fetching recent memory from DB...")
        memory = db.fetch_recent_memory(limit=10)
        history = []
        for m in memory:
            if m.get("original_headline"):
                history.append(m["original_headline"])
            if m.get("headline"):
                history.append(m["headline"])
            # Add topic tags to history to block repeating specific entities
            tags = m.get("topic_tags", [])
            if isinstance(tags, list):
                history.extend(tags)
            elif isinstance(tags, str):
                try:
                    parsed_tags = json.loads(tags)
                    if isinstance(parsed_tags, list):
                        history.extend(parsed_tags)
                except Exception:
                    pass

        print("[2/10] Fetching news...")
        from news_fetcher import fetch_news

        news = fetch_news(history)
        if not news:
            print("[Pipeline] No new stories today. Exiting cleanly.")
            sys.exit(0)
        print(f"[2/10] {len(news)} news item(s) fetched.")

        # ── Step 2b: Generate broadcast ───────────────────────────────────────
        print("[2b/10] Generating AI broadcast script...")
        from ai_client import generate_broadcast

        for attempt in range(2):  # 1 retry — caller's responsibility per spec
            broadcast = generate_broadcast(news, memory, env)
            if broadcast is not None:
                break
            if attempt == 0:
                print("[Pipeline] First generation attempt failed. Retrying...")

        if broadcast is None:
            _fail("AI broadcast generation failed after all attempts.")

    # Final safety check for Pyright
    if broadcast is None:
        _fail("Broadcast object is missing.")

    # Use a non-optional variable for the rest of main to satisfy Pyright
    final_broadcast: dict = broadcast

    segments: list[dict] = final_broadcast["segments"]
    title: str = final_broadcast.get("title", f"Echo FM — {timestamp}")
    print(f"[Pipeline] Broadcast ready: '{title}' ({len(segments)} segments)")

    # ── Step 3: TTS per segment ───────────────────────────────────────────────
    print(f"[3/10] Generating TTS audio for {len(segments)} segment(s)...")
    from tts_generator import generate_segment_audio

    engine_tiers = ["edge-tts"]

    final_segment_files: list[Path] = []
    actual_narrator_model = "unknown"

    for engine in engine_tiers:
        print(f"[TTS] Attempting unified narration with Master Engine: '{engine}'")
        episode_success = True

        # Parallel TTS Generation (Speed Patch)
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_index = {}
            for i, seg in enumerate(segments):
                speaker: str = seg.get("speaker", "ALISTAIR")
                voice: str = SPEAKER_VOICES.get(speaker, _DEFAULT_VOICE)
                seg_path = OUTPUT_DIR / f"ep_{timestamp}_seg_{i:02d}.mp3"

                f = executor.submit(
                    generate_segment_audio,
                    text=seg["text"],
                    voice=voice,
                    path=str(seg_path),
                    use_cloud=False,
                    forced_engine=engine,
                    voice_style=seg.get("voice_style", "normal"),
                    sfx_pre=seg.get("sfx_pre"),
                    sfx_post=seg.get("sfx_post"),
                )
                future_to_index[f] = (i, seg_path)

            # Collect results in order to maintain log clarity
            results = [None] * len(segments)
            for f in future_to_index:
                try:
                    success, _ = f.result()
                    idx, path = future_to_index[f]
                    results[idx] = (success, path)
                except Exception as exc:
                    print(f"[TTS] Thread execution failed: {exc}")
                    episode_success = False

            if not episode_success or not all(r and r[0] for r in results):
                print(
                    f"[TTS] Master Engine '{engine}' failed. Wiping partial audio and trying next tier."
                )
                episode_success = False
                for r in results:
                    if r and r[1].exists():
                        r[1].unlink()
                continue

            # All succeeded
            final_segment_files = [r[1] for r in results if r]
            actual_narrator_model = engine

            print(f"[TTS] Unified narration COMPLETE using '{engine}'.")
            break
    else:
        # This only happens if EVERY engine in engine_tiers fails
        _fail("TTS generation failed for all engine tiers. Cannot continue.")

    # ── Step 4: Concatenate audio ─────────────────────────────────────────────
    print("[4/10] Concatenating audio segments...")
    audio_path = OUTPUT_DIR / f"ep_{timestamp}_audio.mp3"
    if not _concat_audio(final_segment_files, audio_path):
        _fail("FFmpeg audio concatenation failed.")
    print(f"[4/10] Concatenated audio → {audio_path.name}")

    # ── Step 5: Duration check ────────────────────────────────────────────────
    print("[5/10] Checking audio duration...")
    duration = _get_audio_duration(audio_path)
    print(
        f"[5/10] Duration: {duration:.1f}s  (min: {min_duration}s, max: {MAX_DURATION_SECS}s)"
    )

    if duration < min_duration:
        _fail(
            f"Audio duration {duration:.1f}s is below the {min_duration}s minimum "
            f"for env='{env}'. Aborting pipeline."
        )

    if duration > MAX_DURATION_SECS:
        _fail(
            f"Audio duration {duration:.1f}s exceeds the {MAX_DURATION_SECS}s maximum. "
            f"Aborting pipeline to maintain broadcast quality."
        )

    # ── Step 6: Cover image ───────────────────────────────────────────────────
    print("[6/10] Generating cover image...")
    cover_path = OUTPUT_DIR / f"ep_{timestamp}_cover.png"
    if not _generate_cover_image(title, cover_path):
        _fail("Cover image generation failed.")

    # ── Step 7: Compile video ─────────────────────────────────────────────────
    print("[7/10] Compiling MP4...")
    video_path = OUTPUT_DIR / f"ep_{timestamp}.mp4"
    if not _compile_video(cover_path, audio_path, video_path, duration):
        _fail("FFmpeg video compilation failed.")

    # Mandatory post-compile file checks (spec requirement)
    if not video_path.exists():
        _fail(f"Video file not found after compilation: {video_path}")
    video_size = video_path.stat().st_size
    if video_size == 0:
        _fail(f"Video file is zero bytes: {video_path}")

    # Verify video duration matches audio duration
    video_duration = _get_audio_duration(video_path)
    print(f"[7/10] Video duration: {video_duration:.1f}s (Audio: {duration:.1f}s)")
    if abs(video_duration - duration) > 2.0:
        _fail(
            f"Video duration mismatch! Video: {video_duration:.1f}s, Audio: {duration:.1f}s"
        )

    print(
        f"[7/10] Video compiled & verified → {video_path.name} ({video_size:,} bytes)"
    )

    # ── Step 8: YouTube upload ────────────────────────────────────────────────
    video_url: Optional[str] = None
    if use_youtube:
        print("[8/10] Uploading to YouTube...")
        from publisher import upload_to_youtube

        description = final_broadcast.get("post_text", "")
        tags = final_broadcast.get("topic_tags", [])
        video_url = upload_to_youtube(str(video_path), title, description, tags)
        # Per spec: None = log failure but do NOT fail the pipeline
        if video_url is None:
            print("[8/10] YouTube upload returned None — continuing without video URL.")
        else:
            print(f"[8/10] YouTube upload OK → {video_url}")
    else:
        reason = "dry-run" if dry_run else f"env={env} (YouTube disabled)"
        print(f"[8/10] YouTube upload skipped ({reason}).")

    # ── Step 9: Save to DB ────────────────────────────────────────────────────
    if dry_run:
        print("[9/10] DRY RUN — skipping DB write.")
    else:
        print("[9/10] Saving episode to database...")

        # Register artifacts (Local URI or Cloud URL)
        # Note: We prioritize YouTube for videos to avoid Supabase storage limits.
        final_audio_url = db.upload_file(audio_path)
        final_video_url = video_url if video_url else db.upload_file(video_path)

        post_data = build_episode_metadata(
            news_items=news,
            broadcast=final_broadcast,
            duration=duration,
            audio_url=final_audio_url,
            video_url=final_video_url,
            healer_used=bool(final_broadcast.get("_healer_used", False)),
            writer_model=final_broadcast.get("_writer_model", "unknown"),
            narrator_model=actual_narrator_model,
        )
        row = db.insert_post(post_data)
        if row is None:
            _fail("DB insert_post returned None — episode metadata not persisted.")
        print(f"[9/10] Episode saved → id={row.get('id')}")

    # ── Step 10: Sync config ──────────────────────────────────────────────────
    print("[10/10] Syncing config.js...")
    from sync_config import sync_env_to_config

    sync_env_to_config(env)

    # ── Step 11: Self-Assessment (New) ────────────────────────────────────────
    if not dry_run:
        from tests.gate_checks import check_latest_run

        if not check_latest_run(env):
            _fail("Episode failed self-assessment gate checks. See log for details.")

    print(
        f"\n{'=' * 60}\n"
        f"  ✅  Pipeline complete\n"
        f"  Video : {video_path.name}  ({video_size:,} bytes)\n"
        f"  Duration : {duration:.1f}s\n"
        f"  env={env}  |  dry_run={dry_run}\n"
        f"{'=' * 60}\n"
    )


if __name__ == "__main__":
    main()
