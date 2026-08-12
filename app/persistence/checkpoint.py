"""Durable LangGraph SQLite checkpoint resource."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any


class SqliteCheckpointResource:
    """Own a SQLite connection and the LangGraph saver that depends on it.

    The connection must remain open for as long as the compiled graph is in use.
    Imports are local so non-LangGraph unit tests can run in restricted sandboxes.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection: sqlite3.Connection | None = None
        self._saver: Any | None = None

    def open(self) -> Any:
        if self._saver is not None:
            return self._saver

        # LangGraph checkpoint-sqlite recommends strict msgpack deserialization
        # to prevent unsafe object reconstruction if a checkpoint DB is tampered
        # with. Enforce it in application code instead of relying on shell state.
        os.environ["LANGGRAPH_STRICT_MSGPACK"] = "true"
        from langgraph.checkpoint.sqlite import SqliteSaver

        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._saver = SqliteSaver(self._connection)
        return self._saver

    @property
    def saver(self) -> Any:
        if self._saver is None:
            raise RuntimeError("checkpoint resource is not open")
        return self._saver

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
        self._connection = None
        self._saver = None

    def __enter__(self) -> "SqliteCheckpointResource":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
