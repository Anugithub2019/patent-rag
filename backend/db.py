import sqlite3
import os
import time

# Database lives in the project root, not inside backend/
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "upload_records.db")


def get_connection():
    """Get a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the upload_records table if it doesn't exist."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS upload_records (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name       TEXT    NOT NULL,
            file_path       TEXT    NOT NULL,
            file_hash       TEXT    NOT NULL,
            file_size       INTEGER NOT NULL,
            corpus          TEXT    NOT NULL DEFAULT 'patentrag',
            status          TEXT    NOT NULL DEFAULT 'success',
            uploaded_at     REAL    NOT NULL,
            error_message   TEXT
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_file_hash ON upload_records(file_hash)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_file_name ON upload_records(file_name)
    """)

    conn.commit()
    conn.close()
    print(f"📁 Database initialized at: {DB_PATH}")


def is_uploaded(file_hash: str) -> bool:
    """Check if a file with the given hash has already been successfully uploaded."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM upload_records WHERE file_hash = ? AND status = 'success' LIMIT 1",
        (file_hash,)
    )
    result = cursor.fetchone() is not None
    conn.close()
    return result


def mark_uploaded(file_name: str, file_path: str, file_hash: str, file_size: int,
                  corpus: str = "patentrag", status: str = "success",
                  error_message: str = None):
    """Record an upload attempt in the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO upload_records (file_name, file_path, file_hash, file_size,
                                     corpus, status, uploaded_at, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        file_name,
        file_path,
        file_hash,
        file_size,
        corpus,
        status,
        time.time(),
        error_message
    ))
    conn.commit()
    conn.close()


def get_stats():
    """Return summary statistics from the database."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            COUNT(*)                                             AS total_attempts,
            SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END)  AS success_count,
            SUM(CASE WHEN status = 'failed'  THEN 1 ELSE 0 END)  AS fail_count,
            COUNT(DISTINCT file_hash)                            AS unique_files
        FROM upload_records
    """)
    row = cursor.fetchone()

    cursor.execute("""
        SELECT uploaded_at
        FROM upload_records
        WHERE status = 'success'
        ORDER BY uploaded_at DESC
        LIMIT 1
    """)
    last_row = cursor.fetchone()
    last_upload = last_row["uploaded_at"] if last_row else None

    conn.close()

    return {
        "total_attempts": row["total_attempts"] or 0,
        "success_count": row["success_count"] or 0,
        "fail_count": row["fail_count"] or 0,
        "unique_files": row["unique_files"] or 0,
        "last_upload": last_upload,
    }


def list_uploaded():
    """Return a list of all successfully uploaded files, newest first."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT file_name, file_path, file_size, uploaded_at
        FROM upload_records
        WHERE status = 'success'
        ORDER BY uploaded_at DESC
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def list_failed():
    """Return a list of files that failed to upload."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT file_name, file_path, error_message, uploaded_at
        FROM upload_records
        WHERE status = 'failed'
        ORDER BY uploaded_at DESC
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows
