"""任务台账：直接使用 sqlite3，单表 + 显式 SQL。

刻意不引入 ORM：表结构简单，显式 SQL 更容易看清实际读写。
连接按线程创建（sqlite3 连接不能跨线程），并开启 WAL 以支持读写并发。
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from . import paths

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id      TEXT PRIMARY KEY,
    source_url  TEXT NOT NULL,
    title       TEXT NOT NULL DEFAULT '',
    variant     TEXT NOT NULL DEFAULT '',
    kind        TEXT NOT NULL DEFAULT 'vod',
    status      TEXT NOT NULL DEFAULT 'queued',
    out_dir     TEXT NOT NULL DEFAULT '',
    file_hint   TEXT NOT NULL DEFAULT '',
    bytes_total INTEGER NOT NULL DEFAULT 0,
    argv_json   TEXT NOT NULL DEFAULT '[]',
    log_path    TEXT NOT NULL DEFAULT '',
    note        TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC);
"""

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

ACTIVE_STATUSES = (STATUS_QUEUED, STATUS_RUNNING)


@dataclass
class JobRecord:
    job_id: str
    source_url: str
    title: str
    variant: str
    kind: str
    status: str
    out_dir: str
    file_hint: str
    bytes_total: int
    argv_json: str
    log_path: str
    note: str
    created_at: float
    updated_at: float

    @property
    def argv(self) -> List[str]:
        try:
            value = json.loads(self.argv_json)
        except (TypeError, ValueError):
            return []
        return [str(x) for x in value] if isinstance(value, list) else []

    def to_public(self) -> Dict[str, Any]:
        return {
            "id": self.job_id,
            "source": self.source_url,
            "title": self.title,
            "variant": self.variant,
            "kind": self.kind,
            "status": self.status,
            "outDir": self.out_dir,
            "fileHint": self.file_hint,
            "bytesTotal": self.bytes_total,
            "logPath": self.log_path,
            "note": self.note,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }


def _row_to_record(row: sqlite3.Row) -> JobRecord:
    return JobRecord(
        job_id=row["job_id"],
        source_url=row["source_url"],
        title=row["title"],
        variant=row["variant"],
        kind=row["kind"],
        status=row["status"],
        out_dir=row["out_dir"],
        file_hint=row["file_hint"],
        bytes_total=row["bytes_total"],
        argv_json=row["argv_json"],
        log_path=row["log_path"],
        note=row["note"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class JobStore:
    """线程本地的 sqlite3 连接池（这里每个线程一条连接即可）。"""

    def __init__(self, db_file: Optional[Path] = None):
        self._db_file = db_file or paths.db_path()
        self._local = threading.local()
        self._bootstrap_lock = threading.Lock()
        self._bootstrap()

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            self._db_file.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self._db_file), timeout=10.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = conn
        return conn

    def _bootstrap(self) -> None:
        with self._bootstrap_lock:
            self._conn().executescript(SCHEMA)
            self._conn().commit()

    def insert(self, *, source_url: str, title: str, variant: str, kind: str,
               out_dir: str, file_hint: str, argv: Iterable[str], log_path: str,
               status: str = STATUS_QUEUED, note: str = "") -> JobRecord:
        now = time.time()
        job_id = uuid.uuid4().hex
        conn = self._conn()
        conn.execute(
            """INSERT INTO jobs (job_id, source_url, title, variant, kind, status,
                                 out_dir, file_hint, bytes_total, argv_json, log_path,
                                 note, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,0,?,?,?,?,?)""",
            (job_id, source_url, title, variant, kind, status, out_dir, file_hint,
             json.dumps(list(argv), ensure_ascii=False), log_path, note, now, now),
        )
        conn.commit()
        return self.get(job_id)  # type: ignore[return-value]

    def get(self, job_id: str) -> Optional[JobRecord]:
        row = self._conn().execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        return _row_to_record(row) if row else None

    def list(self, status: Optional[str] = None, limit: int = 500) -> List[JobRecord]:
        conn = self._conn()
        if status and status != "all":
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [_row_to_record(row) for row in rows]

    def update(self, job_id: str, **fields: Any) -> Optional[JobRecord]:
        if not fields:
            return self.get(job_id)
        allowed = {"status", "bytes_total", "note", "log_path", "file_hint", "title", "argv_json"}
        assignments = []
        values: List[Any] = []
        for key, value in fields.items():
            if key not in allowed:
                continue
            if key == "argv_json" and not isinstance(value, str):
                value = json.dumps(list(value), ensure_ascii=False)
            assignments.append(f"{key} = ?")
            values.append(value)
        if not assignments:
            return self.get(job_id)
        assignments.append("updated_at = ?")
        values.append(time.time())
        values.append(job_id)
        conn = self._conn()
        conn.execute(f"UPDATE jobs SET {', '.join(assignments)} WHERE job_id = ?", values)
        conn.commit()
        return self.get(job_id)

    def delete(self, job_id: str) -> None:
        conn = self._conn()
        conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
        conn.commit()

    def purge_by_status(self, status: str) -> None:
        conn = self._conn()
        conn.execute("DELETE FROM jobs WHERE status = ?", (status,))
        conn.commit()

    def mark_orphans_failed(self) -> int:
        """上次进程被杀时留下的 running 记录，启动时统一收敛为 failed。"""
        conn = self._conn()
        cur = conn.execute(
            "UPDATE jobs SET status = ?, note = ?, updated_at = ? WHERE status IN (?,?)",
            (STATUS_FAILED, "进程异常退出", time.time(), STATUS_RUNNING, STATUS_QUEUED),
        )
        conn.commit()
        return cur.rowcount or 0


job_store = JobStore()
