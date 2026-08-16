import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Optional


# Database lives in the project root, not inside kg_builder/.
DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "upload_records.db",
)

SCHEMA_VERSION = 2
DEFAULT_CLAIM_STALE_AFTER_SECONDS = 15 * 60
COMPLETED_STATUSES = {"success", "failed"}


class StaleUploadClaimError(RuntimeError):
    """Raised when a worker tries to finish a claim it no longer owns."""


@dataclass(frozen=True)
class UploadClaim:
    acquired: bool
    reason: str
    token: Optional[str] = None


def get_connection():
    """Create a configured SQLite connection."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


@contextmanager
def _connection(*, write=False, enable_wal=False):
    """Yield a connection and always commit/rollback and close it safely."""
    conn = get_connection()
    try:
        if enable_wal:
            conn.execute("PRAGMA journal_mode = WAL")
        if write:
            conn.execute("BEGIN IMMEDIATE")
        yield conn
        if write:
            conn.commit()
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.close()


def _table_exists(conn, table_name):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _create_upload_records_table(conn):
    conn.execute("""
        CREATE TABLE upload_records (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name       TEXT    NOT NULL,
            file_path       TEXT    NOT NULL,
            file_hash       TEXT    NOT NULL CHECK (length(trim(file_hash)) > 0),
            file_size       INTEGER NOT NULL CHECK (file_size >= 0),
            corpus          TEXT    NOT NULL CHECK (length(trim(corpus)) > 0),
            status          TEXT    NOT NULL CHECK (status IN ('success', 'failed')),
            uploaded_at     REAL    NOT NULL,
            error_message   TEXT
        )
    """)


def _create_upload_claims_table(conn):
    conn.execute("""
        CREATE TABLE upload_claims (
            file_hash       TEXT    NOT NULL CHECK (length(trim(file_hash)) > 0),
            corpus          TEXT    NOT NULL CHECK (length(trim(corpus)) > 0),
            file_name       TEXT    NOT NULL,
            file_path       TEXT    NOT NULL,
            file_size       INTEGER NOT NULL CHECK (file_size >= 0),
            status          TEXT    NOT NULL
                                    CHECK (status IN ('processing', 'success', 'failed')),
            claim_token     TEXT UNIQUE,
            attempt_count   INTEGER NOT NULL DEFAULT 1 CHECK (attempt_count >= 1),
            claimed_at      REAL    NOT NULL,
            updated_at      REAL    NOT NULL,
            error_message   TEXT,
            PRIMARY KEY (file_hash, corpus),
            CHECK (
                (status = 'processing' AND claim_token IS NOT NULL)
                OR
                (status IN ('success', 'failed') AND claim_token IS NULL)
            )
        )
    """)


def _create_indexes(conn):
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_upload_records_hash_corpus_status
        ON upload_records (file_hash, corpus, status)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_upload_records_corpus_status_time
        ON upload_records (corpus, status, uploaded_at DESC)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_upload_records_file_name
        ON upload_records (file_name)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_upload_claims_status_time
        ON upload_claims (status, updated_at)
    """)


def _migrate_legacy_upload_records(conn):
    """Rebuild the legacy table with validation while preserving its rows."""
    conn.execute("ALTER TABLE upload_records RENAME TO upload_records_legacy")
    _create_upload_records_table(conn)

    conn.execute("""
        INSERT INTO upload_records (
            id, file_name, file_path, file_hash, file_size,
            corpus, status, uploaded_at, error_message
        )
        SELECT
            id,
            COALESCE(file_name, ''),
            COALESCE(file_path, ''),
            CASE
                WHEN length(trim(COALESCE(file_hash, ''))) > 0 THEN file_hash
                ELSE 'legacy-invalid-' || id
            END,
            CASE WHEN file_size >= 0 THEN file_size ELSE 0 END,
            CASE
                WHEN length(trim(COALESCE(corpus, ''))) > 0 THEN corpus
                ELSE 'legacy-unverified'
            END,
            CASE WHEN status = 'success' THEN 'success' ELSE 'failed' END,
            COALESCE(uploaded_at, 0),
            CASE
                WHEN status IN ('success', 'failed') THEN error_message
                ELSE trim(
                    COALESCE(error_message || '; ', '')
                    || 'Migrated invalid status: '
                    || COALESCE(status, 'NULL')
                )
            END
        FROM upload_records_legacy
    """)

    conn.execute("DROP TABLE upload_records_legacy")


def _seed_upload_claims(conn):
    """Build current deduplication state from the migrated attempt history."""
    conn.execute("""
        INSERT INTO upload_claims (
            file_hash, corpus, file_name, file_path, file_size,
            status, claim_token, attempt_count,
            claimed_at, updated_at, error_message
        )
        SELECT
            record.file_hash,
            record.corpus,
            record.file_name,
            record.file_path,
            record.file_size,
            record.status,
            NULL,
            (
                SELECT COUNT(*)
                FROM upload_records AS attempts
                WHERE attempts.file_hash = record.file_hash
                  AND attempts.corpus = record.corpus
            ),
            record.uploaded_at,
            record.uploaded_at,
            record.error_message
        FROM upload_records AS record
        WHERE record.id = COALESCE(
            (
                SELECT successful.id
                FROM upload_records AS successful
                WHERE successful.file_hash = record.file_hash
                  AND successful.corpus = record.corpus
                  AND successful.status = 'success'
                ORDER BY successful.uploaded_at DESC, successful.id DESC
                LIMIT 1
            ),
            (
                SELECT latest.id
                FROM upload_records AS latest
                WHERE latest.file_hash = record.file_hash
                  AND latest.corpus = record.corpus
                ORDER BY latest.uploaded_at DESC, latest.id DESC
                LIMIT 1
            )
        )
    """)


def init_db():
    """Create or migrate the upload database to the current schema."""
    with _connection(write=True, enable_wal=True) as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError(
                f"Database schema version {version} is newer than supported "
                f"version {SCHEMA_VERSION}"
            )

        if version < SCHEMA_VERSION:
            if _table_exists(conn, "upload_claims"):
                conn.execute("DROP TABLE upload_claims")

            if _table_exists(conn, "upload_records"):
                _migrate_legacy_upload_records(conn)
            else:
                _create_upload_records_table(conn)

            _create_upload_claims_table(conn)
            _create_indexes(conn)
            _seed_upload_claims(conn)
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        else:
            # Index creation is idempotent and repairs manually removed indexes.
            _create_indexes(conn)

    print(f"📁 Database initialized at: {DB_PATH}")


def claim_upload(
    *,
    file_name,
    file_path,
    file_hash,
    file_size,
    corpus,
    stale_after_seconds=DEFAULT_CLAIM_STALE_AFTER_SECONDS,
):
    """Atomically claim a file/destination pair before making a remote POST."""
    if not file_hash or not file_hash.strip():
        raise ValueError("file_hash must not be empty")
    if not corpus or not corpus.strip():
        raise ValueError("corpus must not be empty")
    if file_size < 0:
        raise ValueError("file_size must not be negative")
    if stale_after_seconds <= 0:
        raise ValueError("stale_after_seconds must be positive")

    now = time.time()
    token = uuid.uuid4().hex

    with _connection(write=True) as conn:
        existing = conn.execute(
            """SELECT status, updated_at
               FROM upload_claims
               WHERE file_hash = ? AND corpus = ?""",
            (file_hash, corpus),
        ).fetchone()

        if existing is not None:
            if existing["status"] == "success":
                return UploadClaim(False, "already_uploaded")

            is_active = (
                existing["status"] == "processing"
                and existing["updated_at"] > now - stale_after_seconds
            )
            if is_active:
                return UploadClaim(False, "in_progress")

            conn.execute(
                """UPDATE upload_claims
                   SET file_name = ?, file_path = ?, file_size = ?,
                       status = 'processing', claim_token = ?,
                       attempt_count = attempt_count + 1,
                       claimed_at = ?, updated_at = ?, error_message = NULL
                   WHERE file_hash = ? AND corpus = ?""",
                (
                    file_name,
                    file_path,
                    file_size,
                    token,
                    now,
                    now,
                    file_hash,
                    corpus,
                ),
            )
            return UploadClaim(True, "claimed", token)

        conn.execute(
            """INSERT INTO upload_claims (
                   file_hash, corpus, file_name, file_path, file_size,
                   status, claim_token, attempt_count,
                   claimed_at, updated_at, error_message
               ) VALUES (?, ?, ?, ?, ?, 'processing', ?, 1, ?, ?, NULL)""",
            (
                file_hash,
                corpus,
                file_name,
                file_path,
                file_size,
                token,
                now,
                now,
            ),
        )
        return UploadClaim(True, "claimed", token)


def finish_upload(claim_token, status, error_message=None):
    """Complete an owned upload claim and append its result to attempt history."""
    if status not in COMPLETED_STATUSES:
        raise ValueError(f"Invalid completed upload status: {status}")
    if not claim_token:
        raise ValueError("claim_token must not be empty")

    now = time.time()
    with _connection(write=True) as conn:
        claim = conn.execute(
            """SELECT file_name, file_path, file_hash, file_size, corpus
               FROM upload_claims
               WHERE claim_token = ? AND status = 'processing'""",
            (claim_token,),
        ).fetchone()
        if claim is None:
            raise StaleUploadClaimError(
                "Upload claim is missing, completed, or owned by another worker"
            )

        conn.execute(
            """INSERT INTO upload_records (
                   file_name, file_path, file_hash, file_size,
                   corpus, status, uploaded_at, error_message
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                claim["file_name"],
                claim["file_path"],
                claim["file_hash"],
                claim["file_size"],
                claim["corpus"],
                status,
                now,
                error_message,
            ),
        )
        result = conn.execute(
            """UPDATE upload_claims
               SET status = ?, claim_token = NULL,
                   updated_at = ?, error_message = ?
               WHERE file_hash = ? AND corpus = ?
                 AND claim_token = ? AND status = 'processing'""",
            (
                status,
                now,
                error_message,
                claim["file_hash"],
                claim["corpus"],
                claim_token,
            ),
        )
        if result.rowcount != 1:
            raise StaleUploadClaimError(
                "Upload claim changed before completion could be recorded"
            )


def is_uploaded(file_hash, corpus):
    """Return whether a file hash has completed successfully at a destination."""
    with _connection() as conn:
        row = conn.execute(
            """SELECT 1 FROM upload_claims
               WHERE file_hash = ? AND corpus = ? AND status = 'success'
               LIMIT 1""",
            (file_hash, corpus),
        ).fetchone()
        return row is not None


def get_stats(corpus=None):
    """Return claim/attempt statistics, optionally scoped to one destination."""
    record_filter = "WHERE corpus = ?" if corpus is not None else ""
    record_params = (corpus,) if corpus is not None else ()
    success_filter = (
        "WHERE status = 'success' AND corpus = ?"
        if corpus is not None
        else "WHERE status = 'success'"
    )
    success_params = (corpus,) if corpus is not None else ()
    claim_filter = (
        "WHERE status = 'processing' AND corpus = ?"
        if corpus is not None
        else "WHERE status = 'processing'"
    )
    claim_params = (corpus,) if corpus is not None else ()
    attempt_filter = "WHERE corpus = ?" if corpus is not None else ""
    attempt_params = (corpus,) if corpus is not None else ()

    with _connection() as conn:
        row = conn.execute(
            f"""SELECT
                    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_count,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS fail_count
                FROM upload_records
                {record_filter}""",
            record_params,
        ).fetchone()

        unique_files = conn.execute(
            f"""SELECT COUNT(*) AS unique_files
                FROM (
                    SELECT file_hash, corpus
                    FROM upload_records
                    {success_filter}
                    GROUP BY file_hash, corpus
                )""",
            success_params,
        ).fetchone()["unique_files"]

        last_row = conn.execute(
            f"""SELECT uploaded_at
                FROM upload_records
                {success_filter}
                ORDER BY uploaded_at DESC
                LIMIT 1""",
            success_params,
        ).fetchone()

        in_progress_count = conn.execute(
            f"SELECT COUNT(*) AS count FROM upload_claims {claim_filter}",
            claim_params,
        ).fetchone()["count"]

        total_attempts = conn.execute(
            f"""SELECT COALESCE(SUM(attempt_count), 0) AS count
                FROM upload_claims {attempt_filter}""",
            attempt_params,
        ).fetchone()["count"]

    success_count = row["success_count"] or 0
    fail_count = row["fail_count"] or 0
    abandoned_count = max(
        total_attempts - success_count - fail_count - in_progress_count,
        0,
    )

    return {
        "total_attempts": total_attempts,
        "success_count": success_count,
        "fail_count": fail_count,
        "unique_files": unique_files or 0,
        "in_progress_count": in_progress_count or 0,
        "abandoned_count": abandoned_count,
        "last_upload": last_row["uploaded_at"] if last_row else None,
    }


def list_uploaded(corpus=None):
    """Return successful upload attempts, newest first."""
    where = "AND corpus = ?" if corpus is not None else ""
    params = (corpus,) if corpus is not None else ()
    with _connection() as conn:
        rows = conn.execute(
            f"""SELECT file_name, file_path, file_hash, file_size,
                       corpus, uploaded_at
                FROM upload_records
                WHERE status = 'success' {where}
                ORDER BY uploaded_at DESC, id DESC""",
            params,
        ).fetchall()
        return [dict(row) for row in rows]


def list_failed(corpus=None):
    """Return failed upload attempts, newest first."""
    where = "AND corpus = ?" if corpus is not None else ""
    params = (corpus,) if corpus is not None else ()
    with _connection() as conn:
        rows = conn.execute(
            f"""SELECT file_name, file_path, file_hash, file_size,
                       corpus, error_message, uploaded_at
                FROM upload_records
                WHERE status = 'failed' {where}
                ORDER BY uploaded_at DESC, id DESC""",
            params,
        ).fetchall()
        return [dict(row) for row in rows]
