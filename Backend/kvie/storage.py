"""SQLite persistence for KVIE sessions, transcripts, and document edits."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Optional

from .document_state import DocumentState, EditOperation
from Backend.voice.StreamingSTT import TranscriptEvent

# Anchor the default database to the project root so the store resolves the
# same file regardless of the process working directory.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DB_PATH = _PROJECT_ROOT / "Data" / "kvie.sqlite3"


class KVIEStore:
    def __init__(self, path: str | Path | None = None) -> None:
        raw_path = os.fspath(path if path is not None else _DEFAULT_DB_PATH)
        if "\x00" in raw_path:
            raise ValueError("database path contains an invalid null byte")
        if raw_path == ":memory:":
            self.path: Path | str = ":memory:"
            connection_path = ":memory:"
        else:
            candidate = Path(raw_path).expanduser()
            if ".." in candidate.parts:
                raise ValueError("database path must not contain parent-directory components")
            self.path = candidate.resolve(strict=False)
            connection_path = str(self.path)
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(connection_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._initialize()

    def close(self) -> None:
        self._connection.close()

    def _initialize(self) -> None:
        self._connection.executescript(
            """
            PRAGMA journal_mode=WAL;
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                cursor INTEGER NOT NULL,
                version INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS edit_operations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id TEXT NOT NULL,
                action TEXT NOT NULL,
                before_text TEXT NOT NULL,
                after_text TEXT NOT NULL,
                timestamp_ms INTEGER NOT NULL,
                cursor_before INTEGER NOT NULL,
                cursor_after INTEGER NOT NULL,
                metadata_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS transcript_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                text TEXT NOT NULL,
                language TEXT NOT NULL,
                confidence REAL NOT NULL,
                start_ms INTEGER NOT NULL,
                end_ms INTEGER NOT NULL,
                sequence INTEGER NOT NULL,
                error TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS dictation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at INTEGER NOT NULL,
                raw_text TEXT NOT NULL,
                final_text TEXT NOT NULL,
                app_name TEXT,
                confidence REAL,
                language TEXT,
                duration_ms INTEGER,
                latency_ms INTEGER
            );
            """
        )
        self._connection.commit()

    _MAX_EDIT_OPERATIONS = 1000
    _MAX_TRANSCRIPT_EVENTS = 5000

    def _prune_old_rows(self) -> None:
        """Keep edit_operations and transcript_events tables bounded."""
        self._connection.execute(
            "DELETE FROM edit_operations WHERE id NOT IN "
            "(SELECT id FROM edit_operations ORDER BY id DESC LIMIT ?)",
            (self._MAX_EDIT_OPERATIONS,),
        )
        self._connection.execute(
            "DELETE FROM transcript_events WHERE id NOT IN "
            "(SELECT id FROM transcript_events ORDER BY id DESC LIMIT ?)",
            (self._MAX_TRANSCRIPT_EVENTS,),
        )
        self._connection.commit()

    def save_document(self, document_id: str, document: DocumentState) -> None:
        snapshot = document.snapshot()
        self._connection.execute(
            """
            INSERT INTO documents(id, text, cursor, version, updated_at) VALUES(?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET text=excluded.text, cursor=excluded.cursor,
                version=excluded.version, updated_at=excluded.updated_at
            """,
            (document_id, snapshot.text, snapshot.cursor, snapshot.version, self._now()),
        )
        self._connection.commit()

    def load_document(self, document_id: str) -> Optional[DocumentState]:
        row = self._connection.execute("SELECT text, cursor, version FROM documents WHERE id = ?", (document_id,)).fetchone()
        if not row:
            return None
        document = DocumentState(row["text"])
        document.set_cursor(row["cursor"])
        document.restore_version(row["version"])
        return document

    def save_operation(self, document_id: str, operation: EditOperation) -> None:
        self._connection.execute(
            "INSERT INTO edit_operations(document_id, action, before_text, after_text, timestamp_ms, cursor_before, cursor_after, metadata_json) VALUES(?,?,?,?,?,?,?,?)",
            (document_id, operation.action, operation.before, operation.after, operation.timestamp_ms, operation.cursor_before, operation.cursor_after, json.dumps(operation.metadata)),
        )
        self._connection.commit()
        self._prune_old_rows()

    def save_event(self, session_id: str, event: TranscriptEvent) -> None:
        self._connection.execute(
            "INSERT INTO transcript_events(session_id, kind, text, language, confidence, start_ms, end_ms, sequence, error, created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (session_id, event.kind, event.text, event.language, event.confidence, event.start_ms, event.end_ms, event.sequence, event.error, self._now()),
        )
        self._connection.commit()
        self._prune_old_rows()

    _MAX_DICTATION_HISTORY = 1000

    def save_dictation(
        self,
        raw_text: str,
        final_text: str,
        app_name: Optional[str] = None,
        confidence: Optional[float] = None,
        language: Optional[str] = None,
        duration_ms: Optional[int] = None,
        latency_ms: Optional[int] = None,
    ) -> int:
        cursor = self._connection.execute(
            "INSERT INTO dictation_history(created_at, raw_text, final_text, app_name, confidence, language, duration_ms, latency_ms) VALUES(?,?,?,?,?,?,?,?)",
            (self._now(), raw_text, final_text, app_name, confidence, language, duration_ms, latency_ms),
        )
        self._connection.commit()
        self._connection.execute(
            "DELETE FROM dictation_history WHERE id NOT IN "
            "(SELECT id FROM dictation_history ORDER BY id DESC LIMIT ?)",
            (self._MAX_DICTATION_HISTORY,),
        )
        self._connection.commit()
        return int(cursor.lastrowid or 0)

    def list_dictations(self, limit: int = 200) -> list:
        rows = self._connection.execute(
            "SELECT id, created_at, raw_text, final_text, app_name, confidence, language, duration_ms, latency_ms "
            "FROM dictation_history ORDER BY id DESC LIMIT ?",
            (max(1, min(int(limit), 1000)),),
        ).fetchall()
        return [dict(row) for row in rows]

    def count(self, table: str) -> int:
        count_queries = {
            "documents": "SELECT COUNT(*) FROM documents",
            "edit_operations": "SELECT COUNT(*) FROM edit_operations",
            "transcript_events": "SELECT COUNT(*) FROM transcript_events",
        }
        query = count_queries.get(table)
        if query is None:
            raise ValueError("unsupported table")
        return int(self._connection.execute(query).fetchone()[0])

    @staticmethod
    def _now() -> int:
        return int(time.time() * 1000)
