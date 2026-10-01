"""Profile parity and delivery through the real upload/background pipeline."""
import asyncio
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from app import config, db
from app.routers import videos
from app.services import jobs, video


@pytest.fixture(autouse=True)
def enable_video_features(monkeypatch):
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", True)


@pytest.mark.parametrize("profile", list(video.VIDEO_PROFILES))
@pytest.mark.parametrize("mode", ["fit", "fill", "stretch", "unknown"])
def test_browser_and_server_profiles_match(profile, mode):
    if not shutil.which("node"):
        pytest.skip("node is required to check browser/server argv parity")
    builder = Path(__file__).resolve().parents[2] / "frontend/src/videoencode.js"
    script = (
        f"import {{buildDeviceVideoArgs}} from {json.dumps(builder.as_uri())};"
        f"console.log(JSON.stringify(buildDeviceVideoArgs('input.mp4','output.avi',"
        f"{json.dumps(mode)},{json.dumps(profile)})));"
    )
    r = subprocess.run(["node", "--input-type=module", "-e", script],
                       text=True, capture_output=True, check=True)
    assert json.loads(r.stdout) == video.build_command(
        Path("input.mp4"), Path("output.avi"), mode, profile)[1:]


def test_invalid_profile_falls_back_in_builder():
    assert video.build_command(Path("in"), Path("out"), profile="invalid") == \
           video.build_command(Path("in"), Path("out"), profile="balanced")


@pytest.mark.asyncio
async def test_upload_passes_light_profile_to_background_encoder(client, session_id, monkeypatch):
    monkeypatch.setattr(video, "ffmpeg_available", lambda: True)
    scheduled = []
    original_create_task = asyncio.create_task

    def capture_encode(coro, **kwargs):
        if getattr(coro, "cr_code", None) is videos._run_encode.__code__:
            scheduled.append(coro)
            return None
        return original_create_task(coro, **kwargs)

    monkeypatch.setattr(videos.asyncio, "create_task", capture_encode)
    calls = []

    async def encode(src, dst, mode="fit", profile="balanced"):
        calls.append((mode, profile))
        dst.write_bytes(b"encoded AVI")
        return dst

    async def skip(*args, **kwargs):
        pass

    monkeypatch.setattr(video, "encode_to_mjpeg_avi", encode)
    monkeypatch.setattr(video, "make_web_preview", skip)
    monkeypatch.setattr(video, "make_thumb", skip)
    response = client.post(f"/api/sessions/{session_id}/videos",
                           files={"file": ("clip.mp4", b"source", "video/mp4")},
                           data={"mode": "fill", "profile": "light"})
    assert response.status_code == 200, response.text
    assert len(scheduled) == 1
    await scheduled[0]
    assert calls == [("fill", "light")]
    with db.connect() as conn:
        row = conn.execute("SELECT status FROM videos WHERE id=?",
                           (response.json()["video_id"],)).fetchone()
    assert row["status"] == "ok"
    assert jobs.get(response.json()["job_id"]).status == "done"


def test_unknown_profile_is_rejected_before_job_creation(client, session_id):
    response = client.post(f"/api/sessions/{session_id}/videos",
                           files={"file": ("clip.mp4", b"source", "video/mp4")},
                           data={"profile": "invalid"})
    assert response.status_code == 422


@pytest.mark.parametrize("profile", list(video.VIDEO_PROFILES))
def test_real_encode_output_fits_device_workspace(tmp_path, profile):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg and ffprobe are required for the media contract check")
    src, dst = tmp_path / "source.mkv", tmp_path / "device.avi"
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
        "testsrc2=size=640x360:rate=30:duration=1", "-f", "lavfi", "-i",
        "sine=frequency=440:sample_rate=48000:duration=1",
        "-c:v", "ffv1", "-c:a", "pcm_s16le", str(src),
    ], check=True, capture_output=True)
    asyncio.run(video.encode_to_mjpeg_avi(src, dst, profile=profile))
    r = subprocess.run([
        "ffprobe", "-v", "error", "-show_streams", "-show_packets", "-of", "json", str(dst),
    ], check=True, capture_output=True, text=True)
    data = json.loads(r.stdout)
    v = next(s for s in data["streams"] if s["codec_type"] == "video")
    a = next(s for s in data["streams"] if s["codec_type"] == "audio")
    assert (v["codec_name"], v["width"], v["height"], v["pix_fmt"]) == ("mjpeg", 320, 240, "yuvj420p")
    assert v["r_frame_rate"] == f"{video.VIDEO_PROFILES[profile]['fps']}/1"
    assert (a["codec_name"], a["sample_rate"], a["channels"]) == ("mp3", "48000", 1)
    packets = [int(p["size"]) for p in data["packets"] if p["stream_index"] == v["index"]]
    assert packets and max(packets) <= 65536
