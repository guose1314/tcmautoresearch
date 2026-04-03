"""Web Console 任务持久化存储。"""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

SAFE_JOB_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class PersistentJobStore:
    """以 JSON 文件持久化任务快照与事件流。"""

    def __init__(self, storage_dir: str | Path):
        self.storage_dir = Path(storage_dir).expanduser().resolve()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _normalize_job_id(self, job_id: str) -> str:
        normalized_job_id = str(job_id or "").strip()
        if not normalized_job_id or not SAFE_JOB_ID_PATTERN.fullmatch(normalized_job_id):
            raise ValueError("非法 job_id")
        return normalized_job_id

    def _job_path(self, job_id: str, *, suffix: str = ".json") -> Path:
        normalized_job_id = self._normalize_job_id(job_id)
        candidate = (self.storage_dir / f"{normalized_job_id}{suffix}").resolve()
        candidate.relative_to(self.storage_dir)
        return candidate

    def load_jobs(self) -> Dict[str, Dict[str, Any]]:
        jobs: Dict[str, Dict[str, Any]] = {}
        for path in sorted(self.storage_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            job_id = str(payload.get("job", {}).get("job_id") or path.stem).strip()
            if not job_id:
                continue
            jobs[job_id] = payload
        return jobs

    def get_job_payload(self, job_id: str) -> Dict[str, Any] | None:
        try:
            path = self._job_path(job_id)
        except (ValueError, OSError):
            return None
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def list_job_payloads(self, limit: int = 10) -> list[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 100))
        jobs = list(self.load_jobs().values())
        jobs.sort(
            key=lambda payload: (
                str((payload.get("job") or {}).get("created_at") or ""),
                str((payload.get("job") or {}).get("started_at") or ""),
                str((payload.get("job") or {}).get("completed_at") or ""),
                str((payload.get("job") or {}).get("job_id") or ""),
            ),
            reverse=True,
        )
        return jobs[:safe_limit]

    def get_storage_summary(self) -> Dict[str, Any]:
        total_size_bytes = 0
        latest_updated_at = None
        job_file_count = 0
        temp_file_count = 0
        for path in self.storage_dir.glob("*"):
            if not path.is_file():
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            total_size_bytes += int(stat.st_size)
            if latest_updated_at is None or stat.st_mtime > latest_updated_at:
                latest_updated_at = stat.st_mtime
            if path.suffix == ".json":
                job_file_count += 1
            elif path.suffix == ".tmp":
                temp_file_count += 1

        return {
            "storage_dir": str(self.storage_dir),
            "job_file_count": job_file_count,
            "temp_file_count": temp_file_count,
            "total_size_bytes": total_size_bytes,
            "stored_job_count": len(self.load_jobs()),
            "latest_updated_at": None if latest_updated_at is None else datetime.fromtimestamp(latest_updated_at).isoformat(),
        }

    def save_job(self, payload: Dict[str, Any]) -> None:
        job = payload.get("job") if isinstance(payload, dict) else None
        job_id = str((job or {}).get("job_id") or "").strip()
        if not job_id:
            raise ValueError("job 持久化缺少 job_id")

        path = self._job_path(job_id)
        tmp_path = self._job_path(job_id, suffix=".json.tmp")
        serialized = json.dumps(payload, ensure_ascii=False, indent=2)
        with self._lock:
            tmp_path.write_text(serialized, encoding="utf-8")
            tmp_path.replace(path)

    def delete_job(self, job_id: str) -> bool:
        try:
            path = self._job_path(job_id)
            tmp_path = self._job_path(job_id, suffix=".json.tmp")
        except (ValueError, OSError):
            return False
        deleted = False
        with self._lock:
            for candidate in (path, tmp_path):
                try:
                    candidate.unlink()
                    deleted = True
                except FileNotFoundError:
                    continue
        return deleted