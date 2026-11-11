"""Find top-level JSON properties as soon as their value is complete in a streamed object
(spec 006 AC3), so each summary field can be saved and shown the moment the model finishes it.
"""

import json
from typing import Any


class FieldStream:
    """Feed text chunks of one JSON object; `feed` returns properties completed by that chunk."""

    def __init__(self) -> None:
        self._buffer = ""
        self._pos = 0  # next character to scan
        self._depth = 0
        self._in_string = False
        self._escape = False
        self._key: str | None = None
        self._key_start: int | None = None
        self._value_start: int | None = None
        self._expect_key = False
        self.done: dict[str, Any] = {}

    def feed(self, chunk: str) -> dict[str, Any]:
        self._buffer += chunk
        completed: dict[str, Any] = {}
        while self._pos < len(self._buffer):
            ch = self._buffer[self._pos]
            if self._in_string:
                if self._escape:
                    self._escape = False
                elif ch == "\\":
                    self._escape = True
                elif ch == '"':
                    self._in_string = False
                    if self._depth == 1 and self._key_start is not None and self._key is None:
                        self._key = json.loads(self._buffer[self._key_start : self._pos + 1])
                        self._key_start = None
                    elif self._depth == 1 and self._value_start is not None:
                        self._finish(self._pos + 1, completed)  # a string value at top level
            elif ch == '"':
                self._in_string = True
                if self._depth == 1 and self._key is None and self._value_start is None:
                    self._key_start = self._pos
            elif ch == ":" and self._depth == 1 and self._key is not None:
                self._value_start = self._pos + 1
            elif ch in "{[":
                self._depth += 1
            elif ch in "}]":
                self._depth -= 1
                if self._depth == 1 and self._value_start is not None:
                    self._finish(self._pos + 1, completed)
                elif self._depth == 0 and self._value_start is not None:
                    self._finish(self._pos, completed)  # last scalar before the closing brace
            elif ch == "," and self._depth == 1 and self._value_start is not None:
                self._finish(self._pos, completed)
            self._pos += 1
        return completed

    def _finish(self, end: int, completed: dict[str, Any]) -> None:
        assert self._key is not None
        assert self._value_start is not None
        raw = self._buffer[self._value_start : end].strip()
        if raw:
            try:
                value = json.loads(raw)
            except json.JSONDecodeError:
                value = None
            if value is not None or raw == "null":
                completed[self._key] = value
                self.done[self._key] = value
        self._key = None
        self._value_start = None
