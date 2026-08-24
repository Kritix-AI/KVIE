"""Living document model used by KVIE editing decisions.

The model deliberately contains no UI or LLM code. Every mutation becomes an
operation with a before/after snapshot, which makes undo/redo deterministic
and gives the intelligence layer an auditable edit trail.
"""

from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class EditOperation:
    action: str
    before: str
    after: str
    timestamp_ms: int
    cursor_before: int
    cursor_after: int
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DocumentSnapshot:
    text: str
    cursor: int
    version: int
    can_undo: bool
    can_redo: bool


class DocumentState:
    """Mutable document with sentence-aware operations and bounded history."""

    def __init__(self, text: str = "", history_limit: int = 100) -> None:
        if history_limit < 1:
            raise ValueError("history_limit must be at least 1")
        self._text = text
        self._cursor = len(text)
        self._version = 0
        self._history_limit = history_limit
        self._undo_stack: List[EditOperation] = []
        self._redo_stack: List[EditOperation] = []

    @property
    def text(self) -> str:
        return self._text

    @property
    def cursor(self) -> int:
        return self._cursor

    @property
    def version(self) -> int:
        return self._version

    def set_cursor(self, position: int) -> int:
        self._cursor = max(0, min(len(self._text), position))
        return self._cursor

    def snapshot(self) -> DocumentSnapshot:
        return DocumentSnapshot(self._text, self._cursor, self._version, bool(self._undo_stack), bool(self._redo_stack))

    def append(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> DocumentSnapshot:
        separator = "" if not self._text or self._text.endswith((" ", "\n")) else " "
        return self._commit(self._text + separator + text.strip(), "append", metadata or {})

    def insert(self, text: str, position: Optional[int] = None, metadata: Optional[Dict[str, Any]] = None) -> DocumentSnapshot:
        position = self._cursor if position is None else max(0, min(len(self._text), position))
        new_text = self._text[:position] + text + self._text[position:]
        return self._commit(new_text, "insert", metadata or {}, cursor=position + len(text))

    def replace(self, start: int, end: int, text: str, metadata: Optional[Dict[str, Any]] = None) -> DocumentSnapshot:
        if start < 0 or end < start or end > len(self._text):
            raise ValueError("invalid replacement range")
        new_text = self._text[:start] + text + self._text[end:]
        return self._commit(new_text, "replace", metadata or {}, cursor=start + len(text))

    def delete(self, start: int, end: int, metadata: Optional[Dict[str, Any]] = None) -> DocumentSnapshot:
        return self.replace(start, end, "", metadata={**(metadata or {}), "deleted_range": [start, end]})

    def clear(self, metadata: Optional[Dict[str, Any]] = None) -> DocumentSnapshot:
        return self._commit("", "clear", metadata or {}, cursor=0)

    def replace_sentence(self, index: int, replacement: str, metadata: Optional[Dict[str, Any]] = None) -> DocumentSnapshot:
        spans = self.sentence_spans()
        if index < 0 or index >= len(spans):
            raise IndexError("sentence index out of range")
        start, end = spans[index]
        return self.replace(start, end, replacement.strip(), metadata={**(metadata or {}), "sentence_index": index})

    def sentence_spans(self) -> List[Tuple[int, int]]:
        return [(match.start(), match.end()) for match in re.finditer(r"\S.*?(?:[.!?](?=\s|$)|$)", self._text, re.DOTALL)]

    def sentences(self) -> List[str]:
        return [self._text[start:end].strip() for start, end in self.sentence_spans()]

    def undo(self) -> DocumentSnapshot:
        if not self._undo_stack:
            return self.snapshot()
        operation = self._undo_stack.pop()
        inverse = EditOperation("undo", self._text, operation.before, self._now(), self._cursor, operation.cursor_before, {"undone_action": operation.action})
        self._redo_stack.append(operation)
        self._text = operation.before
        self._cursor = operation.cursor_before
        self._version += 1
        return self.snapshot()

    def redo(self) -> DocumentSnapshot:
        if not self._redo_stack:
            return self.snapshot()
        operation = self._redo_stack.pop()
        self._undo_stack.append(operation)
        self._text = operation.after
        self._cursor = operation.cursor_after
        self._version += 1
        return self.snapshot()

    def history(self) -> List[EditOperation]:
        return list(self._undo_stack)

    def to_dict(self) -> Dict[str, Any]:
        return {"text": self._text, "cursor": self._cursor, "version": self._version, "history": [asdict(item) for item in self._undo_stack]}

    def _commit(self, text: str, action: str, metadata: Dict[str, Any], cursor: Optional[int] = None) -> DocumentSnapshot:
        if text == self._text:
            return self.snapshot()
        before = self._text
        old_cursor = self._cursor
        self._text = text
        self._cursor = len(text) if cursor is None else max(0, min(len(text), cursor))
        operation = EditOperation(action, before, text, self._now(), old_cursor, self._cursor, metadata)
        self._undo_stack.append(operation)
        self._undo_stack = self._undo_stack[-self._history_limit:]
        self._redo_stack.clear()
        self._version += 1
        return self.snapshot()

    def _now(self) -> int:
        return int(time.time() * 1000)
