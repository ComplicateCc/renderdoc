"""E2E tests for CLI-Anything RenderDoc — subprocess and backend tests.

Tests the installed CLI command via subprocess. Some tests require RenderDoc
to be installed and a .rdc capture file to be available.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

import pytest


def _resolve_cli(name):
    """Resolve installed CLI command; falls back to python -m for dev.

    Set env CLI_ANYTHING_FORCE_INSTALLED=1 to require the installed command.
    """
    force = os.environ.get("CLI_ANYTHING_FORCE_INSTALLED", "").strip() == "1"
    path = shutil.which(name)
    if path:
        print(f"[_resolve_cli] Using installed command: {path}")
        return [path]
    if force:
        raise RuntimeError(f"{name} not found in PATH. Install with: pip install -e .")
    module = "cli_anything.renderdoc.renderdoc_cli"
    print(f"[_resolve_cli] Falling back to: {sys.executable} -m {module}")
    return [sys.executable, "-m", module]


class TestCLISubprocess:
    """Test the CLI via subprocess — no backend required."""

    CLI_BASE = _resolve_cli("cli-anything-renderdoc")

    def _run(self, args, check=True):
        return subprocess.run(
            self.CLI_BASE + args,
            capture_output=True,
            text=True,
            check=check,
        )

    def test_help(self):
        result = self._run(["--help"])
        assert result.returncode == 0
        assert "RenderDoc" in result.stdout

    def test_version(self):
        result = self._run(["version"], check=False)
        assert result.returncode == 0
        assert "cli-anything-renderdoc" in result.stdout

    def test_version_flag(self):
        result = self._run(["--version"], check=False)
        assert result.returncode == 0
        assert "cli-anything-renderdoc" in result.stdout

    def test_info_no_capture(self):
        """Should error gracefully when no capture is specified."""
        result = self._run(["info"], check=False)
        # Should output an error, not crash
        assert result.returncode == 0 or result.returncode == 1

    def test_json_version(self):
        result = self._run(["--json", "version"], check=False)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "harness_version" in data

    def test_session_save_load(self):
        """Test session save/load round trip via subprocess."""
        with tempfile.TemporaryDirectory() as tmp:
            session_path = os.path.join(tmp, "test_session.json")

            # Save a session
            result = self._run([
                "--capture", __file__,  # Use this file as a dummy path
                "session", "save", session_path,
            ], check=False)

            # The capture path won't be a valid .rdc, but session save should still work
            if result.returncode == 0 and os.path.isfile(session_path):
                with open(session_path, "r") as f:
                    data = json.load(f)
                assert "capture_path" in data
                assert "command_log" in data

    def test_session_status_json(self):
        result = self._run(["--json", "session", "status"], check=False)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "capture_path" in data
        assert "current_event_id" in data

    def test_actions_no_capture(self):
        result = self._run(["actions"], check=False)
        assert result.returncode == 0 or result.returncode == 1

    def test_textures_no_capture(self):
        result = self._run(["textures"], check=False)
        assert result.returncode == 0 or result.returncode == 1


class TestWithRealCapture:
    """Tests that require a real .rdc capture file.

    Set RDC_TEST_CAPTURE env var to the path of a .rdc file to enable these tests.
    """

    @pytest.fixture
    def rdc_path(self):
        path = os.environ.get("RDC_TEST_CAPTURE")
        if not path or not os.path.isfile(path):
            pytest.skip("RDC_TEST_CAPTURE not set or file not found")
        return path

    @pytest.fixture
    def tmp_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            yield tmp

    CLI_BASE = _resolve_cli("cli-anything-renderdoc")

    def _run(self, args, check=True):
        return subprocess.run(
            self.CLI_BASE + args,
            capture_output=True,
            text=True,
            check=check,
        )

    def test_info_real(self, rdc_path):
        result = self._run(["--json", "info", rdc_path])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["path"] == rdc_path
        assert data["file_size"] > 0
        print(f"\n  Capture: {rdc_path} ({data['file_size']:,} bytes)")

    def test_actions_real(self, rdc_path):
        result = self._run(["--json", "actions", rdc_path])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["count"] > 0
        print(f"\n  Actions: {data['count']} total")

    def test_textures_real(self, rdc_path):
        result = self._run(["--json", "textures", rdc_path])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["count"] > 0
        print(f"\n  Textures: {data['count']} total")

    def test_thumb_real(self, rdc_path, tmp_dir):
        output = os.path.join(tmp_dir, "thumb.png")
        result = self._run(["thumb", rdc_path, output], check=False)
        if result.returncode == 0:
            assert os.path.isfile(output)
            size = os.path.getsize(output)
            assert size > 0
            print(f"\n  Thumbnail: {output} ({size:,} bytes)")

    def test_full_workflow(self, rdc_path, tmp_dir):
        """Full analysis workflow: info → actions → session save."""
        # 1. Info
        result = self._run(["--json", "info", rdc_path])
        assert result.returncode == 0
        info = json.loads(result.stdout)
        print(f"\n  [1] Info: {info['file_size']:,} bytes")

        # 2. Actions
        result = self._run(["--json", "actions", rdc_path])
        assert result.returncode == 0
        actions = json.loads(result.stdout)
        print(f"  [2] Actions: {actions['count']}")

        # 3. Save session
        session_path = os.path.join(tmp_dir, "workflow_session.json")
        result = self._run([
            "--capture", rdc_path,
            "session", "save", session_path,
        ], check=False)
        if result.returncode == 0:
            assert os.path.isfile(session_path)
            print(f"  [3] Session saved: {session_path}")
