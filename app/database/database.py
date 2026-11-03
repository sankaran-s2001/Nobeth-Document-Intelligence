import sqlite3
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List
from app.config import config
from app.schemas.document import MasterDocument

logger = logging.getLogger("nobeth.database")


def get_db_connection() -> sqlite3.Connection:
    config.ensure_directories()
    conn = sqlite3.connect(str(config.db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def init_db() -> None:
    conn = get_db_connection()
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    original_filename TEXT NOT NULL,
                    file_format TEXT NOT NULL,
                    file_size_bytes INTEGER NOT NULL,
                    page_count INTEGER DEFAULT 1,
                    status TEXT NOT NULL,
                    progress_percent INTEGER DEFAULT 0,
                    stage_label TEXT DEFAULT '',
                    error_message TEXT DEFAULT '',
                    result_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at);
                """
            )
        logger.info("SQLite database initialized at %s", config.db_path)
    finally:
        conn.close()


def create_job(
    job_id: str,
    original_filename: str,
    file_format: str,
    file_size_bytes: int,
    page_count: int = 1,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=config.job_retention_hours)
    now_str = now.isoformat()
    expires_str = expires.isoformat()

    conn = get_db_connection()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    job_id, original_filename, file_format, file_size_bytes,
                    page_count, status, progress_percent, stage_label,
                    error_message, result_json, created_at, updated_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    job_id,
                    original_filename,
                    file_format,
                    file_size_bytes,
                    page_count,
                    "queued",
                    5,
                    "Document queued for processing",
                    "",
                    None,
                    now_str,
                    now_str,
                    expires_str,
                ),
            )
        return {
            "job_id": job_id,
            "original_filename": original_filename,
            "file_format": file_format,
            "status": "queued",
            "progress_percent": 5,
            "stage_label": "Document queued for processing",
            "created_at": now_str,
        }
    finally:
        conn.close()


def update_job_status(
    job_id: str,
    status: str,
    progress_percent: int,
    stage_label: str,
    error_message: str = "",
    page_count: Optional[int] = None,
) -> None:
    now_str = datetime.now(timezone.utc).isoformat()
    conn = get_db_connection()
    try:
        with conn:
            if page_count is not None:
                conn.execute(
                    """
                    UPDATE jobs SET
                        status = ?,
                        progress_percent = ?,
                        stage_label = ?,
                        error_message = ?,
                        page_count = ?,
                        updated_at = ?
                    WHERE job_id = ?;
                    """,
                    (status, progress_percent, stage_label, error_message, page_count, now_str, job_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE jobs SET
                        status = ?,
                        progress_percent = ?,
                        stage_label = ?,
                        error_message = ?,
                        updated_at = ?
                    WHERE job_id = ?;
                    """,
                    (status, progress_percent, stage_label, error_message, now_str, job_id),
                )
    finally:
        conn.close()


def save_job_result(job_id: str, master_doc: MasterDocument) -> None:
    now_str = datetime.now(timezone.utc).isoformat()
    doc_json = master_doc.model_dump_json(indent=2)
    conn = get_db_connection()
    try:
        with conn:
            conn.execute(
                """
                UPDATE jobs SET
                    status = 'ready',
                    progress_percent = 100,
                    stage_label = 'Processing complete. Ready for review.',
                    result_json = ?,
                    page_count = ?,
                    updated_at = ?
                WHERE job_id = ?;
                """,
                (doc_json, len(master_doc.pages), now_str, job_id),
            )
    finally:
        conn.close()


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            """
            SELECT job_id, original_filename, file_format, file_size_bytes,
                   page_count, status, progress_percent, stage_label,
                   error_message, result_json, created_at, updated_at, expires_at
            FROM jobs WHERE job_id = ?;
            """,
            (job_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        if d.get("result_json"):
            try:
                d["result"] = json.loads(d["result_json"])
            except Exception:
                d["result"] = None
        else:
            d["result"] = None
        return d
    finally:
        conn.close()


def get_all_jobs(limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            """
            SELECT job_id, original_filename, file_format, file_size_bytes,
                   page_count, status, progress_percent, stage_label,
                   error_message, created_at, updated_at, expires_at
            FROM jobs ORDER BY created_at DESC LIMIT ?;
            """,
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def delete_job(job_id: str) -> bool:
    conn = get_db_connection()
    try:
        with conn:
            cursor = conn.execute("DELETE FROM jobs WHERE job_id = ?;", (job_id,))
            return cursor.rowcount > 0
    finally:
        conn.close()


def cleanup_expired_jobs() -> int:
    """Removes records older than configured retention period."""
    now_str = datetime.now(timezone.utc).isoformat()
    conn = get_db_connection()
    try:
        # Find expired job IDs to clean their filesystem assets
        cursor = conn.execute("SELECT job_id FROM jobs WHERE expires_at < ?;", (now_str,))
        expired_ids = [r["job_id"] for r in cursor.fetchall()]
        
        with conn:
            conn.execute("DELETE FROM jobs WHERE expires_at < ?;", (now_str,))
            
        return len(expired_ids)
    finally:
        conn.close()

