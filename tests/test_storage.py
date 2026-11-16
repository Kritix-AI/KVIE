"""Tests for KVIEStore persistence, thread safety, indexing, and throttled pruning."""

from __future__ import annotations

import tempfile
import threading
from pathlib import Path
import unittest

from Backend.kvie.document_state import DocumentState, EditOperation
from Backend.kvie.storage import KVIEStore
from Backend.voice.StreamingSTT import TranscriptEvent


class TestKVIEStore(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_kvie.sqlite3"
        self.store = KVIEStore(self.db_path)

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def test_secondary_indexes_exist(self) -> None:
        """Verify the 3 composite secondary indexes are created in sqlite_master."""
        with self.store._lock:
            cursor = self.store._connection.execute(
                "SELECT name, tbl_name, sql FROM sqlite_master WHERE type = 'index'"
            )
            indexes = {row["name"]: dict(row) for row in cursor.fetchall()}

        # Verify idx_transcript_events_session
        self.assertIn("idx_transcript_events_session", indexes)
        self.assertEqual(indexes["idx_transcript_events_session"]["tbl_name"], "transcript_events")
        self.assertIn("session_id", indexes["idx_transcript_events_session"]["sql"])
        self.assertIn("id", indexes["idx_transcript_events_session"]["sql"])

        # Verify idx_edit_operations_doc
        self.assertIn("idx_edit_operations_doc", indexes)
        self.assertEqual(indexes["idx_edit_operations_doc"]["tbl_name"], "edit_operations")
        self.assertIn("document_id", indexes["idx_edit_operations_doc"]["sql"])
        self.assertIn("id", indexes["idx_edit_operations_doc"]["sql"])

        # Verify idx_dictation_history_created
        self.assertIn("idx_dictation_history_created", indexes)
        self.assertEqual(indexes["idx_dictation_history_created"]["tbl_name"], "dictation_history")
        self.assertIn("created_at", indexes["idx_dictation_history_created"]["sql"])

    def test_multithreaded_concurrent_writes_and_reads(self) -> None:
        """Verify thread safety with 12 concurrent reader and writer threads."""
        num_threads = 12
        iterations_per_thread = 25
        errors: list[Exception] = []

        def writer_task(worker_id: int) -> None:
            try:
                for i in range(iterations_per_thread):
                    doc_id = f"doc_{worker_id}"
                    doc = DocumentState(f"Initial worker {worker_id} text.")
                    doc.append(f" Iteration {i}")
                    self.store.save_document(doc_id, doc)

                    op = EditOperation(
                        action="append",
                        before="",
                        after=f" Iteration {i}",
                        timestamp_ms=1000 + i,
                        cursor_before=0,
                        cursor_after=len(f" Iteration {i}"),
                        metadata={"worker": worker_id},
                    )
                    self.store.save_operation(doc_id, op)

                    event = TranscriptEvent(
                        kind="final",
                        text=f"Worker {worker_id} event {i}",
                        language="en",
                        confidence=0.95,
                        start_ms=i * 100,
                        end_ms=(i + 1) * 100,
                        sequence=i,
                        error="",
                    )
                    self.store.save_event(f"session_{worker_id}", event)

                    self.store.save_dictation(
                        raw_text=f"raw {worker_id} {i}",
                        final_text=f"final {worker_id} {i}",
                        app_name="test_app",
                        confidence=0.99,
                        language="en",
                        duration_ms=150,
                        latency_ms=25,
                    )
            except Exception as exc:
                errors.append(exc)

        def reader_task(worker_id: int) -> None:
            try:
                for _ in range(iterations_per_thread):
                    self.store.load_document(f"doc_{worker_id % (num_threads // 2)}")
                    self.store.list_dictations(limit=20)
                    self.store.count("documents")
                    self.store.count("dictation_history")
            except Exception as exc:
                errors.append(exc)

        threads: list[threading.Thread] = []
        for worker_id in range(num_threads):
            target = writer_task if worker_id % 2 == 0 else reader_task
            t = threading.Thread(target=target, args=(worker_id,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=10.0)

        self.assertEqual(errors, [], f"Thread errors occurred: {errors}")
        self.assertGreater(self.store.count("documents"), 0)
        self.assertGreater(self.store.count("dictation_history"), 0)

    def test_pruning_is_throttled_and_close_prunes(self) -> None:
        """Verify pruning is throttled to 1-in-100 writes and runs during close()."""
        # Override table bounds to small limits for testing
        self.store._MAX_DICTATION_HISTORY = 10

        # Perform 50 inserts: should NOT trigger prune
        for i in range(50):
            self.store.save_dictation(f"raw_{i}", f"final_{i}")

        self.assertEqual(self.store._write_count, 50)
        self.assertEqual(self.store.count("dictation_history"), 50)

        # Perform another 49 inserts (total 99): should still NOT prune
        for i in range(50, 99):
            self.store.save_dictation(f"raw_{i}", f"final_{i}")

        self.assertEqual(self.store._write_count, 99)
        self.assertEqual(self.store.count("dictation_history"), 99)

        # 100th insert: write_count % 100 == 0 triggers self.prune()
        self.store.save_dictation("raw_99", "final_99")
        self.assertEqual(self.store._write_count, 100)
        self.assertEqual(self.store.count("dictation_history"), 10)

        # Add 5 more inserts (total rows 15, count 105)
        for i in range(100, 105):
            self.store.save_dictation(f"raw_{i}", f"final_{i}")
        self.assertEqual(self.store.count("dictation_history"), 15)

        # close() must safely prune before closing
        self.store.close()

        # Reopen database to verify pruned state
        reopened = KVIEStore(self.db_path)
        reopened._MAX_DICTATION_HISTORY = 10
        self.assertEqual(reopened.count("dictation_history"), 10)
        reopened.close()

    def test_close_is_idempotent_and_guards_operations(self) -> None:
        """Verify close() can be called multiple times and subsequent operations fail cleanly."""
        self.store.close()
        # Second close() call should be a no-op
        self.store.close()

        with self.assertRaises(RuntimeError):
            self.store.save_dictation("raw", "final")

        with self.assertRaises(RuntimeError):
            self.store.load_document("doc-1")

        with self.assertRaises(RuntimeError):
            self.store.count("documents")


if __name__ == "__main__":
    unittest.main()
