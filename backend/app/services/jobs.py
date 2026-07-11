"""
In-memory job registry for long-running work (video encoding, SD-zip build).

Files persist on disk + DB, but live progress is ephemeral (lost on restart) —
fine for MVP; a restart just means re-checking the DB status. When the app
moves to Docker/multiple workers this should become Redis/RQ or similar.

Thread-safe (plain threading.Lock, synchronous API) so both async endpoints and
CPU-bound worker threads (run_in_threadpool) can report progress and observe
cancellation uniformly.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, replace

# status: queued -> running -> done | failed | cancelled
_jobs: dict[str, "Job"] = {}
_cancelled: set[str] = set()
_lock = threading.Lock()


@dataclass(frozen=True)
class Job:
    id: str
    kind: str                 # e.g. "video_encode", "sd_zip"
    status: str = "queued"
    progress: float = 0.0     # 0..1 (best-effort)
    message: str = ""
    result: dict | None = None

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "progress": round(self.progress, 3),
            "message": self.message,
            "result": self.result,
        }


def create(job_id: str, kind: str) -> Job:
    with _lock:
        job = Job(id=job_id, kind=kind)
        _jobs[job_id] = job
        _cancelled.discard(job_id)
        return job


def update(job_id: str, **changes) -> Job | None:
    """Immutably replace the stored job with the given field changes."""
    with _lock:
        current = _jobs.get(job_id)
        if current is None:
            return None
        updated = replace(current, **changes)
        _jobs[job_id] = updated
        return updated


def get(job_id: str) -> Job | None:
    with _lock:
        return _jobs.get(job_id)


def request_cancel(job_id: str) -> bool:
    """Ask a running job to stop. Returns False for an unknown job. The worker
    is responsible for polling is_cancelled() and bailing out cleanly."""
    with _lock:
        if job_id not in _jobs:
            return False
        _cancelled.add(job_id)
        return True


def is_cancelled(job_id: str) -> bool:
    with _lock:
        return job_id in _cancelled
