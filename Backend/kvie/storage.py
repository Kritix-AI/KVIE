"""SQLite persistence for KVIE sessions, transcripts, and document edits."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Optional

from .document_state import DocumentState, EditOperation
from Backend.voice.StreamingSTT import TranscriptEvent


class KVIEStore:
    def __init__(self, path: str | Path = "Data/kvie.sqlite3") -> None:
        self.path = Path(path)
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(self.path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._initialize()

    def close(self) -> None:
        self._connection.close()

    def _initialize(self) -> None:
        self._connection.executescript(
            """
            PRAGMA journal_mode=WAL;
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
            """
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
        row = self._connection.execute("SELECT text, cursor FROM documents WHERE id = ?", (document_id,)).fetchone()
        if not row:
            return None
        document = DocumentState(row["text"])
        document.set_cursor(row["cursor"])
        return document

    def save_operation(self, document_id: str, operation: EditOperation) -> None:
        self._connection.execute(
            "INSERT INTO edit_operations(document_id, action, before_text, after_text, timestamp_ms, cursor_before, cursor_after, metadata_json) VALUES(?,?,?,?,?,?,?,?)",
            (document_id, operation.action, operation.before, operation.after, operation.timestamp_ms, operation.cursor_before, operation.cursor_after, json.dumps(operation.metadata)),
        )
        self._connection.commit()

    def save_event(self, session_id: str, event: TranscriptEvent) -> None:
        self._connection.execute(
            "INSERT INTO transcript_events(session_id, kind, text, language, confidence, start_ms, end_ms, sequence, error, created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (session_id, event.kind, event.text, event.language, event.confidence, event.start_ms, event.end_ms, event.sequence, event.error, self._now()),
        )
        self._connection.commit()

    def count(self, table: str) -> int:
        if table not in {"documents", "edit_operations", "transcript_events"}:
            raise ValueError("unsupported table")
        return int(self._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    @staticmethod
    def _now() -> int:
        return int(time.time() * 1000)
