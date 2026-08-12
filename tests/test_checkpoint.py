import importlib.util
import sqlite3

import pytest

from app.persistence import SqliteCheckpointResource


def test_checkpoint_resource_creates_parent_directory_without_opening(tmp_path):
    path = tmp_path / "nested" / "checkpoints.sqlite"
    resource = SqliteCheckpointResource(path)
    assert path.parent.exists()
    assert resource.path == path


@pytest.mark.skipif(
    importlib.util.find_spec("langgraph") is None,
    reason="LangGraph dependency unavailable in this execution sandbox",
)
def test_real_sqlite_checkpointer_writes_checkpoint_tables(tmp_path):
    path = tmp_path / "checkpoints.sqlite"
    with SqliteCheckpointResource(path) as resource:
        saver = resource.saver
        saver.setup()
    conn = sqlite3.connect(path)
    try:
        names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    assert {"checkpoints", "writes"}.issubset(names)
