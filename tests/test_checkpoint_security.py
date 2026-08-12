from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.persistence.checkpoint import SqliteCheckpointResource


def test_checkpoint_open_enforces_strict_msgpack_before_optional_import(tmp_path, monkeypatch):
    monkeypatch.delenv("LANGGRAPH_STRICT_MSGPACK", raising=False)
    resource = SqliteCheckpointResource(tmp_path / "checkpoints.sqlite")

    # In restricted test sandboxes LangGraph may be absent. The security env var
    # must still be set before the optional import fails.
    try:
        resource.open()
    except ModuleNotFoundError:
        pass
    finally:
        resource.close()

    assert os.environ["LANGGRAPH_STRICT_MSGPACK"] == "true"
