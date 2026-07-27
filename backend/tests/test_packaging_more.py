# -*- coding: utf-8 -*-
"""services/packaging.py — the SD-ZIP builder, its on-disk content-fingerprint
cache, and progress/cancellation plumbing. backend/tests/test_packaging.py
already pins `_excluded()` directly; this file covers everything built on top
of it: what `_sd_entries`/`build_sd_zip_cached` actually write into the zip,
per-system/homebrew/sd_exclude filtering end-to-end, the experimental /media
+/music gating through the real build path, the fingerprint cache (hit / miss
/ eviction), job-driven cancellation, and the size estimators.
"""
from __future__ import annotations

import zipfile

import pytest

from app import config
from app.services import packaging, pico8core, storage


@pytest.fixture(autouse=True)
def _no_pico8_network(monkeypatch):
    """PICO-8 core fetch hits GitHub over the network; never do that in tests."""
    monkeypatch.setattr(pico8core, "ensure_cores_dir", lambda force=False: None)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "LIBRARY_DIR", tmp_path / "library")
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", False)
    return config.SHARED_SESSION_ID


def _write(path, data=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _names(zip_path) -> set[str]:
    with zipfile.ZipFile(zip_path) as zf:
        return set(zf.namelist())


# ---------------------------------------------------------------------------
# build_sd_zip_cached: contents / arcnames
# ---------------------------------------------------------------------------

def test_build_writes_roms_and_covers_with_sd_relative_arcnames(env):
    sid = env
    _write(storage.roms_dir(sid, "nes") / "Game.nes", b"rom-bytes")
    _write(storage.covers_dir(sid, "nes") / "Game.img", b"cover-bytes")

    path, etag = packaging.build_sd_zip_cached(sid)

    names = _names(path)
    assert "roms/nes/Game.nes" in names
    assert "covers/nes/Game.img" in names
    assert isinstance(etag, str) and etag


def test_build_excludes_scratch_previews_and_trash(env):
    sid = env
    _write(storage.roms_dir(sid, "nes") / "Game.nes")
    _write(storage.scratch_dir(sid) / "some_upload.zip")
    _write(storage.previews_dir(sid, "nes") / "Game.webp")
    _write(storage.trash_dir(sid) / "deleted.nes")

    path, _ = packaging.build_sd_zip_cached(sid)

    names = _names(path)
    assert names == {"roms/nes/Game.nes"}


def test_build_ships_firmware_at_sd_root(env):
    sid = env
    _write(storage.roms_dir(sid, "nes") / "Game.nes")
    _write(storage.firmware_path(sid), b"firmware-bytes")

    path, _ = packaging.build_sd_zip_cached(sid)

    names = _names(path)
    assert storage.FIRMWARE_FILENAME in names


def test_build_ships_extra_passthrough_files_at_root(env):
    sid = env
    _write(storage.roms_dir(sid, "nes") / "Game.nes")
    _write(storage.extra_dir(sid) / "bios" / "nes" / "disksys.rom", b"bios")

    path, _ = packaging.build_sd_zip_cached(sid)

    names = _names(path)
    assert "bios/nes/disksys.rom" in names


# ---------------------------------------------------------------------------
# per-system filtering
# ---------------------------------------------------------------------------

def test_build_with_systems_filter_keeps_only_selected_systems(env):
    sid = env
    _write(storage.roms_dir(sid, "nes") / "Game.nes")
    _write(storage.roms_dir(sid, "gb") / "Other.gb")
    _write(storage.covers_dir(sid, "gb") / "Other.img")

    path, _ = packaging.build_sd_zip_cached(sid, systems={"nes"})

    names = _names(path)
    assert "roms/nes/Game.nes" in names
    assert not any("gb" in n for n in names)


def test_build_with_systems_filter_excludes_pico8_core_when_not_selected(env, monkeypatch, tmp_path):
    sid = env
    _write(storage.roms_dir(sid, "nes") / "Game.nes")
    cores = tmp_path / "fake_cores"
    _write(cores / "pico8.gnw", b"core")
    monkeypatch.setattr(pico8core, "ensure_cores_dir", lambda force=False: cores)

    path, _ = packaging.build_sd_zip_cached(sid, systems={"nes"})

    names = _names(path)
    assert not any(n.startswith("cores/") for n in names)


def test_build_includes_pico8_core_when_pico8_selected(env, monkeypatch, tmp_path):
    sid = env
    _write(storage.roms_dir(sid, "pico8") / "Game.p8")
    cores = tmp_path / "fake_cores"
    _write(cores / "pico8.gnw", b"core")
    monkeypatch.setattr(pico8core, "ensure_cores_dir", lambda force=False: cores)

    path, _ = packaging.build_sd_zip_cached(sid, systems={"pico8"})

    names = _names(path)
    assert "cores/pico8.gnw" in names


def test_build_includes_pico8_core_for_full_library(env, monkeypatch, tmp_path):
    sid = env
    _write(storage.roms_dir(sid, "nes") / "Game.nes")
    cores = tmp_path / "fake_cores"
    _write(cores / "pico8.gnw", b"core")
    monkeypatch.setattr(pico8core, "ensure_cores_dir", lambda force=False: cores)

    path, _ = packaging.build_sd_zip_cached(sid, systems=None)  # full SD, no filter

    names = _names(path)
    assert "cores/pico8.gnw" in names


# ---------------------------------------------------------------------------
# homebrew .bin opt-in
# ---------------------------------------------------------------------------

def test_build_homebrew_bin_ships_only_when_opted_in(env):
    sid = env
    rel_bin = "roms/homebrew/App.bin"
    rel_dat = "roms/homebrew/App.dat"
    _write(storage.session_root(sid) / rel_bin, b"app")
    _write(storage.session_root(sid) / rel_dat, b"assets")

    default_path, _ = packaging.build_sd_zip_cached(sid)
    default_names = _names(default_path)
    assert rel_dat in default_names
    assert rel_bin not in default_names

    optin_path, _ = packaging.build_sd_zip_cached(sid, homebrew_roms={rel_bin})
    optin_names = _names(optin_path)
    assert rel_bin in optin_names
    assert rel_dat in optin_names


# ---------------------------------------------------------------------------
# sd_exclude (per-ROM opt-out)
# ---------------------------------------------------------------------------

def test_build_drops_sd_excluded_rom_and_its_cover(env):
    sid = env
    keep_rel = "roms/nes/Keep.nes"
    drop_rel = "roms/nes/Drop.nes"
    drop_cover_rel = "covers/nes/Drop.img"
    _write(storage.session_root(sid) / keep_rel)
    _write(storage.session_root(sid) / drop_rel)
    _write(storage.session_root(sid) / drop_cover_rel)

    path, _ = packaging.build_sd_zip_cached(sid, excluded_roms={drop_rel, drop_cover_rel})

    names = _names(path)
    assert keep_rel in names
    assert drop_rel not in names
    assert drop_cover_rel not in names


# ---------------------------------------------------------------------------
# /media +/music experimental gating, end-to-end through the real build
# ---------------------------------------------------------------------------

def test_official_mode_build_never_ships_media_or_music(env):
    sid = env
    _write(storage.media_dir(sid) / "clip.avi")
    _write(storage.music_dir(sid) / "song.mp3")
    _write(storage.roms_dir(sid, "nes") / "Game.nes")

    path, _ = packaging.build_sd_zip_cached(sid, include_video=True)

    names = _names(path)
    assert names == {"roms/nes/Game.nes"}


def test_experimental_mode_build_ships_music_and_opted_in_media(env, monkeypatch):
    sid = env
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", True)
    _write(storage.media_dir(sid) / "clip.avi")
    _write(storage.music_dir(sid) / "song.mp3")

    path, _ = packaging.build_sd_zip_cached(sid, include_video=True)

    names = _names(path)
    assert f"{config.MEDIA_DIR_NAME}/clip.avi" in names
    assert f"{config.MUSIC_DIR_NAME}/song.mp3" in names


def test_experimental_mode_without_video_flag_still_excludes_media(env, monkeypatch):
    sid = env
    monkeypatch.setattr(config, "EXPERIMENTAL_MODE", True)
    _write(storage.media_dir(sid) / "clip.avi")

    path, _ = packaging.build_sd_zip_cached(sid, include_video=False)

    names = _names(path)
    assert not any(n.startswith(config.MEDIA_DIR_NAME) for n in names)


# ---------------------------------------------------------------------------
# fingerprint / cache: hit, miss, distinct keys per param set
# ---------------------------------------------------------------------------

def test_cached_zip_path_reports_absence_before_any_build(env):
    sid = env
    _write(storage.roms_dir(sid, "nes") / "Game.nes")

    path, key, exists = packaging.cached_zip_path(sid)

    assert exists is False
    assert key == packaging.sd_fingerprint(sid)


def test_build_is_a_cache_hit_on_second_call(env):
    sid = env
    _write(storage.roms_dir(sid, "nes") / "Game.nes")

    first_path, first_etag = packaging.build_sd_zip_cached(sid)
    progress_calls = []
    second_path, second_etag = packaging.build_sd_zip_cached(
        sid, on_progress=lambda d, t: progress_calls.append((d, t))
    )

    assert second_path == first_path
    assert second_etag == first_etag
    # cache-hit fast path reports exactly one (1,1) progress tick, not a full rebuild
    assert progress_calls == [(1, 1)]


def test_fingerprint_changes_when_library_content_changes(env):
    sid = env
    _write(storage.roms_dir(sid, "nes") / "Game.nes")
    key1 = packaging.sd_fingerprint(sid)

    _write(storage.roms_dir(sid, "nes") / "Another.nes")
    key2 = packaging.sd_fingerprint(sid)

    assert key1 != key2


def test_fingerprint_varies_by_params_not_just_content(env):
    sid = env
    _write(storage.roms_dir(sid, "nes") / "Game.nes")

    assert packaging.sd_fingerprint(sid) != packaging.sd_fingerprint(sid, include_video=True)
    assert packaging.sd_fingerprint(sid) != packaging.sd_fingerprint(sid, systems={"nes"})
    assert packaging.sd_fingerprint(sid) != packaging.sd_fingerprint(sid, homebrew_roms={"x"})
    assert packaging.sd_fingerprint(sid) != packaging.sd_fingerprint(sid, excluded_roms={"x"})


def test_cached_zip_path_touches_mtime_of_existing_cache(env):
    sid = env
    _write(storage.roms_dir(sid, "nes") / "Game.nes")
    path_str, _ = packaging.build_sd_zip_cached(sid)
    import os
    old_mtime = os.stat(path_str).st_mtime
    os.utime(path_str, (old_mtime - 1000, old_mtime - 1000))

    _, _, exists = packaging.cached_zip_path(sid)

    assert exists is True
    assert os.stat(path_str).st_mtime > old_mtime - 1000


def test_build_progress_reports_full_completion_on_a_real_build(env):
    sid = env
    _write(storage.roms_dir(sid, "nes") / "Game.nes", b"x" * 100)

    calls = []
    packaging.build_sd_zip_cached(sid, on_progress=lambda d, t, n="": calls.append((d, t, n)))

    assert calls[0][:2] == (0, calls[0][1])
    assert calls[-1][0] == calls[-1][1]        # done == total at the end
    # …and it says WHICH file it just wrote. Compressing a library takes minutes, and a bar
    # with no words cannot be told apart from a hang — the name is the proof of life.
    assert calls[-1][2] == "Game.nes"


# ---------------------------------------------------------------------------
# cancellation
# ---------------------------------------------------------------------------

def test_build_sd_zip_cached_raises_and_cleans_up_temp_on_cancel(env):
    sid = env
    _write(storage.roms_dir(sid, "nes") / "Game.nes")
    cache_dir = config.DATA_DIR / "_cache"

    with pytest.raises(packaging.BuildCancelled):
        packaging.build_sd_zip_cached(sid, should_cancel=lambda: True)

    # no half-built cache artifact left behind
    assert not any(cache_dir.glob("sd-*.zip")) if cache_dir.exists() else True
    assert not any(cache_dir.glob("*.tmp")) if cache_dir.exists() else True


def test_run_sd_zip_build_job_success_marks_job_done(env):
    from app.services import jobs
    sid = env
    _write(storage.roms_dir(sid, "nes") / "Game.nes")
    job_id = "job-pkg-success"
    jobs.create(job_id, "sd_zip")

    packaging.run_sd_zip_build_job(job_id, sid)

    job = jobs.get(job_id)
    assert job.status == "done"
    assert job.progress == 1.0
    assert job.result["etag"] == packaging.sd_fingerprint(sid)


def test_run_sd_zip_build_job_throttles_progress_updates(env, monkeypatch):
    """Progress is only pushed to the job registry every ~0.5% (or at 100%) so a
    big library doesn't spam an update per file."""
    from app.services import jobs
    sid = env
    for i in range(300):
        _write(storage.roms_dir(sid, "nes") / f"g{i}.nes", b"x")
    job_id = "job-pkg-throttle"
    jobs.create(job_id, "sd_zip")

    seen_progress = []
    orig_update = jobs.update

    def spy_update(jid, **changes):
        if "progress" in changes:
            seen_progress.append(changes["progress"])
        return orig_update(jid, **changes)

    # run_sd_zip_build_job does a LOCAL `from . import jobs`, which still binds
    # to this same module object, so patching its `update` here is visible there.
    monkeypatch.setattr(jobs, "update", spy_update)

    packaging.run_sd_zip_build_job(job_id, sid)

    # far fewer progress writes than files -- most were throttled away
    assert 0 < len(seen_progress) < 300
    assert seen_progress[-1] == 1.0


def test_run_sd_zip_build_job_cancelled_marks_job_cancelled(env):
    from app.services import jobs
    sid = env
    _write(storage.roms_dir(sid, "nes") / "Game.nes")
    job_id = "job-pkg-cancel"
    jobs.create(job_id, "sd_zip")
    jobs.request_cancel(job_id)

    packaging.run_sd_zip_build_job(job_id, sid)

    assert jobs.get(job_id).status == "cancelled"


def test_run_sd_zip_build_job_failure_marks_job_failed(env, monkeypatch):
    from app.services import jobs
    sid = env
    job_id = "job-pkg-fail"
    jobs.create(job_id, "sd_zip")

    def boom(*a, **k):
        raise RuntimeError("disk exploded")

    monkeypatch.setattr(packaging, "build_sd_zip_cached", boom)

    packaging.run_sd_zip_build_job(job_id, sid)

    job = jobs.get(job_id)
    assert job.status == "failed"
    assert job.message == "disk exploded"


# ---------------------------------------------------------------------------
# _prune_sd_cache / prune_cache
# ---------------------------------------------------------------------------

def _fake_cache_zip(cache_dir, name, size, mtime):
    p = cache_dir / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"0" * size)
    import os
    os.utime(p, (mtime, mtime))
    return p


def test_prune_keeps_newest_within_count_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(packaging, "_SD_CACHE_KEEP", 2)
    monkeypatch.setattr(packaging, "_SD_CACHE_MAX_BYTES", 10_000)
    # Budget is normally clamped by real free disk (reserve). Pin it to the cap so
    # the test is deterministic on any CI runner, tight disk or not.
    monkeypatch.setattr(packaging, "_cache_budget", lambda _d: packaging._SD_CACHE_MAX_BYTES)
    cache_dir = tmp_path / "_cache"
    now = 1_000_000
    for i in range(5):
        _fake_cache_zip(cache_dir, f"sd-{i}.zip", 10, now + i)  # higher i = newer

    packaging._prune_sd_cache(cache_dir)

    remaining = {p.name for p in cache_dir.glob("sd-*.zip")}
    assert remaining == {"sd-4.zip", "sd-3.zip"}  # two newest survive


def test_prune_always_keeps_the_single_newest_even_if_oversized(tmp_path, monkeypatch):
    monkeypatch.setattr(packaging, "_SD_CACHE_KEEP", 4)
    monkeypatch.setattr(packaging, "_SD_CACHE_MAX_BYTES", 1)  # budget smaller than any one file
    cache_dir = tmp_path / "_cache"
    _fake_cache_zip(cache_dir, "sd-old.zip", 100, 1_000_000)
    _fake_cache_zip(cache_dir, "sd-new.zip", 100, 2_000_000)

    packaging._prune_sd_cache(cache_dir)

    remaining = {p.name for p in cache_dir.glob("sd-*.zip")}
    assert remaining == {"sd-new.zip"}  # newest kept despite blowing the budget


def test_prune_respects_byte_budget_over_count_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(packaging, "_SD_CACHE_KEEP", 10)
    monkeypatch.setattr(packaging, "_SD_CACHE_MAX_BYTES", 250)
    monkeypatch.setattr(packaging, "_cache_budget", lambda _d: packaging._SD_CACHE_MAX_BYTES)
    cache_dir = tmp_path / "_cache"
    _fake_cache_zip(cache_dir, "sd-a.zip", 100, 3_000_000)  # newest
    _fake_cache_zip(cache_dir, "sd-b.zip", 100, 2_000_000)  # 2nd: 200 <= 250 kept
    _fake_cache_zip(cache_dir, "sd-c.zip", 100, 1_000_000)  # 3rd: 300 > 250 dropped

    packaging._prune_sd_cache(cache_dir)

    remaining = {p.name for p in cache_dir.glob("sd-*.zip")}
    assert remaining == {"sd-a.zip", "sd-b.zip"}


def test_prune_cache_returns_count_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(packaging, "_SD_CACHE_KEEP", 1)
    monkeypatch.setattr(packaging, "_SD_CACHE_MAX_BYTES", 10_000)
    cache_dir = tmp_path / "_cache"
    _fake_cache_zip(cache_dir, "sd-a.zip", 10, 2_000_000)
    _fake_cache_zip(cache_dir, "sd-b.zip", 10, 1_000_000)

    removed = packaging.prune_cache()

    assert removed == 1


def test_prune_cache_on_missing_cache_dir_is_a_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)  # no _cache dir created

    assert packaging.prune_cache() == 0


# ---------------------------------------------------------------------------
# sd_content_size / session_has_content
# ---------------------------------------------------------------------------

def test_sd_content_size_sums_roms_covers_extra_and_firmware(env):
    sid = env
    _write(storage.roms_dir(sid, "nes") / "Game.nes", b"a" * 10)
    _write(storage.covers_dir(sid, "nes") / "Game.img", b"b" * 5)
    _write(storage.extra_dir(sid) / "bios" / "nes" / "disksys.rom", b"c" * 7)
    _write(storage.firmware_path(sid), b"d" * 3)
    _write(storage.scratch_dir(sid) / "ignored.zip", b"e" * 1000)  # never counted

    assert packaging.sd_content_size(sid) == 10 + 5 + 7 + 3


def test_sd_content_size_includes_pico8_core_by_default(env, monkeypatch, tmp_path):
    sid = env
    cores = tmp_path / "fake_cores"
    _write(cores / "pico8.gnw", b"z" * 20)
    monkeypatch.setattr(pico8core, "ensure_cores_dir", lambda force=False: cores)

    assert packaging.sd_content_size(sid) == 20


def test_sd_content_size_excludes_pico8_core_when_filtered_out(env, monkeypatch, tmp_path):
    sid = env
    cores = tmp_path / "fake_cores"
    _write(cores / "pico8.gnw", b"z" * 20)
    monkeypatch.setattr(pico8core, "ensure_cores_dir", lambda force=False: cores)

    assert packaging.sd_content_size(sid, systems={"nes"}) == 0


def test_sd_content_size_empty_session_is_zero(env):
    assert packaging.sd_content_size(env) == 0


def test_session_has_content_false_for_empty_and_scratch_only(env):
    sid = env
    assert packaging.session_has_content(sid) is False

    _write(storage.scratch_dir(sid) / "upload.zip")
    assert packaging.session_has_content(sid) is False


def test_session_has_content_true_once_a_rom_exists(env):
    sid = env
    _write(storage.roms_dir(sid, "nes") / "Game.nes")

    assert packaging.session_has_content(sid) is True


def test_session_has_content_false_when_root_missing(env):
    # session_root() is never created for this session id -> early-return path
    assert packaging.session_has_content("never-used-session") is False


class TestSdCacheBudgetYieldsToDisk:
    """A cache that fills the disk has stopped being an optimisation.

    The budget was a flat 12 GB, which is a fine trade on an empty disk and a bad one on a
    full one: at 99% used, the pruner was dutifully DEFENDING 2.7 GB of zips that rebuild in
    a minute — while uploads and the database had nowhere left to write.
    """

    def _cache(self, tmp_path, sizes_mb):
        from app.services import packaging
        cache = tmp_path / "_cache"
        cache.mkdir()
        for i, mb in enumerate(sizes_mb):
            # Sparse, not written: these cases go up to a GiB apiece, and
            # b"\0" * (1 << 30) builds the whole gibibyte in RAM before it ever
            # reaches the disk — on a Pi that is the spike, and three kept pytest
            # runs of it filled a 4 GB /tmp. truncate() costs no memory and no
            # blocks, and the code under test only ever reads st_size
            # (packaging.py: _cache_budget, _prune_sd_cache), never the contents.
            with open(cache / f"sd-{i:040x}.zip", "wb") as fh:
                fh.truncate(mb * 1024 * 1024)
        return packaging, cache

    def _disk(self, monkeypatch, packaging, free_gb):
        import collections
        usage = collections.namedtuple("usage", "total used free")
        monkeypatch.setattr(packaging.shutil, "disk_usage",
                            lambda _p: usage(200 << 30, (200 - free_gb) << 30, free_gb << 30))

    def test_a_roomy_disk_keeps_the_full_budget(self, tmp_path, monkeypatch):
        packaging, cache = self._cache(tmp_path, [1, 1])
        self._disk(monkeypatch, packaging, free_gb=100)

        assert packaging._cache_budget(cache) == packaging._SD_CACHE_MAX_BYTES

    def test_a_tight_disk_shrinks_the_budget_to_nothing(self, tmp_path, monkeypatch):
        packaging, cache = self._cache(tmp_path, [1, 1])
        self._disk(monkeypatch, packaging, free_gb=2)      # 2 GB free, reserve is 20

        assert packaging._cache_budget(cache) == 0

    def test_a_tight_disk_evicts_everything_but_the_newest(self, tmp_path, monkeypatch):
        # The newest is always kept: it is the zip just built or being served, and its path
        # has already been handed to the caller.
        packaging, cache = self._cache(tmp_path, [200, 200, 200])
        self._disk(monkeypatch, packaging, free_gb=1)

        packaging._prune_sd_cache(cache)

        assert len(list(cache.glob("sd-*.zip"))) == 1

    def test_the_cache_may_spend_what_it_is_already_holding(self, tmp_path, monkeypatch):
        """Its own bytes count as 'used' on the disk, so they are part of what it can
        afford — otherwise a cache would evict itself the moment it grew."""
        held = 1024 * 1024 * 1024                              # 1 GiB of zips
        packaging, cache = self._cache(tmp_path, [1024])
        free = 25 << 30
        self._disk(monkeypatch, packaging, free_gb=25)

        budget = packaging._cache_budget(cache)

        # free + held - reserve: the zips it holds are not spent, they are spendable.
        assert budget == free + held - packaging._SD_CACHE_DISK_RESERVE
