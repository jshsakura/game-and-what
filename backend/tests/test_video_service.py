# -*- coding: utf-8 -*-
"""app.services.video — the ffmpeg/ffprobe wrapper for the device's MJPEG/.avi
player, thumbnails, cover art, web previews, MP3 extraction, and the clock
background GIF.

This module NEVER invokes real ffmpeg/ffprobe/gifsicle. Every test either:
  * calls a pure argv-building function directly (build_command,
    build_clock_gif_command, _clock_scale) and asserts on the exact list, or
  * monkeypatches the asyncio-subprocess boundary the module actually calls
    (`video.asyncio.create_subprocess_exec`) with a fake that records the argv
    and simulates ffmpeg's side effect (writing, or not writing, the output
    file) so the module's own success/failure logic runs for real, or
  * monkeypatches the sync `subprocess.run` boundary used by `_probe_seconds`
    and `_process_art_sync`.

What this pins: the MJPEG/.avi codec+quality+fps+scale/pad/crop/stretch
filters, mono MP3 audio, ffprobe duration parsing (valid + malformed),
VideoEncodeError on non-zero exit / missing input / missing output (with the
ffmpeg stderr surfaced), and the clock-GIF quality ladder that walks
fps/colors/lossy rungs until the output fits CLOCK_GIF_TARGET_BYTES (or ships
the last rung anyway on a pathological input).

Not covered: this module has no cancellation handling (no CancelledError
catch/propagation logic anywhere), so there is nothing distinct to pin there.

test_video_webp.py already pins `_is_animated_webp`/`_animated_webp_to_gif`
directly and test_clock.py already pins the `/api/clock/background` router
plus one `_clock_scale("custom", ...)` case — those are not duplicated here.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from PIL import Image

from app.services import video


# ── shared fakes ─────────────────────────────────────────────────────────────

class _FakeProc:
    """Stand-in for what asyncio.create_subprocess_exec() returns."""

    def __init__(self, returncode: int, stderr: bytes):
        self.returncode = returncode
        self._stderr = stderr

    async def communicate(self):
        return b"", self._stderr


def _fake_exec(*, returncode=0, stderr=b"", write_output=True, output_index=-1,
               content=b"fake-output-bytes", calls: list | None = None):
    """Factory for a fake `asyncio.create_subprocess_exec`. Records the argv
    (if `calls` is given) and simulates ffmpeg's side effect of writing (or
    not writing, for failure tests) the output file at `cmd[output_index]`."""

    async def _fake(*cmd, **_kwargs):
        if calls is not None:
            calls.append(list(cmd))
        if write_output:
            out_path = Path(cmd[output_index])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(content)
        return _FakeProc(returncode, stderr)

    return _fake


async def _noop_gifsicle(_path, _lossy):
    pass


# ── ffmpeg_available / gifsicle_available ───────────────────────────────────

def test_ffmpeg_available_true_when_binary_on_path(monkeypatch):
    monkeypatch.setattr(video.shutil, "which", lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else None)
    assert video.ffmpeg_available() is True


def test_ffmpeg_available_false_when_binary_missing(monkeypatch):
    monkeypatch.setattr(video.shutil, "which", lambda _name: None)
    assert video.ffmpeg_available() is False


def test_gifsicle_available_true_when_binary_on_path(monkeypatch):
    monkeypatch.setattr(video.shutil, "which", lambda name: "/usr/bin/gifsicle" if name == "gifsicle" else None)
    assert video.gifsicle_available() is True


def test_gifsicle_available_false_when_binary_missing(monkeypatch):
    monkeypatch.setattr(video.shutil, "which", lambda _name: None)
    assert video.gifsicle_available() is False


# ── build_command (MJPEG/.avi argv, pure function) ──────────────────────────

def test_build_command_default_fit_mode_matches_documented_contract(tmp_path):
    src, dst = tmp_path / "in.mp4", tmp_path / "out.avi"

    cmd = video.build_command(src, dst)

    assert cmd == [
        "ffmpeg", "-hide_banner", "-y",
        "-i", str(src),
        "-c:v", "mjpeg",
        "-b:v", "2400k", "-maxrate", "2400k", "-bufsize", "320k",
        "-qmin", "17", "-qmax", "31",
        "-vf", "scale=320:240:force_original_aspect_ratio=decrease,pad=320:240:-1:-1:color=black,fps=30",
        "-c:a", "libmp3lame", "-ac", "1", "-b:a", "96k", "-ar", "48000",
        str(dst),
    ]


def test_build_command_fill_mode_scales_up_and_crops_to_cover(tmp_path):
    cmd = video.build_command(tmp_path / "in.mp4", tmp_path / "out.avi", mode="fill")

    vf = cmd[cmd.index("-vf") + 1]
    assert vf == "scale=320:240:force_original_aspect_ratio=increase,crop=320:240,fps=30"


def test_build_command_stretch_mode_distorts_to_exact_screen_size(tmp_path):
    cmd = video.build_command(tmp_path / "in.mp4", tmp_path / "out.avi", mode="stretch")

    vf = cmd[cmd.index("-vf") + 1]
    assert vf == "scale=320:240,fps=30"


def test_build_command_unknown_mode_falls_back_to_fit(tmp_path):
    src, dst = tmp_path / "in.mp4", tmp_path / "out.avi"

    cmd = video.build_command(src, dst, mode="nonsense")

    assert cmd == video.build_command(src, dst, mode="fit")


# ── encode_to_mjpeg_avi ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_encode_to_mjpeg_avi_happy_path_uses_build_command_and_writes_output(monkeypatch, tmp_path):
    src = tmp_path / "in.mp4"
    src.write_bytes(b"fake source video")
    dst = tmp_path / "nested" / "clip.avi"
    monkeypatch.setattr(video, "ffmpeg_available", lambda: True)
    calls: list = []
    monkeypatch.setattr(video.asyncio, "create_subprocess_exec", _fake_exec(calls=calls))

    result = await video.encode_to_mjpeg_avi(src, dst, mode="fill")

    assert result == dst
    assert dst.exists()
    assert calls[0] == video.build_command(src, dst, mode="fill")


@pytest.mark.asyncio
async def test_encode_to_mjpeg_avi_raises_when_ffmpeg_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(video, "ffmpeg_available", lambda: False)

    with pytest.raises(video.VideoEncodeError, match="not installed"):
        await video.encode_to_mjpeg_avi(tmp_path / "in.mp4", tmp_path / "out.avi")


@pytest.mark.asyncio
async def test_encode_to_mjpeg_avi_raises_when_input_missing_without_spawning_ffmpeg(monkeypatch, tmp_path):
    monkeypatch.setattr(video, "ffmpeg_available", lambda: True)
    calls: list = []
    monkeypatch.setattr(video.asyncio, "create_subprocess_exec", _fake_exec(calls=calls))

    with pytest.raises(video.VideoEncodeError, match="Input not found"):
        await video.encode_to_mjpeg_avi(tmp_path / "missing.mp4", tmp_path / "out.avi")

    assert calls == []


@pytest.mark.asyncio
async def test_encode_to_mjpeg_avi_raises_with_stderr_tail_on_nonzero_exit(monkeypatch, tmp_path):
    src = tmp_path / "in.mp4"
    src.write_bytes(b"x")
    monkeypatch.setattr(video, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(
        video.asyncio, "create_subprocess_exec",
        _fake_exec(returncode=1, stderr=b"invalid data found when processing input", write_output=False),
    )

    with pytest.raises(video.VideoEncodeError, match="invalid data found when processing input"):
        await video.encode_to_mjpeg_avi(src, tmp_path / "out.avi")


@pytest.mark.asyncio
async def test_encode_to_mjpeg_avi_raises_when_output_not_produced(monkeypatch, tmp_path):
    src = tmp_path / "in.mp4"
    src.write_bytes(b"x")
    monkeypatch.setattr(video, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(video.asyncio, "create_subprocess_exec", _fake_exec(write_output=False))

    with pytest.raises(video.VideoEncodeError, match="no output"):
        await video.encode_to_mjpeg_avi(src, tmp_path / "out.avi")


@pytest.mark.asyncio
async def test_encode_to_mjpeg_avi_raises_when_output_is_empty(monkeypatch, tmp_path):
    src = tmp_path / "in.mp4"
    src.write_bytes(b"x")
    monkeypatch.setattr(video, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(video.asyncio, "create_subprocess_exec", _fake_exec(content=b""))

    with pytest.raises(video.VideoEncodeError, match="no output"):
        await video.encode_to_mjpeg_avi(src, tmp_path / "out.avi")


# ── make_thumb ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_make_thumb_happy_path_builds_scaled_cropped_jpeg_command(monkeypatch, tmp_path):
    src, dst = tmp_path / "in.mp4", tmp_path / "thumb.jpg"
    monkeypatch.setattr(video, "ffmpeg_available", lambda: True)
    calls: list = []
    monkeypatch.setattr(video.asyncio, "create_subprocess_exec", _fake_exec(calls=calls))

    result = await video.make_thumb(src, dst, w=480, h=270)

    assert result == dst and dst.exists()
    cmd = calls[0]
    assert cmd[:5] == ["ffmpeg", "-hide_banner", "-y", "-i", str(src)]
    assert cmd[cmd.index("-frames:v") + 1] == "1"
    assert cmd[cmd.index("-vf") + 1] == "scale=480:270:force_original_aspect_ratio=increase,crop=480:270"
    assert cmd[cmd.index("-q:v") + 1] == "3"
    assert cmd[-1] == str(dst)


@pytest.mark.asyncio
async def test_make_thumb_raises_when_ffmpeg_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(video, "ffmpeg_available", lambda: False)

    with pytest.raises(video.VideoEncodeError):
        await video.make_thumb(tmp_path / "in.mp4", tmp_path / "thumb.jpg")


@pytest.mark.asyncio
async def test_make_thumb_raises_on_nonzero_exit(monkeypatch, tmp_path):
    monkeypatch.setattr(video, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(
        video.asyncio, "create_subprocess_exec",
        _fake_exec(returncode=1, stderr=b"boom", write_output=False),
    )

    with pytest.raises(video.VideoEncodeError, match="thumb failed"):
        await video.make_thumb(tmp_path / "in.mp4", tmp_path / "thumb.jpg")


# ── extract_cover ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_cover_happy_path_builds_single_frame_no_audio_command(monkeypatch, tmp_path):
    src, dst = tmp_path / "song.mp3", tmp_path / "cover.jpg"
    monkeypatch.setattr(video, "ffmpeg_available", lambda: True)
    calls: list = []
    monkeypatch.setattr(video.asyncio, "create_subprocess_exec", _fake_exec(calls=calls))

    result = await video.extract_cover(src, dst)

    assert result == dst and dst.exists()
    assert calls[0] == ["ffmpeg", "-hide_banner", "-y", "-i", str(src), "-an", "-frames:v", "1", str(dst)]


@pytest.mark.asyncio
async def test_extract_cover_raises_when_no_embedded_art(monkeypatch, tmp_path):
    monkeypatch.setattr(video, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(video.asyncio, "create_subprocess_exec", _fake_exec(write_output=False))

    with pytest.raises(video.VideoEncodeError, match="cover failed"):
        await video.extract_cover(tmp_path / "song.mp3", tmp_path / "cover.jpg")


@pytest.mark.asyncio
async def test_extract_cover_raises_when_ffmpeg_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(video, "ffmpeg_available", lambda: False)

    with pytest.raises(video.VideoEncodeError):
        await video.extract_cover(tmp_path / "song.mp3", tmp_path / "cover.jpg")


# ── make_web_preview ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_make_web_preview_happy_path_builds_h264_aac_mp4_command(monkeypatch, tmp_path):
    src, dst = tmp_path / "clip.avi", tmp_path / "preview.mp4"
    monkeypatch.setattr(video, "ffmpeg_available", lambda: True)
    calls: list = []
    monkeypatch.setattr(video.asyncio, "create_subprocess_exec", _fake_exec(calls=calls))

    result = await video.make_web_preview(src, dst)

    assert result == dst and dst.exists()
    assert calls[0] == [
        "ffmpeg", "-hide_banner", "-y", "-i", str(src),
        "-vf", "scale='min(640,iw)':-2",
        "-c:v", "libx264", "-crf", "28", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart",
        str(dst),
    ]


@pytest.mark.asyncio
async def test_make_web_preview_raises_when_ffmpeg_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(video, "ffmpeg_available", lambda: False)

    with pytest.raises(video.VideoEncodeError):
        await video.make_web_preview(tmp_path / "in.avi", tmp_path / "out.mp4")


@pytest.mark.asyncio
async def test_make_web_preview_raises_on_nonzero_exit(monkeypatch, tmp_path):
    monkeypatch.setattr(video, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(
        video.asyncio, "create_subprocess_exec",
        _fake_exec(returncode=1, stderr=b"unsupported codec", write_output=False),
    )

    with pytest.raises(video.VideoEncodeError, match="preview failed"):
        await video.make_web_preview(tmp_path / "in.avi", tmp_path / "out.mp4")


# ── extract_mp3 ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_mp3_happy_path_builds_audio_only_vbr_command(monkeypatch, tmp_path):
    src = tmp_path / "clip.mp4"
    src.write_bytes(b"x")
    dst = tmp_path / "track.mp3"
    monkeypatch.setattr(video, "ffmpeg_available", lambda: True)
    calls: list = []
    monkeypatch.setattr(video.asyncio, "create_subprocess_exec", _fake_exec(calls=calls))

    result = await video.extract_mp3(src, dst)

    assert result == dst and dst.exists()
    assert calls[0] == [
        "ffmpeg", "-hide_banner", "-y", "-i", str(src),
        "-vn", "-c:a", "libmp3lame", "-q:a", "2",
        str(dst),
    ]


@pytest.mark.asyncio
async def test_extract_mp3_raises_when_ffmpeg_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(video, "ffmpeg_available", lambda: False)

    with pytest.raises(video.VideoEncodeError, match="not installed"):
        await video.extract_mp3(tmp_path / "in.mp4", tmp_path / "out.mp3")


@pytest.mark.asyncio
async def test_extract_mp3_raises_when_input_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(video, "ffmpeg_available", lambda: True)

    with pytest.raises(video.VideoEncodeError, match="Input not found"):
        await video.extract_mp3(tmp_path / "missing.mp4", tmp_path / "out.mp3")


@pytest.mark.asyncio
async def test_extract_mp3_raises_with_stderr_tail_on_nonzero_exit(monkeypatch, tmp_path):
    src = tmp_path / "clip.mp4"
    src.write_bytes(b"x")
    monkeypatch.setattr(video, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(
        video.asyncio, "create_subprocess_exec",
        _fake_exec(returncode=1, stderr=b"no audio stream found", write_output=False),
    )

    with pytest.raises(video.VideoEncodeError, match="no audio stream found"):
        await video.extract_mp3(src, tmp_path / "out.mp3")


@pytest.mark.asyncio
async def test_extract_mp3_raises_when_output_not_produced(monkeypatch, tmp_path):
    src = tmp_path / "clip.mp4"
    src.write_bytes(b"x")
    monkeypatch.setattr(video, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(video.asyncio, "create_subprocess_exec", _fake_exec(write_output=False))

    with pytest.raises(video.VideoEncodeError, match="no audio"):
        await video.extract_mp3(src, tmp_path / "out.mp3")


# ── _probe_seconds (ffprobe duration parsing) ───────────────────────────────

def test_probe_seconds_parses_valid_ffprobe_output(monkeypatch, tmp_path):
    fake_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="12.345000\n")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: fake_result)

    assert video._probe_seconds(tmp_path / "in.mp4") == pytest.approx(12.345)


def test_probe_seconds_returns_zero_for_malformed_output(monkeypatch, tmp_path):
    fake_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="N/A\n")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: fake_result)

    assert video._probe_seconds(tmp_path / "in.mp4") == 0.0


def test_probe_seconds_returns_zero_when_ffprobe_binary_missing(monkeypatch, tmp_path):
    def _boom(*_a, **_k):
        raise FileNotFoundError("ffprobe not found")

    monkeypatch.setattr(subprocess, "run", _boom)

    assert video._probe_seconds(tmp_path / "in.mp4") == 0.0


def test_probe_seconds_returns_zero_on_ffprobe_timeout(monkeypatch, tmp_path):
    def _boom(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd=["ffprobe"], timeout=20)

    monkeypatch.setattr(subprocess, "run", _boom)

    assert video._probe_seconds(tmp_path / "in.mp4") == 0.0


# ── _clock_scale (320x240 fit/fill/stretch/custom filter graphs) ───────────

def test_clock_scale_fit_matches_video_filters_shape_with_lanczos_and_fps():
    result = video._clock_scale("fit", fps=12)

    assert result == (
        "scale=320:240:force_original_aspect_ratio=decrease:flags=lanczos"
        ",pad=320:240:-1:-1:color=black,fps=12"
    )


def test_clock_scale_fill_crops_to_cover():
    result = video._clock_scale("fill", fps=10)

    assert result == "scale=320:240:force_original_aspect_ratio=increase:flags=lanczos,crop=320:240,fps=10"


def test_clock_scale_stretch_distorts_to_exact_screen():
    result = video._clock_scale("stretch", fps=8)

    assert result == "scale=320:240:flags=lanczos,fps=8"


def test_clock_scale_still_image_omits_fps_resample():
    result = video._clock_scale("fit", fps=12, animated=False)

    assert "fps=" not in result


def test_clock_scale_unknown_mode_falls_back_to_fit():
    assert video._clock_scale("bogus", fps=12) == video._clock_scale("fit", fps=12)


def test_clock_scale_custom_without_crop_falls_back_to_fit():
    """The crop branch is guarded by `if m == "custom" and crop:` — no crop
    tuple means it flows through to the default fit filter instead."""
    result = video._clock_scale("custom", fps=12, crop=None)

    assert result == video._clock_scale("fit", fps=12)


# ── build_clock_gif_command (pure function) ─────────────────────────────────

def test_build_clock_gif_command_animated_includes_duration_cap_and_palette_graph(tmp_path):
    src, dst = tmp_path / "in.mp4", tmp_path / "bg.gif"

    cmd = video.build_clock_gif_command(src, dst, mode="fit", fps=12, max_colors=128, seconds=15, still=False)

    assert cmd[:3] == ["ffmpeg", "-hide_banner", "-y"]
    assert cmd[3:5] == ["-t", "15"]
    assert cmd[5:7] == ["-i", str(src)]
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert graph.startswith(
        "scale=320:240:force_original_aspect_ratio=decrease:flags=lanczos"
        ",pad=320:240:-1:-1:color=black,fps=12,split[a][b]"
    )
    assert "palettegen=max_colors=128:stats_mode=diff" in graph
    assert "paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle" in graph
    assert cmd[-3:] == ["-loop", "0", str(dst)]


def test_build_clock_gif_command_still_omits_duration_cap_and_fps(tmp_path):
    src, dst = tmp_path / "in.png", tmp_path / "bg.gif"

    cmd = video.build_clock_gif_command(src, dst, still=True)

    assert "-t" not in cmd
    assert cmd[1:5] == ["-hide_banner", "-y", "-i", str(src)]
    graph = cmd[cmd.index("-filter_complex") + 1]
    scale_stage = graph.split(",split")[0]
    assert "fps=" not in scale_stage


def test_build_clock_gif_command_custom_mode_threads_crop_rectangle(tmp_path):
    src, dst = tmp_path / "in.mp4", tmp_path / "bg.gif"

    cmd = video.build_clock_gif_command(
        src, dst, mode="custom", crop=(0.25, 0.1, 0.5, 0.4), fps=10, max_colors=96,
    )

    graph = cmd[cmd.index("-filter_complex") + 1]
    assert graph.startswith("crop=iw*0.500000:ih*0.400000:iw*0.250000:ih*0.100000,scale=320:240:flags=lanczos,fps=10")


# ── _process_art_sync / optimize_album_art (embedded MP3 cover art) ────────

def test_process_art_sync_returns_false_and_leaves_file_untouched_when_no_art(monkeypatch, tmp_path):
    mp3 = tmp_path / "song.mp3"
    mp3.write_bytes(b"original mp3 bytes")

    def fake_run(cmd, **_kwargs):
        return subprocess.CompletedProcess(cmd, returncode=1)  # ffmpeg found no picture stream

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert video._process_art_sync(mp3) is False
    assert mp3.read_bytes() == b"original mp3 bytes"


def test_process_art_sync_resizes_and_reembeds_art(monkeypatch, tmp_path):
    mp3 = tmp_path / "song.mp3"
    mp3.write_bytes(b"original mp3 bytes")

    def fake_run(cmd, **_kwargs):
        dest = Path(cmd[-1])
        if dest.name == "raw.jpg":
            Image.new("RGB", (600, 600), (200, 50, 50)).save(dest, "JPEG")
        else:
            dest.write_bytes(b"reencoded mp3 with optimized art")
        return subprocess.CompletedProcess(cmd, returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert video._process_art_sync(mp3) is True
    assert mp3.read_bytes() == b"reencoded mp3 with optimized art"


def test_process_art_sync_returns_false_when_reembed_step_fails(monkeypatch, tmp_path):
    mp3 = tmp_path / "song.mp3"
    mp3.write_bytes(b"original mp3 bytes")

    def fake_run(cmd, **_kwargs):
        dest = Path(cmd[-1])
        if dest.name == "raw.jpg":
            Image.new("RGB", (100, 100), (1, 2, 3)).save(dest, "JPEG")
            return subprocess.CompletedProcess(cmd, returncode=0)
        return subprocess.CompletedProcess(cmd, returncode=1)  # re-embed fails

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert video._process_art_sync(mp3) is False
    assert mp3.read_bytes() == b"original mp3 bytes"


@pytest.mark.asyncio
async def test_optimize_album_art_returns_false_when_ffmpeg_missing(monkeypatch, tmp_path):
    mp3 = tmp_path / "song.mp3"
    mp3.write_bytes(b"x")
    monkeypatch.setattr(video, "ffmpeg_available", lambda: False)

    assert await video.optimize_album_art(mp3) is False


@pytest.mark.asyncio
async def test_optimize_album_art_returns_false_when_file_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(video, "ffmpeg_available", lambda: True)

    assert await video.optimize_album_art(tmp_path / "missing.mp3") is False


@pytest.mark.asyncio
async def test_optimize_album_art_delegates_to_process_art_sync(monkeypatch, tmp_path):
    mp3 = tmp_path / "song.mp3"
    mp3.write_bytes(b"x")
    monkeypatch.setattr(video, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(video, "_process_art_sync", lambda _p: True)

    assert await video.optimize_album_art(mp3) is True


# ── _gifsicle_optimize (in-place lossy pass) ────────────────────────────────

@pytest.mark.asyncio
async def test_gifsicle_optimize_skipped_when_binary_missing(monkeypatch, tmp_path):
    gif = tmp_path / "bg.gif"
    gif.write_bytes(b"original gif bytes")
    monkeypatch.setattr(video, "gifsicle_available", lambda: False)
    called = False

    async def fake_exec(*_cmd, **_kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(video.asyncio, "create_subprocess_exec", fake_exec)

    await video._gifsicle_optimize(gif, lossy=80)

    assert called is False
    assert gif.read_bytes() == b"original gif bytes"


@pytest.mark.asyncio
async def test_gifsicle_optimize_replaces_file_when_output_smaller(monkeypatch, tmp_path):
    gif = tmp_path / "bg.gif"
    gif.write_bytes(b"x" * 1000)
    monkeypatch.setattr(video, "gifsicle_available", lambda: True)

    async def fake_exec(*cmd, **_kwargs):
        tmp = Path(cmd[cmd.index("-o") + 1])
        tmp.write_bytes(b"y" * 100)
        return _FakeProc(0, b"")

    monkeypatch.setattr(video.asyncio, "create_subprocess_exec", fake_exec)

    await video._gifsicle_optimize(gif, lossy=80)

    assert gif.read_bytes() == b"y" * 100


@pytest.mark.asyncio
async def test_gifsicle_optimize_keeps_original_when_output_not_smaller(monkeypatch, tmp_path):
    gif = tmp_path / "bg.gif"
    gif.write_bytes(b"x" * 100)
    monkeypatch.setattr(video, "gifsicle_available", lambda: True)

    async def fake_exec(*cmd, **_kwargs):
        tmp = Path(cmd[cmd.index("-o") + 1])
        tmp.write_bytes(b"y" * 500)  # bigger than the original
        return _FakeProc(0, b"")

    monkeypatch.setattr(video.asyncio, "create_subprocess_exec", fake_exec)

    await video._gifsicle_optimize(gif, lossy=80)

    assert gif.read_bytes() == b"x" * 100
    assert not (tmp_path / "bg.opt.gif").exists()


@pytest.mark.asyncio
async def test_gifsicle_optimize_keeps_original_when_gifsicle_fails(monkeypatch, tmp_path):
    gif = tmp_path / "bg.gif"
    gif.write_bytes(b"x" * 100)
    monkeypatch.setattr(video, "gifsicle_available", lambda: True)

    async def fake_exec(*_cmd, **_kwargs):
        return _FakeProc(1, b"gifsicle error")

    monkeypatch.setattr(video.asyncio, "create_subprocess_exec", fake_exec)

    await video._gifsicle_optimize(gif, lossy=80)

    assert gif.read_bytes() == b"x" * 100


# ── encode_to_clock_gif (quality-ladder orchestration) ──────────────────────

@pytest.mark.asyncio
async def test_encode_to_clock_gif_raises_when_ffmpeg_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(video, "ffmpeg_available", lambda: False)

    with pytest.raises(video.VideoEncodeError, match="not installed"):
        await video.encode_to_clock_gif(tmp_path / "in.mp4", tmp_path / "bg.gif")


@pytest.mark.asyncio
async def test_encode_to_clock_gif_raises_when_input_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(video, "ffmpeg_available", lambda: True)

    with pytest.raises(video.VideoEncodeError, match="Input not found"):
        await video.encode_to_clock_gif(tmp_path / "missing.mp4", tmp_path / "bg.gif")


@pytest.mark.asyncio
async def test_encode_to_clock_gif_still_image_stops_after_first_rung_regardless_of_size(monkeypatch, tmp_path):
    src, dst = tmp_path / "pic.png", tmp_path / "bg.gif"
    src.write_bytes(b"x")
    monkeypatch.setattr(video, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(video, "_probe_seconds", lambda _p: 0.0)  # no timeline -> still
    calls: list = []

    async def fake_run_ffmpeg(cmd, output_path, _what):
        calls.append(cmd)
        output_path.write_bytes(b"x" * (video.CLOCK_GIF_TARGET_BYTES * 5))  # oversized on purpose
        return output_path

    monkeypatch.setattr(video, "_run_ffmpeg", fake_run_ffmpeg)
    monkeypatch.setattr(video, "_gifsicle_optimize", _noop_gifsicle)

    result = await video.encode_to_clock_gif(src, dst)

    assert result == dst
    assert len(calls) == 1
    assert "-t" not in calls[0]


@pytest.mark.asyncio
async def test_encode_to_clock_gif_stops_at_first_rung_that_fits_budget(monkeypatch, tmp_path):
    src, dst = tmp_path / "clip.mp4", tmp_path / "bg.gif"
    src.write_bytes(b"x")
    monkeypatch.setattr(video, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(video, "_probe_seconds", lambda _p: 5.0)  # animated
    calls: list = []

    async def fake_run_ffmpeg(cmd, output_path, _what):
        calls.append(cmd)
        output_path.write_bytes(b"x" * 100)  # comfortably under budget
        return output_path

    monkeypatch.setattr(video, "_run_ffmpeg", fake_run_ffmpeg)
    monkeypatch.setattr(video, "_gifsicle_optimize", _noop_gifsicle)

    await video.encode_to_clock_gif(src, dst)

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_encode_to_clock_gif_walks_ladder_rungs_until_it_fits(monkeypatch, tmp_path):
    src, dst = tmp_path / "clip.mp4", tmp_path / "bg.gif"
    src.write_bytes(b"x")
    monkeypatch.setattr(video, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(video, "_probe_seconds", lambda _p: 5.0)
    sizes = [video.CLOCK_GIF_TARGET_BYTES + 1, video.CLOCK_GIF_TARGET_BYTES + 1, 100]
    calls: list = []

    async def fake_run_ffmpeg(cmd, output_path, _what):
        calls.append(cmd)
        output_path.write_bytes(b"x" * sizes[len(calls) - 1])
        return output_path

    monkeypatch.setattr(video, "_run_ffmpeg", fake_run_ffmpeg)
    monkeypatch.setattr(video, "_gifsicle_optimize", _noop_gifsicle)

    await video.encode_to_clock_gif(src, dst)

    assert len(calls) == 3
    for cmd, rung in zip(calls, video.CLOCK_GIF_LADDER):
        graph = cmd[cmd.index("-filter_complex") + 1]
        assert f"fps={rung['fps']}" in graph
        assert f"max_colors={rung['colors']}" in graph


@pytest.mark.asyncio
async def test_encode_to_clock_gif_ships_last_rung_even_if_still_oversized(monkeypatch, tmp_path):
    src, dst = tmp_path / "clip.mp4", tmp_path / "bg.gif"
    src.write_bytes(b"x")
    monkeypatch.setattr(video, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(video, "_probe_seconds", lambda _p: 5.0)
    calls: list = []

    async def fake_run_ffmpeg(cmd, output_path, _what):
        calls.append(cmd)
        output_path.write_bytes(b"x" * (video.CLOCK_GIF_TARGET_BYTES * 2))  # never fits
        return output_path

    monkeypatch.setattr(video, "_run_ffmpeg", fake_run_ffmpeg)
    monkeypatch.setattr(video, "_gifsicle_optimize", _noop_gifsicle)

    result = await video.encode_to_clock_gif(src, dst)

    assert result == dst
    assert len(calls) == len(video.CLOCK_GIF_LADDER)


@pytest.mark.asyncio
async def test_encode_to_clock_gif_source_keeps_whole_loop_duration_cap(monkeypatch, tmp_path):
    src, dst = tmp_path / "loop.gif", tmp_path / "bg.gif"
    src.write_bytes(b"GIF89a")
    monkeypatch.setattr(video, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(video, "_probe_seconds", lambda _p: 3.0)
    calls: list = []

    async def fake_run_ffmpeg(cmd, output_path, _what):
        calls.append(cmd)
        output_path.write_bytes(b"x" * 100)
        return output_path

    monkeypatch.setattr(video, "_run_ffmpeg", fake_run_ffmpeg)
    monkeypatch.setattr(video, "_gifsicle_optimize", _noop_gifsicle)

    await video.encode_to_clock_gif(src, dst)

    cmd = calls[0]
    assert cmd[cmd.index("-t") + 1] == str(video.CLOCK_GIF_LOOP_MAX_SECONDS)


@pytest.mark.asyncio
async def test_encode_to_clock_gif_non_gif_source_uses_short_duration_cap(monkeypatch, tmp_path):
    src, dst = tmp_path / "clip.mp4", tmp_path / "bg.gif"
    src.write_bytes(b"x")
    monkeypatch.setattr(video, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(video, "_probe_seconds", lambda _p: 3.0)
    calls: list = []

    async def fake_run_ffmpeg(cmd, output_path, _what):
        calls.append(cmd)
        output_path.write_bytes(b"x" * 100)
        return output_path

    monkeypatch.setattr(video, "_run_ffmpeg", fake_run_ffmpeg)
    monkeypatch.setattr(video, "_gifsicle_optimize", _noop_gifsicle)

    await video.encode_to_clock_gif(src, dst)

    cmd = calls[0]
    assert cmd[cmd.index("-t") + 1] == str(video.CLOCK_GIF_MAX_SECONDS)


@pytest.mark.asyncio
async def test_encode_to_clock_gif_converts_animated_webp_before_probing_and_encoding(monkeypatch, tmp_path):
    src = tmp_path / "src.webp"
    frames = [Image.new("RGB", (40, 30), c) for c in [(255, 0, 0), (0, 255, 0)]]
    frames[0].save(src, save_all=True, append_images=frames[1:], duration=100, loop=0)
    dst = tmp_path / "bg.gif"
    monkeypatch.setattr(video, "ffmpeg_available", lambda: True)
    probed_inputs: list = []

    def fake_probe(p):
        probed_inputs.append(p)
        return 2.0  # animated

    monkeypatch.setattr(video, "_probe_seconds", fake_probe)
    calls: list = []

    async def fake_run_ffmpeg(cmd, output_path, _what):
        calls.append(cmd)
        output_path.write_bytes(b"x" * 100)
        return output_path

    monkeypatch.setattr(video, "_run_ffmpeg", fake_run_ffmpeg)
    monkeypatch.setattr(video, "_gifsicle_optimize", _noop_gifsicle)

    await video.encode_to_clock_gif(src, dst)

    # webp was converted to a real .gif before probing/encoding, so it's then
    # treated as a loop source (LOOP_MAX_SECONDS cap, not the short image cap)
    assert probed_inputs[0].suffix == ".gif"
    cmd = calls[0]
    assert cmd[cmd.index("-i") + 1] == str(probed_inputs[0])
    assert cmd[cmd.index("-t") + 1] == str(video.CLOCK_GIF_LOOP_MAX_SECONDS)
