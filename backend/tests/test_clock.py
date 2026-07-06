# -*- coding: utf-8 -*-
"""POST /api/clock/background — image/video → 320×240 bg.gif download.

The router is mounted standalone (not the whole app) so the test needs no DB or
startup wiring, and ffmpeg is stubbed so it runs anywhere."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import clock
from app.services import video


def _client(monkeypatch, *, ffmpeg=True):
    async def fake_encode(src, out, mode="fit"):
        out.write_bytes(b"GIF89a-fake-" + mode.encode())
        return out

    monkeypatch.setattr(video, "ffmpeg_available", lambda: ffmpeg)
    monkeypatch.setattr(video, "encode_to_clock_gif", fake_encode)
    app = FastAPI()
    app.include_router(clock.router)
    return TestClient(app)


def test_converts_and_returns_gif(monkeypatch):
    c = _client(monkeypatch)
    r = c.post(
        "/api/clock/background",
        files={"file": ("pic.png", b"\x89PNGfake", "image/png")},
        data={"mode": "fill"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/gif"
    assert r.content == b"GIF89a-fake-fill"          # mode threaded through
    assert 'filename="bg.gif"' in r.headers.get("content-disposition", "")


def test_bad_mode_falls_back_to_fit(monkeypatch):
    c = _client(monkeypatch)
    r = c.post(
        "/api/clock/background",
        files={"file": ("pic.png", b"x", "image/png")},
        data={"mode": "nonsense"},
    )
    assert r.status_code == 200
    assert r.content == b"GIF89a-fake-fit"


def test_empty_upload_rejected(monkeypatch):
    c = _client(monkeypatch)
    r = c.post("/api/clock/background", files={"file": ("empty.png", b"", "image/png")})
    assert r.status_code == 400


def test_ffmpeg_missing_returns_503(monkeypatch):
    c = _client(monkeypatch, ffmpeg=False)
    r = c.post("/api/clock/background", files={"file": ("pic.png", b"x", "image/png")})
    assert r.status_code == 503


def test_encode_failure_returns_422(monkeypatch):
    async def boom(src, out, mode="fit"):
        raise video.VideoEncodeError("ffmpeg exploded")

    monkeypatch.setattr(video, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(video, "encode_to_clock_gif", boom)
    app = FastAPI()
    app.include_router(clock.router)
    r = TestClient(app).post(
        "/api/clock/background", files={"file": ("pic.png", b"x", "image/png")}
    )
    assert r.status_code == 422
    assert "ffmpeg exploded" in r.json()["detail"]
