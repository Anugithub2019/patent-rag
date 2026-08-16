import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from kg_builder import db


class TemporaryDatabaseTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = db.DB_PATH
        db.DB_PATH = str(Path(self.temp_dir.name) / "upload_records.db")

    def tearDown(self):
        db.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def claim(self, file_hash="hash-a", corpus="owner/corpus", **overrides):
        values = {
            "file_name": "patent.txt",
            "file_path": "data/patent.txt",
            "file_hash": file_hash,
            "file_size": 123,
            "corpus": corpus,
        }
        values.update(overrides)
        return db.claim_upload(**values)


class SchemaMigrationTests(TemporaryDatabaseTestCase):
    def test_fresh_schema_has_version_constraints_and_composite_indexes(self):
        db.init_db()

        conn = db.get_connection()
        try:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 2)
            indexes = {
                row["name"]
                for row in conn.execute("PRAGMA index_list(upload_records)").fetchall()
            }
            self.assertIn("idx_upload_records_hash_corpus_status", indexes)
            columns = {
                row["name"]: row
                for row in conn.execute("PRAGMA table_info(upload_records)").fetchall()
            }
            self.assertIsNone(columns["corpus"]["dflt_value"])

            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    """INSERT INTO upload_records (
                           file_name, file_path, file_hash, file_size,
                           corpus, status, uploaded_at
                       ) VALUES ('x', 'x', 'hash', 1, 'owner/corpus', 'typo', 1)"""
                )
        finally:
            conn.close()

    def test_legacy_schema_is_migrated_and_claim_state_is_backfilled(self):
        conn = sqlite3.connect(db.DB_PATH)
        conn.executescript("""
            CREATE TABLE upload_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_hash TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                corpus TEXT NOT NULL DEFAULT 'patentrag',
                status TEXT NOT NULL DEFAULT 'success',
                uploaded_at REAL NOT NULL,
                error_message TEXT
            );
            CREATE INDEX idx_file_hash ON upload_records(file_hash);
        """)
        conn.executemany(
            """INSERT INTO upload_records (
                   file_name, file_path, file_hash, file_size,
                   corpus, status, uploaded_at, error_message
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                ("a.txt", "a.txt", "same", 10, "legacy", "success", 1, None),
                ("a.txt", "a.txt", "same", 10, "legacy", "failed", 2, "later"),
                ("b.txt", "b.txt", "other", -1, "", "unexpected", 3, None),
            ],
        )
        conn.commit()
        conn.close()

        db.init_db()
        db.init_db()  # Migration and initialization must be idempotent.

        conn = db.get_connection()
        try:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 2)
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM upload_records").fetchone()[0],
                3,
            )
            migrated = conn.execute(
                "SELECT status, file_size, corpus, error_message FROM upload_records WHERE file_hash = 'other'"
            ).fetchone()
            self.assertEqual(migrated["status"], "failed")
            self.assertEqual(migrated["file_size"], 0)
            self.assertEqual(migrated["corpus"], "legacy-unverified")
            self.assertIn("Migrated invalid status", migrated["error_message"])

            claim = conn.execute(
                "SELECT status, attempt_count FROM upload_claims WHERE file_hash = 'same'"
            ).fetchone()
            self.assertEqual(claim["status"], "success")
            self.assertEqual(claim["attempt_count"], 2)
        finally:
            conn.close()

    def test_newer_schema_version_is_rejected(self):
        conn = sqlite3.connect(db.DB_PATH)
        conn.execute("PRAGMA user_version = 99")
        conn.commit()
        conn.close()

        with self.assertRaisesRegex(RuntimeError, "newer than supported"):
            db.init_db()


class UploadClaimTests(TemporaryDatabaseTestCase):
    def setUp(self):
        super().setUp()
        db.init_db()

    def test_concurrent_claims_allow_only_one_worker(self):
        barrier = threading.Barrier(2)

        def try_claim():
            barrier.wait()
            return self.claim()

        with ThreadPoolExecutor(max_workers=2) as executor:
            claims = list(executor.map(lambda _: try_claim(), range(2)))

        self.assertEqual(sum(claim.acquired for claim in claims), 1)
        self.assertEqual(
            sorted(claim.reason for claim in claims),
            ["claimed", "in_progress"],
        )

    def test_same_file_can_be_claimed_for_different_corpora(self):
        first = self.claim(corpus="owner/corpus-a")
        second = self.claim(corpus="owner/corpus-b")

        self.assertTrue(first.acquired)
        self.assertTrue(second.acquired)

    def test_success_blocks_future_claims(self):
        claim = self.claim()
        db.finish_upload(claim.token, "success")

        self.assertTrue(db.is_uploaded("hash-a", "owner/corpus"))
        duplicate = self.claim()
        self.assertFalse(duplicate.acquired)
        self.assertEqual(duplicate.reason, "already_uploaded")

    def test_failed_claim_can_retry_and_stale_token_cannot_finish(self):
        first = self.claim()
        db.finish_upload(first.token, "failed", "network error")
        second = self.claim()

        self.assertTrue(second.acquired)
        self.assertNotEqual(first.token, second.token)
        with self.assertRaises(db.StaleUploadClaimError):
            db.finish_upload(first.token, "success")

        db.finish_upload(second.token, "success")
        self.assertTrue(db.is_uploaded("hash-a", "owner/corpus"))

    def test_expired_claim_can_be_recovered(self):
        first = self.claim()
        conn = db.get_connection()
        try:
            conn.execute(
                "UPDATE upload_claims SET updated_at = 0 WHERE claim_token = ?",
                (first.token,),
            )
            conn.commit()
        finally:
            conn.close()

        recovered = self.claim(stale_after_seconds=1)
        self.assertTrue(recovered.acquired)
        self.assertNotEqual(first.token, recovered.token)
        stats = db.get_stats("owner/corpus")
        self.assertEqual(stats["total_attempts"], 2)
        self.assertEqual(stats["in_progress_count"], 1)
        self.assertEqual(stats["abandoned_count"], 1)
        with self.assertRaises(db.StaleUploadClaimError):
            db.finish_upload(first.token, "success")


class DestinationAwareReportingTests(TemporaryDatabaseTestCase):
    def setUp(self):
        super().setUp()
        db.init_db()

    def complete(self, file_hash, corpus, status):
        claim = self.claim(file_hash=file_hash, corpus=corpus)
        db.finish_upload(claim.token, status, "failed" if status == "failed" else None)

    def test_stats_and_lists_are_destination_aware(self):
        self.complete("shared", "owner/a", "success")
        self.complete("failed-only", "owner/a", "failed")
        self.complete("shared", "owner/b", "success")

        corpus_a = db.get_stats("owner/a")
        self.assertEqual(corpus_a["total_attempts"], 2)
        self.assertEqual(corpus_a["success_count"], 1)
        self.assertEqual(corpus_a["fail_count"], 1)
        self.assertEqual(corpus_a["unique_files"], 1)
        self.assertEqual(corpus_a["in_progress_count"], 0)
        self.assertEqual(corpus_a["abandoned_count"], 0)

        global_stats = db.get_stats()
        self.assertEqual(global_stats["unique_files"], 2)
        self.assertEqual(global_stats["total_attempts"], 3)

        uploaded = db.list_uploaded("owner/a")
        failed = db.list_failed("owner/a")
        self.assertEqual({row["corpus"] for row in uploaded}, {"owner/a"})
        self.assertEqual({row["corpus"] for row in failed}, {"owner/a"})
        self.assertEqual(
            {row["corpus"] for row in db.list_uploaded()},
            {"owner/a", "owner/b"},
        )


if __name__ == "__main__":
    unittest.main()
