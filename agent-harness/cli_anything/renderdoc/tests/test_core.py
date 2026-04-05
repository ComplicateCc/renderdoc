"""Unit tests for CLI-Anything RenderDoc — core modules (synthetic data, no backend)."""

import json
import os
import tempfile

import pytest

from cli_anything.renderdoc.core import Session


# ─── Session tests ───────────────────────────────────────────────────────────

class TestSession:
    def test_session_create(self):
        s = Session()
        assert s.capture_path is None
        assert s.current_event_id == 0
        assert s.modified is False
        assert len(s.command_log) == 0

    def test_session_create_with_path(self):
        s = Session("/path/to/capture.rdc")
        assert s.capture_path == "/path/to/capture.rdc"

    def test_session_set_capture(self):
        s = Session()
        s.set_capture("/tmp/test.rdc")
        assert s.capture_path == "/tmp/test.rdc"
        assert s.current_event_id == 0
        assert s.modified is True

    def test_session_set_event(self):
        s = Session("/tmp/test.rdc")
        s.set_event(42)
        assert s.current_event_id == 42
        assert s.modified is True

    def test_session_undo(self):
        s = Session()
        s.set_capture("/tmp/a.rdc")
        s.set_event(10)
        assert s.current_event_id == 10

        assert s.undo() is True
        assert s.current_event_id == 0
        assert s.capture_path == "/tmp/a.rdc"

        assert s.undo() is True
        assert s.capture_path is None

    def test_session_redo(self):
        s = Session()
        s.set_capture("/tmp/a.rdc")
        s.set_event(10)

        s.undo()
        assert s.current_event_id == 0

        assert s.redo() is True
        assert s.current_event_id == 10

    def test_session_undo_empty(self):
        s = Session()
        assert s.undo() is False

    def test_session_redo_empty(self):
        s = Session()
        assert s.redo() is False

    def test_session_undo_clears_redo(self):
        s = Session()
        s.set_event(10)
        s.set_event(20)
        s.undo()
        # Redo stack has event=20
        s.set_event(30)
        # New action clears redo stack
        assert s.redo() is False

    def test_session_save_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "session.json")

            s = Session()
            s.set_capture("/tmp/test.rdc")
            s.set_event(42)
            s.save(path)

            assert os.path.isfile(path)

            loaded = Session.load(path)
            assert loaded.capture_path == "/tmp/test.rdc"
            assert loaded.current_event_id == 42

    def test_session_save_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "session.json")

            s = Session()
            s.set_capture("/captures/frame0.rdc")
            s.set_event(100)
            s.set_event(200)
            s.save(path)

            with open(path, "r") as f:
                data = json.load(f)

            assert data["capture_path"] == "/captures/frame0.rdc"
            assert data["current_event_id"] == 200
            assert len(data["command_log"]) == 3  # set_capture + 2x set_event

    def test_session_status(self):
        s = Session()
        s.set_capture("/tmp/test.rdc")
        st = s.status()

        assert "capture_path" in st
        assert "current_event_id" in st
        assert "modified" in st
        assert "undo_depth" in st
        assert "redo_depth" in st
        assert "command_count" in st
        assert st["capture_path"] == "/tmp/test.rdc"
        assert st["undo_depth"] == 1
        assert st["modified"] is True

    def test_session_command_log(self):
        s = Session()
        s.set_capture("/tmp/a.rdc")
        s.set_event(10)
        s.set_event(20)

        assert len(s.command_log) == 3
        assert s.command_log[0]["command"] == "set_capture"
        assert s.command_log[1]["command"] == "set_event"
        assert s.command_log[1]["args"]["event_id"] == 10
        assert s.command_log[2]["command"] == "set_event"
        assert s.command_log[2]["args"]["event_id"] == 20

    def test_session_to_dict(self):
        s = Session("/tmp/test.rdc")
        s.set_event(55)
        d = s.to_dict()
        assert d["capture_path"] == "/tmp/test.rdc"
        assert d["current_event_id"] == 55
        assert "created_at" in d
        assert "command_log" in d

    def test_session_from_dict(self):
        d = {
            "capture_path": "/my/capture.rdc",
            "current_event_id": 99,
            "created_at": "2025-01-01T00:00:00",
            "command_log": [{"timestamp": "2025-01-01T00:00:01", "command": "test", "args": {}}],
        }
        s = Session.from_dict(d)
        assert s.capture_path == "/my/capture.rdc"
        assert s.current_event_id == 99
        assert s.created_at == "2025-01-01T00:00:00"
        assert len(s.command_log) == 1


# ─── Backend utils tests ────────────────────────────────────────────────────

class TestBackendUtils:
    def test_find_renderdoc_module(self):
        from cli_anything.renderdoc.utils import find_renderdoc_module
        # Just check it returns a boolean
        result = find_renderdoc_module()
        assert isinstance(result, bool)

    def test_find_renderdoccmd_error_message(self):
        """If renderdoccmd is not on PATH, error should include install instructions."""
        import unittest.mock as mock

        with mock.patch("shutil.which", return_value=None):
            with mock.patch("os.path.isfile", return_value=False):
                from cli_anything.renderdoc.utils import find_renderdoccmd
                with pytest.raises(RuntimeError, match="renderdoccmd not found"):
                    find_renderdoccmd()
