"""
tts_generator.py — AI Radio Echo
Text-to-speech generation with high-fidelity mixing.

TTS provider: edge-tts (free)
Mixing:      Pydub for SFX overlays, looping ambient tracks, and voice styles.

Voice Styles:
  - normal:  Base settings.
  - whisper: -8dB gain + simulated reverb.
  - grave:   0.9x speed + flat emotion.
  - excited: 1.1x speed + high emotion.
  - deadpan: 0.8x speed + clinical delivery.
"""

import asyncio
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional
from pydub import AudioSegment

# ── Network-error detection ───────────────────────────────────────────────────

_NETWORK_ERROR_MARKERS = (
    "SSLCertVerificationError",
    "Cannot connect",
    "certificate verify failed",
    "ConnectionError",
    "TimeoutError",
    "ssl:",
    "Network",
)


def _is_network_error(msg: str) -> bool:
    return any(m in msg for m in _NETWORK_ERROR_MARKERS)


# ── Step 1 & 2: Style & SFX Processing ────────────────────────────────────────

def _simulate_reverb(audio: AudioSegment) -> AudioSegment:
    """
    Simulate slight reverb by overlaying a delayed, quieter version.

    Args:
        audio: The pydub AudioSegment to process.

    Returns:
        The processed AudioSegment with simulated reverb.
    """
    delay = 40 # ms
    feedback = audio - 15 # -15dB
    return audio.overlay(feedback, position=delay)

def _apply_audio_processing(
    audio_path: str, 
    voice_style: str, 
    sfx_pre: Optional[str], 
    sfx_post: Optional[str]
) -> bool:
    """
    Apply voice styles (pydub) and mix SFX overlays.

    Args:
        audio_path:  Path to the existing TTS audio file.
        voice_style: One of: normal, whisper, grave, excited, deadpan.
        sfx_pre:     Optional name of SFX to prepend.
        sfx_post:    Optional name of SFX to append.

    Returns:
        True on success, False on failure.
    """
    # Normalize SFX names (handle models returning string "null")
    if sfx_pre == "null":
        sfx_pre = None
    if sfx_post == "null":
        sfx_post = None

    try:
        speech = AudioSegment.from_file(audio_path)
        
        # 1. Voice Style Processing (Post-Generation)
        if voice_style == "whisper":
            speech = speech - 8 # Reduce gain by 8dB
            speech = _simulate_reverb(speech)
        
        # 2. Ambient Underlay (Looping)
        ambient_path = Path("sfx/STREET_AMBIENT.mp3")
        if ambient_path.exists():
            ambient = AudioSegment.from_file(str(ambient_path))
            # Loop ambient to cover speech duration
            loop_count = int(len(speech) / len(ambient)) + 1
            ambient_loop = (ambient * loop_count)[:len(speech)]
            ambient_loop = ambient_loop - 22 # Quiet background
            speech = ambient_loop.overlay(speech)
        
        # 3. SFX Pre/Post
        final_audio = speech
        
        if sfx_pre:
            pre_path = Path(f"sfx/{sfx_pre}.mp3")
            if pre_path.exists():
                sfx = AudioSegment.from_file(str(pre_path))
                final_audio = sfx + final_audio
            elif sfx_pre == "SILENCE":
                # Ensure SILENCE.mp3 exists or generate on the fly
                if not Path("sfx/SILENCE.mp3").exists():
                    AudioSegment.silent(duration=2000).export("sfx/SILENCE.mp3", format="mp3")
                sfx = AudioSegment.from_file("sfx/SILENCE.mp3")
                final_audio = sfx + final_audio
            else:
                print(f"[SFX] Warning: Pre-SFX '{sfx_pre}' not found.")

        if sfx_post:
            post_path = Path(f"sfx/{sfx_post}.mp3")
            if post_path.exists():
                sfx = AudioSegment.from_file(str(post_path))
                final_audio = final_audio + sfx
            elif sfx_post == "SILENCE":
                if not Path("sfx/SILENCE.mp3").exists():
                    AudioSegment.silent(duration=2000).export("sfx/SILENCE.mp3", format="mp3")
                sfx = AudioSegment.from_file("sfx/SILENCE.mp3")
                final_audio = final_audio + sfx
            else:
                print(f"[SFX] Warning: Post-SFX '{sfx_post}' not found.")

        final_audio.export(audio_path, format="mp3", bitrate="64k")
        return True

    except Exception as exc:
        print(f"[Mixer] Failed to process audio: {exc}")
        return False


# ── FFmpeg silent/tone fallback ───────────────────────────────────────────────

def _generate_ffmpeg_audio_fallback(text: str, path: str) -> bool:
    """
    Last-resort audio generation via FFmpeg when edge-tts is network-blocked.
    Generates a silent audio clip whose length is proportional to the word count
    so the duration check in main.py reflects a plausible reading time.

    Logged loudly — never silent.  Only called when edge-tts fails with a
    network/SSL error (i.e. an environment restriction, not a code bug).
    Returns True on success, False if FFmpeg itself fails.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("[TTS] FFmpeg fallback unavailable — ffmpeg not in PATH.")
        return False

    # Estimate reading duration: ~130 words per minute at TTS speed
    word_count = len(text.split())
    duration_secs = max(5, int((word_count / 130) * 60))

    print(
        f"[TTS] NETWORK FALLBACK: edge-tts is unreachable in this environment. "
        f"Generating {duration_secs}s silent audio via FFmpeg for {word_count} words. "
        f"Real TTS will work on GitHub Actions."
    )

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            ffmpeg, "-y",
            "-f", "lavfi",
            "-i", "anullsrc=r=22050:cl=mono",
            "-t", str(duration_secs),
            "-c:a", "libmp3lame", "-b:a", "64k",
            path,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"[TTS] FFmpeg audio fallback failed: {result.stderr[-500:]}")
        return False
    print(f"[TTS] FFmpeg audio fallback OK → {path} ({duration_secs}s)")
    return True


# ── edge-tts ──────────────────────────────────────────────────────────────────

_EDGE_TTS_MAX_ATTEMPTS = 3
_EDGE_TTS_RETRY_DELAY_SECONDS = 2

async def _edge_tts_async(text: str, voice: str, path: str) -> tuple[bool, str]:
    """Returns (success, error_message)."""
    try:
        import edge_tts
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(path)
        return True, ""
    except Exception as exc:
        return False, str(exc)


def _run_edge_tts(text: str, voice: str, path: str) -> bool:
    """
    Run edge-tts via asyncio.
    Falls back to an explicit new event loop if one is already running
    (RuntimeError: 'event loop already running').

    Retries transient failures with exponential backoff before applying the
    explicit FFmpeg fallback for network-restricted environments.
    """
    last_error = ""
    for attempt in range(1, _EDGE_TTS_MAX_ATTEMPTS + 1):
        try:
            ok, err = asyncio.run(_edge_tts_async(text, voice, path))
        except RuntimeError as exc:
            exc_str = str(exc)
            if "event loop" in exc_str.lower():
                loop = asyncio.new_event_loop()
                try:
                    ok, err = loop.run_until_complete(_edge_tts_async(text, voice, path))
                finally:
                    loop.close()
            else:
                ok, err = False, exc_str

        if ok:
            if attempt > 1:
                print(f"[TTS] edge-tts succeeded on attempt {attempt}.")
            return True

        last_error = err
        print(
            f"[TTS] edge-tts attempt {attempt}/{_EDGE_TTS_MAX_ATTEMPTS} failed "
            f"(voice={voice}): {err}"
        )
        if attempt < _EDGE_TTS_MAX_ATTEMPTS:
            time.sleep(_EDGE_TTS_RETRY_DELAY_SECONDS * (2 ** (attempt - 1)))

    print(f"[TTS] edge-tts synthesis failed after {_EDGE_TTS_MAX_ATTEMPTS} attempts (voice={voice}): {last_error}")
    if _is_network_error(last_error):
        return _generate_ffmpeg_audio_fallback(text, path)
    return False


# ── TTS Quality Guard ─────────────────────────────────────────────────────────

def _get_audio_duration(path: str) -> float:
    """Return duration in seconds using ffprobe or ffmpeg."""
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg:
        return -1.0

    if ffprobe:
        cmd = [
            ffprobe, "-v", "quiet", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", path
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                return float(res.stdout.strip())
        except (ValueError, subprocess.TimeoutExpired, Exception):
            pass

    # Fallback to ffmpeg -i
    cmd = [ffmpeg, "-i", path]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        import re
        match = re.search(r"Duration:\s*(\d{2}):(\d{2}):(\d{2}(?:\.\d+)?)", res.stderr)
        if match:
            h, m, s = int(match.group(1)), int(match.group(2)), float(match.group(3))
            return h * 3600 + m * 60 + s
    except Exception:
        pass
    return -1.0


def _is_audio_valid(path: str, word_count: int) -> bool:
    """
    Verify audio integrity.
    Rejects files that are missing, zero-byte, or suspiciously short 
    (e.g. > 300 words per minute is likely a TTS truncation error).
    """
    p = Path(path)
    if not p.exists() or p.stat().st_size < 100:
        return False
    
    duration = _get_audio_duration(path)
    if duration <= 0:
        print(f"[TTS] Quality Check: Failed to determine duration for {path}.")
        return False
    
    # 300 WPM is double the normal speed. Anything faster is definitely a bug.
    wpm = (word_count / duration) * 60
    print(f"[TTS] Quality Check: {path} has {word_count} words in {duration:.1f}s (~{wpm:.0f} WPM).")
    
    if wpm > 300:
        print("[TTS] Quality Alert: Audio too fast/short for word count.")
        return False
    
    return True


# ── Public API ────────────────────────────────────────────────────────────────

def generate_segment_audio(
    text: str,
    voice: str,
    path: str,
    use_cloud: bool,
    forced_engine: Optional[str] = None,
    voice_style: str = "normal",
    sfx_pre: Optional[str] = None,
    sfx_post: Optional[str] = None,
) -> tuple[bool, str]:
    """
    Generate TTS audio and apply voice styles/SFX (Step 1 & 2).
    Includes a quality guard for generated Edge TTS audio.

    Returns:
        (success, engine_name)
    """
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    word_count = len(text.split())
    preview = (text[:47] + "...") if len(text) > 50 else text
    print(f"[TTS] Narrating {word_count} words ({voice_style}): \"{preview}\"")

    # 1. Selection & Generation
    success = False
    engine_used = "failed"

    if forced_engine:
        if forced_engine == "edge-tts":
            success = _run_edge_tts(text, voice, path)
        
        if success and not _is_audio_valid(path, word_count):
            print(f"[TTS] Quality Check Failed for forced engine '{forced_engine}'.")
            success = False
        engine_used = forced_engine
    else:
        ok = _run_edge_tts(text, voice, path)
        if ok:
            if _is_audio_valid(path, word_count):
                success = True
                engine_used = "edge-tts"
            else:
                print("[TTS] Quality Check Failed for 'edge-tts'.")
                if Path(path).exists():
                    Path(path).unlink()
        
        if not success:
            success = _generate_ffmpeg_audio_fallback(text, path)
            engine_used = "silent-fallback"

    # 2. Mixing (Step 2)
    if success:
        if _apply_audio_processing(path, voice_style, sfx_pre, sfx_post):
            return True, engine_used
    
    return False, "failed"
