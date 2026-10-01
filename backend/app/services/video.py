"""Device media encoders: baseline MJPEG AVI at 320x240 with mono MP3.

Video profiles trade motion smoothness against SD/decoder load. Balanced
20fps is the default; smooth 30fps and light 15fps are explicit choices.
Browser and server video encoding use matching rate/quality limits.
"""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

SCREEN_WIDTH = 320
SCREEN_HEIGHT = 240
VIDEO_PROFILES = {
    "balanced": {"fps": 20, "bitrate": "1600k", "qmin": 17},
    "smooth": {"fps": 30, "bitrate": "2400k", "qmin": 17},
    "light": {"fps": 15, "bitrate": "1000k", "qmin": 20},
}
DEFAULT_VIDEO_PROFILE = "balanced"
FRAME_RATE = VIDEO_PROFILES[DEFAULT_VIDEO_PROFILE]["fps"]
VIDEO_BITRATE = VIDEO_PROFILES[DEFAULT_VIDEO_PROFILE]["bitrate"]
VIDEO_QSCALE = VIDEO_PROFILES[DEFAULT_VIDEO_PROFILE]["qmin"]
VIDEO_VBV_BUF = "320k"
AUDIO_BITRATE = "96k"
AUDIO_RATE = 48000
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


def build_command(input_path: Path, output_path: Path, mode: str = DEFAULT_FIT_MODE,
                  profile: str = DEFAULT_VIDEO_PROFILE) -> list[str]:
    """The exact MJPEG/.avi command, as an argv list (no shell). `mode` is one of
    FIT_MODES — 'fit' (letterbox), 'fill' (crop to cover), 'stretch' (distort).
    Unknown values fall back to the default fit."""
    settings = VIDEO_PROFILES.get(profile, VIDEO_PROFILES[DEFAULT_VIDEO_PROFILE])
    vf = _VIDEO_FILTERS.get(mode, _VIDEO_FILTERS[DEFAULT_FIT_MODE])
    vf = vf.rsplit(",fps=", 1)[0] + f",fps={settings['fps']}"
    return [
        "ffmpeg", "-hide_banner", "-y",
        "-i", str(input_path),
        "-c:v", "mjpeg",
        "-pix_fmt", "yuvj420p",  # fits the device's fixed YCbCr decode workspace
        "-b:v", settings["bitrate"], "-maxrate", settings["bitrate"], "-bufsize", VIDEO_VBV_BUF,
        "-qmin", str(settings["qmin"]), "-qmax", "31",
        "-vf", vf,
        "-c:a", "libmp3lame", "-ac", "1", "-b:a", AUDIO_BITRATE, "-ar", str(AUDIO_RATE),
        str(output_path),
    ]


async def encode_to_mjpeg_avi(input_path: Path, output_path: Path, mode: str = DEFAULT_FIT_MODE,
                              profile: str = DEFAULT_VIDEO_PROFILE) -> Path:
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
    cmd = build_command(input_path, output_path, mode=mode, profile=profile)

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


# ── Clock background GIF ────────────────────────────────────────────────────
# The firmware Clock app plays /clock/gif/bg.gif behind the digits (PAUSE → Background
# → GIF). It decodes ONE frame at a time into an RGB565 canvas and scale-fills it
# onto the 320×240 LCD, so:
#   • Resolution is EXACTLY 320×240. The screen is 320×240 and the app downscales
#     anything bigger, so a larger GIF only wastes decode RAM/time on pixels that
#     get thrown away (and a >~480×360 GIF won't even fit the app's RAM budget).
#     Producing it at 320×240 is both the safe limit AND the optimal size.
#   • The palette is reduced (device renders RGB565 ≈ 65k colours and GIF is
#     ≤256 anyway): fewer colours = smaller file + faster LZW decode on-device.
#     palettegen + Bayer (ordered) dither maps cleanly onto 565 without the
#     inter-frame shimmer that error-diffusion causes on a loop.
#   • fps is low — the whole face repaints per GIF frame (the app labels this
#     the "high" battery level), and a background doesn't need motion; duration
#     is capped since it loops on-device.
#   • File size is kept under a byte budget with a quality LADDER: each rung
#     re-encodes with lower fps/colors and a heavier gifsicle lossy pass, and we
#     stop at the first rung that fits. Quality knobs drop BEFORE motion knobs,
#     so the source's loop/movement survives even on pathological inputs.
CLOCK_GIF_MAX_SECONDS = 15        # non-loop sources (videos) get cut here
CLOCK_GIF_LOOP_MAX_SECONDS = 30   # a GIF source is a loop — cutting it breaks the
                                  # motion, so whole loops are kept up to this
CLOCK_GIF_TARGET_BYTES = 2_000_000  # device-comfortable budget: small enough for
                                    # smooth SD streaming, roomy enough for quality
# Ladder rungs, best quality first. Worst-case measured (every pixel changing,
# 8s 25fps source): 2.8MB / 1.8MB / 1.2MB — real footage lands far lower.
CLOCK_GIF_LADDER = (
    {"fps": 12, "colors": 128, "lossy": 35},
    {"fps": 10, "colors": 96, "lossy": 80},
    {"fps": 8, "colors": 64, "lossy": 120},
)
CLOCK_GIF_SUFFIX = ".gif"
CLOCK_FIT_MODES = FIT_MODES + ("custom",)   # custom = user crop rectangle

# User-adjusted crop rectangle as FRACTIONS of the source frame (resolution-
# independent, straight from the web cropper): x/y = top-left, w/h = size.
ClockCrop = tuple[float, float, float, float]


def _clock_scale(mode: str, fps: int, animated: bool = True,
                 crop: ClockCrop | None = None) -> str:
    """320×240 fit/fill/stretch/custom (mirrors _VIDEO_FILTERS). `animated` adds
    the fps resample; a still image must NOT (fps on a timeline-less single frame
    yields zero frames), it just flows through as one frame. `custom` cuts the
    user's crop rectangle first, then scales it to the full screen."""
    m = mode if mode in CLOCK_FIT_MODES else DEFAULT_FIT_MODE
    fps_f = f",fps={fps}" if animated else ""
    if m == "custom" and crop:
        cx, cy, cw, ch = crop
        return (f"crop=iw*{cw:.6f}:ih*{ch:.6f}:iw*{cx:.6f}:ih*{cy:.6f}"
                f",scale={SCREEN_WIDTH}:{SCREEN_HEIGHT}:flags=lanczos{fps_f}")
    if m == "fill":
        return (f"scale={SCREEN_WIDTH}:{SCREEN_HEIGHT}:force_original_aspect_ratio=increase:flags=lanczos"
                f",crop={SCREEN_WIDTH}:{SCREEN_HEIGHT}{fps_f}")
    if m == "stretch":
        return f"scale={SCREEN_WIDTH}:{SCREEN_HEIGHT}:flags=lanczos{fps_f}"
    return (f"scale={SCREEN_WIDTH}:{SCREEN_HEIGHT}:force_original_aspect_ratio=decrease:flags=lanczos"
            f",pad={SCREEN_WIDTH}:{SCREEN_HEIGHT}:-1:-1:color=black{fps_f}")


def _probe_seconds(input_path: Path) -> float:
    """Source duration in seconds via ffprobe; 0.0 for a still image (no
    timeline) or if ffprobe can't tell."""
    import subprocess
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nk=1:nw=1", str(input_path)],
            capture_output=True, text=True, timeout=20,
        ).stdout.strip()
        return float(out)
    except (ValueError, OSError, subprocess.SubprocessError):
        return 0.0


def build_clock_gif_command(input_path: Path, output_path: Path,
                            mode: str = DEFAULT_FIT_MODE,
                            fps: int = CLOCK_GIF_LADDER[0]["fps"],
                            max_colors: int = CLOCK_GIF_LADDER[0]["colors"],
                            seconds: int = CLOCK_GIF_MAX_SECONDS,
                            still: bool = False,
                            crop: ClockCrop | None = None) -> list[str]:
    """ffmpeg argv for a device-optimized 320×240 clock-background GIF: one
    filter graph does the screen-fit scale + a per-clip optimized palette
    (palettegen) applied with ordered dithering (paletteuse). A `still` input
    yields a single-frame GIF (a static background — the app just loops it);
    an animated one is capped at `seconds`."""
    scale = _clock_scale(mode, fps, animated=not still, crop=crop)
    graph = (
        f"{scale},split[a][b]"
        f";[a]palettegen=max_colors={max_colors}:stats_mode=diff[p]"
        f";[b][p]paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle"
    )
    cmd = ["ffmpeg", "-hide_banner", "-y"]
    if not still:
        cmd += ["-t", str(seconds)]          # cap length (loops on device)
    cmd += ["-i", str(input_path), "-filter_complex", graph,
            "-loop", "0", str(output_path)]
    return cmd


def _is_animated_webp(input_path: Path) -> bool:
    """ffmpeg's built-in webp decoder only reads a single VP8/VP8L bitstream —
    it can't parse the ANIM/ANMF chunks of an animated WebP and fails outright
    ("Decode error rate 1 exceeds maximum"). Detect that case so it can be
    re-encoded via Pillow first."""
    if input_path.suffix.lower() != ".webp":
        return False
    from PIL import Image
    try:
        with Image.open(input_path) as im:
            return bool(getattr(im, "is_animated", False))
    except Exception:
        return False


def _animated_webp_to_gif(input_path: Path) -> Path:
    """Re-encode an animated WebP into a temporary animated GIF via Pillow (which
    decodes ANIM/ANMF chunks fine) so ffmpeg gets a format it can actually read."""
    from PIL import Image
    gif_path = input_path.with_suffix(".converted.gif")
    with Image.open(input_path) as im:
        frames, durations = [], []
        for i in range(im.n_frames):
            im.seek(i)
            frames.append(im.convert("RGBA"))
            durations.append(im.info.get("duration", 100))
        frames[0].save(
            gif_path, save_all=True, append_images=frames[1:],
            duration=durations, loop=0, disposal=2,
        )
    return gif_path


def gifsicle_available() -> bool:
    return shutil.which("gifsicle") is not None


async def _gifsicle_optimize(path: Path, lossy: int) -> None:
    """In-place gifsicle -O3 lossy pass — 15–30%+ smaller on top of ffmpeg's
    output. Quietly skipped if gifsicle isn't installed or fails (the ffmpeg
    GIF is already valid, just bigger)."""
    if not gifsicle_available():
        return
    tmp = path.with_suffix(".opt.gif")
    proc = await asyncio.create_subprocess_exec(
        "gifsicle", "-O3", f"--lossy={lossy}", "-o", str(tmp), str(path),
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.communicate()
    if proc.returncode == 0 and tmp.exists() and 0 < tmp.stat().st_size < path.stat().st_size:
        tmp.replace(path)
    else:
        tmp.unlink(missing_ok=True)


async def encode_to_clock_gif(input_path: Path, output_path: Path,
                              mode: str = DEFAULT_FIT_MODE,
                              crop: ClockCrop | None = None) -> Path:
    """Encode any image/video into a clock-ready /clock/gif/bg.gif (320×240, palette-
    optimized, ordered-dithered). `mode` = fit / fill / stretch / custom (with
    `crop` fractions). A still image becomes a 1-frame static background; an
    animated source loops on-device — a GIF source keeps its WHOLE loop (up to
    CLOCK_GIF_LOOP_MAX_SECONDS) so the original motion survives.

    Walks the quality ladder until the file fits CLOCK_GIF_TARGET_BYTES: every
    input comes out device-playable, degrading quality (colors/fps/lossy) before
    ever touching the motion. Raises VideoEncodeError on failure."""
    if not ffmpeg_available():
        raise VideoEncodeError("ffmpeg is not installed on the server")
    if not input_path.exists():
        raise VideoEncodeError(f"Input not found: {input_path}")
    if _is_animated_webp(input_path):
        input_path = _animated_webp_to_gif(input_path)
    still = _probe_seconds(input_path) <= 0.0
    is_gif_loop = input_path.suffix.lower() == CLOCK_GIF_SUFFIX
    seconds = CLOCK_GIF_LOOP_MAX_SECONDS if is_gif_loop else CLOCK_GIF_MAX_SECONDS

    for rung in CLOCK_GIF_LADDER:
        cmd = build_clock_gif_command(
            input_path, output_path, mode=mode, fps=rung["fps"],
            max_colors=rung["colors"], seconds=seconds, still=still, crop=crop,
        )
        await _run_ffmpeg(cmd, output_path, "clock gif")
        await _gifsicle_optimize(output_path, rung["lossy"])
        if still or output_path.stat().st_size <= CLOCK_GIF_TARGET_BYTES:
            break   # fits (or single frame — the ladder won't shrink it further)
    # If even the last rung is over budget (pathological input) it's still the
    # most compressed encode — ship it rather than cutting the loop.
    return output_path


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
