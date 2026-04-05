"""Session state management for the RenderDoc CLI harness.

Provides stateful session tracking with undo/redo and JSON persistence.
"""

from __future__ import annotations

import copy
import json
import os
import time
from typing import Any, Dict, List, Optional


class Session:
    """Stateful session for RenderDoc CLI interactions.

    Tracks the current capture file, event position, and command history.
    Supports undo/redo and JSON-based save/load.
    """

    def __init__(self, capture_path: Optional[str] = None):
        self.capture_path: Optional[str] = capture_path
        self.current_event_id: int = 0
        self.created_at: str = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.modified: bool = False

        # History for undo/redo
        self._history: List[Dict[str, Any]] = []
        self._redo_stack: List[Dict[str, Any]] = []

        # Command log
        self.command_log: List[Dict[str, Any]] = []

    def _snapshot(self) -> Dict[str, Any]:
        """Create a snapshot of current state for undo."""
        return {
            "capture_path": self.capture_path,
            "current_event_id": self.current_event_id,
        }

    def _push_undo(self):
        """Push current state to undo stack."""
        self._history.append(self._snapshot())
        self._redo_stack.clear()
        self.modified = True

    def set_capture(self, path: str):
        """Set the active capture file."""
        self._push_undo()
        self.capture_path = path
        self.current_event_id = 0
        self._log_command("set_capture", {"path": path})

    def set_event(self, event_id: int):
        """Navigate to a specific event ID."""
        self._push_undo()
        self.current_event_id = event_id
        self._log_command("set_event", {"event_id": event_id})

    def undo(self) -> bool:
        """Undo the last state change. Returns True if successful."""
        if not self._history:
            return False
        self._redo_stack.append(self._snapshot())
        state = self._history.pop()
        self.capture_path = state["capture_path"]
        self.current_event_id = state["current_event_id"]
        self._log_command("undo", {})
        return True

    def redo(self) -> bool:
        """Redo the last undone change. Returns True if successful."""
        if not self._redo_stack:
            return False
        self._history.append(self._snapshot())
        state = self._redo_stack.pop()
        self.capture_path = state["capture_path"]
        self.current_event_id = state["current_event_id"]
        self._log_command("redo", {})
        return True

    def _log_command(self, command: str, args: Dict[str, Any]):
        """Log a command to the session history."""
        self.command_log.append({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "command": command,
            "args": args,
        })

    def status(self) -> Dict[str, Any]:
        """Return current session status as a dict."""
        return {
            "capture_path": self.capture_path,
            "current_event_id": self.current_event_id,
            "created_at": self.created_at,
            "modified": self.modified,
            "undo_depth": len(self._history),
            "redo_depth": len(self._redo_stack),
            "command_count": len(self.command_log),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the session to a dict."""
        return {
            "capture_path": self.capture_path,
            "current_event_id": self.current_event_id,
            "created_at": self.created_at,
            "command_log": self.command_log,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Session":
        """Deserialize a session from a dict."""
        s = cls(data.get("capture_path"))
        s.current_event_id = data.get("current_event_id", 0)
        s.created_at = data.get("created_at", s.created_at)
        s.command_log = data.get("command_log", [])
        return s

    def save(self, path: str):
        """Save session to a JSON file."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
        self.modified = False

    @classmethod
    def load(cls, path: str) -> "Session":
        """Load session from a JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)
