"""
Video encoding for the device's /media MJPEG player.

Hard hardware fact: the chip has NO H.264/HEVC decoder, only a hardware JPEG
decoder. So the ONLY playable video is MJPEG inside an .avi container. This
is the EXACT command build_command() emits (default 'fit' mode shown):

  ffmpeg -hide_banner -y -i input -c:v mjpeg -q:v 8 \
    -vf scale=320:240:force_original_aspect_ratio=decrease,pad=320:240:-1:-1:color=black,fps=30 \
    -c:a libmp3lame -ac 1 -b:a 96k -ar 44100 output.avi

Only the -vf filter changes with the screen-fit mode (see _VIDEO_FILTERS):
  fit     scale=320:240:force_original_aspect_ratio=decrease,pad=320:240:-1:-1:color=black,fps=30
  fill    scale=320:240:force_original_aspect_ratio=increase,crop=320:240,fps=30
  stretch scale=320:240,fps=30

Audio = MP3 mono, NOT raw PCM: the SD card is the bottleneck. MP3 mono 96k is
~12 KB/s and reuses the device's existing minimp3 decoder (shared with the
music app) — no new audio path. The device downmixes/resamples to its 48kHz
mono output internally, so source channels/rate don't matter. Video is
320x240 MJPEG q8 @ 30fps (~250 KB/s); the on-device player drops video frames
when the SD can't keep up so audio stays locked in sync. Screen is 320x240.
"""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

# Device-verified encode parameters (bench-tested on hardware).
SCREEN_WIDTH = 320
SCREEN_HEIGHT = 240
VIDEO_QSCALE = 8          # -q:v 8 (smaller frames -> less SD load; offsets 30fps)
FRAME_RATE = 30           # fps=30 — the device decodes via the HW JPEG codec now
                          # (~few ms/frame), so 30fps is smooth; q8 keeps SD load flat
AUDIO_BITRATE = "96k"     # MP3 mono — minimal SD load, reuses minimp3 on device
AUDIO_RATE = 44100        # -ar 44100 (device resamples to 48k mono internally)
OUTPUT_SUFFIX = ".avi"

# Three ways to map an arbitrary source onto the exact 320x240 screen:
#   fit     (default) — scale DOWN to fit, then PAD with black bars (letterbox).
#                       Whole frame kept, correct aspect, no cropping.
#   fill    (cover)   — scale UP to cover, then CROP the overflow. Fills the
#                       screen edge-to-edge, correct aspect, crops the long side.
#   stretch           — scale to EXACTLY 320x240 ignoring aspect. Fills the
#                       screen with no bars and no cropping, but DISTORTS.
# All end at exactly 320x240 and resample to the target frame rate.
_VIDEO_FILTERS = {
    "fit": (
        f"scale={SCREEN_WIDTH}:{SCREEN_HEIGHT}:force_original_aspect_ratio=decrease"
        f",pad={SCREEN_WIDTH}:{SCREEN_HEIGHT}:-1:-1:color=black"
        f",fps={FRAME_RATE}"
    ),
    "fill": (
        f"scale={SCREEN_WIDTH}:{SCREEN_HEIGHT}:force_original_aspect_ratio=increase"
        f",crop={SCREEN_WIDTH}:{SCREEN_HEIGHT}"
        f",fps={FRAME_RATE}"
    ),
    "stretch": (
        f"scale={SCREEN_WIDTH}:{SCREEN_HEIGHT}"
        f",fps={FRAME_RATE}"
    ),
}
DEFAULT_FIT_MODE = "fit"
FIT_MODES = tuple(_VIDEO_FILTERS)  # ("fit", "fill", "stretch")


class VideoEncodeError(RuntimeError):
    """Raised when ffmpeg is missing or the encode fails."""


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def build_command(input_path: Path, output_path: Path, mode: str = DEFAULT_FIT_MODE) -> list[str]:
    """The exact MJPEG/.avi command, as an argv list (no shell). `mode` is one of
    FIT_MODES — 'fit' (letterbox), 'fill' (crop to cover), 'stretch' (distort).
    Unknown values fall back to the default fit."""
    return [
        "ffmpeg", "-hide_banner", "-y",
        "-i", str(input_path),
        "-c:v", "mjpeg", "-q:v", str(VIDEO_QSCALE),
        "-vf", _VIDEO_FILTERS.get(mode, _VIDEO_FILTERS[DEFAULT_FIT_MODE]),
        "-c:a", "libmp3lame", "-ac", "1", "-b:a", AUDIO_BITRATE, "-ar", str(AUDIO_RATE),
        str(output_path),
    ]


async def encode_to_mjpeg_avi(input_path: Path, output_path: Path, mode: str = DEFAULT_FIT_MODE) -> Path:
    """
    Encode `input_path` to a device-playable MJPEG .avi at `output_path`.

    `mode` controls screen mapping: 'fit' letterboxes (keeps whole frame),
    'fill' scales up + crops to cover, 'stretch' distorts to exactly 320x240.

    Runs ffmpeg in a subprocess so the event loop stays free. Raises
    VideoEncodeError on any failure (caller marks the job failed).
    """
    if not ffmpeg_available():
        raise VideoEncodeError("ffmpeg is not installed on the server")
    if not input_path.exists():
        raise VideoEncodeError(f"Input not found: {input_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = build_command(input_path, output_path, mode=mode)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        tail = (stderr or b"").decode("utf-8", "replace")[-800:]
        raise VideoEncodeError(f"ffmpeg failed (code {proc.returncode}):\n{tail}")
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise VideoEncodeError("ffmpeg produced no output")
    return output_path


async def _run_ffmpeg(cmd: list[str], output_path: Path, what: str) -> Path:
    """Run an ffmpeg argv, raising VideoEncodeError unless it produced a file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0 or not output_path.exists() or output_path.stat().st_size == 0:
        tail = (stderr or b"").decode("utf-8", "replace")[-600:]
        raise VideoEncodeError(f"ffmpeg {what} failed:\n{tail}")
    return output_path


async def make_thumb(input_path: Path, output_path: Path, w: int = 480, h: int = 270) -> Path:
    """Grab an early frame, scaled+cropped to a 16:9 JPEG thumbnail (YouTube-style)."""
    if not ffmpeg_available():
        raise VideoEncodeError("ffmpeg is not installed on the server")
    cmd = [
        "ffmpeg", "-hide_banner", "-y", "-i", str(input_path),
        "-frames:v", "1",
        "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}",
        "-q:v", "3", str(output_path),
    ]
    return await _run_ffmpeg(cmd, output_path, "thumb")


async def extract_cover(input_path: Path, output_path: Path) -> Path:
    """Extract embedded cover art (e.g. an MP3's ID3 picture) to a JPEG. Raises
    VideoEncodeError when the file has no embedded art."""
    if not ffmpeg_available():
        raise VideoEncodeError("ffmpeg is not installed on the server")
    cmd = [
        "ffmpeg", "-hide_banner", "-y", "-i", str(input_path),
        "-an", "-frames:v", "1", str(output_path),
    ]
    return await _run_ffmpeg(cmd, output_path, "cover")


# Album art the device shows on its small LCD — pre-shrink + gently boost so the
# firmware doesn't down-scale a huge image into mush. Tune on-device.
ART_SIZE = 240


def _process_art_sync(mp3_path: Path) -> bool:
    import shutil
    import tempfile
    from PIL import Image, ImageEnhance, ImageOps

    d = Path(tempfile.mkdtemp(prefix=".art_", dir=mp3_path.parent))
    try:
        raw = d / "raw.jpg"
        # pull the embedded picture (ffmpeg) — no art → leave the file untouched.
        import subprocess
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-y", "-i", str(mp3_path), "-an", "-frames:v", "1", str(raw)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if r.returncode != 0 or not raw.exists() or raw.stat().st_size == 0:
            return False

        img = ImageOps.exif_transpose(Image.open(raw)).convert("RGB")
        img.thumbnail((ART_SIZE, ART_SIZE), Image.LANCZOS)   # downscale only, keep aspect
        img = ImageEnhance.Contrast(img).enhance(1.08)        # small LCDs look flat
        img = ImageEnhance.Color(img).enhance(1.12)           # lift saturation a touch
        proc = d / "cover.jpg"
        img.save(proc, "JPEG", quality=88, optimize=True)

        out = d / "out.mp3"
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-y", "-i", str(mp3_path), "-i", str(proc),
             "-map", "0:a", "-map", "1:0", "-c:a", "copy", "-c:v", "mjpeg",
             "-id3v2_version", "3", "-disposition:v", "attached_pic", str(out)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if r.returncode != 0 or not out.exists() or out.stat().st_size == 0:
            return False
        shutil.move(str(out), str(mp3_path))
        return True
    finally:
        shutil.rmtree(d, ignore_errors=True)


async def optimize_album_art(mp3_path: Path) -> bool:
    """Resize+optimize the MP3's embedded album art for the device and re-embed it
    (replacing the original). Returns False (no-op) when there's no art."""
    if not ffmpeg_available() or not mp3_path.exists():
        return False
    return await asyncio.to_thread(_process_art_sync, mp3_path)


async def make_web_preview(input_path: Path, output_path: Path) -> Path:
    """Transcode the device MJPEG/.avi to a small browser-playable H.264 .mp4."""
    if not ffmpeg_available():
        raise VideoEncodeError("ffmpeg is not installed on the server")
    cmd = [
        "ffmpeg", "-hide_banner", "-y", "-i", str(input_path),
        "-vf", "scale='min(640,iw)':-2",   # cap width at 640 (downscale only) → small file
        "-c:v", "libx264", "-crf", "28", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart",
        str(output_path),
    ]
    return await _run_ffmpeg(cmd, output_path, "preview")


async def extract_mp3(input_path: Path, output_path: Path) -> Path:
    """Extract the audio track of any media file (video or audio) to an MP3 — used
    by the Music tab to turn an uploaded video into a /music track. No video stream."""
    if not ffmpeg_available():
        raise VideoEncodeError("ffmpeg is not installed on the server")
    if not input_path.exists():
        raise VideoEncodeError(f"Input not found: {input_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-hide_banner", "-y", "-i", str(input_path),
        "-vn", "-c:a", "libmp3lame", "-q:a", "2",   # VBR ~190 kbps
        str(output_path),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        tail = (stderr or b"").decode("utf-8", "replace")[-800:]
        raise VideoEncodeError(f"ffmpeg audio extract failed (code {proc.returncode}):\n{tail}")
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise VideoEncodeError("ffmpeg produced no audio")
    return output_path
