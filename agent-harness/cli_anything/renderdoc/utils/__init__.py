"""RenderDoc backend utilities — wraps renderdoccmd and the renderdoc Python module."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional


def find_renderdoccmd() -> str:
    """Locate the renderdoccmd executable.

    Searches PATH, then common install locations on Windows/Linux.
    Raises RuntimeError with install instructions if not found.
    """
    path = shutil.which("renderdoccmd")
    if path:
        return path

    # Common Windows install paths
    if sys.platform == "win32":
        candidates = [
            os.path.join(os.environ.get("ProgramFiles", ""), "RenderDoc", "renderdoccmd.exe"),
            os.path.join(os.environ.get("ProgramFiles(x86)", ""), "RenderDoc", "renderdoccmd.exe"),
        ]
        for c in candidates:
            if os.path.isfile(c):
                return c

    # Common Linux paths
    if sys.platform.startswith("linux"):
        candidates = [
            "/usr/bin/renderdoccmd",
            "/usr/local/bin/renderdoccmd",
            os.path.expanduser("~/renderdoc/bin/renderdoccmd"),
        ]
        for c in candidates:
            if os.path.isfile(c):
                return c

    raise RuntimeError(
        "renderdoccmd not found in PATH.\n"
        "Install RenderDoc:\n"
        "  Windows: https://renderdoc.org/builds (MSI or portable ZIP)\n"
        "  Linux:   sudo apt install renderdoc  OR  download from https://renderdoc.org/builds\n"
        "Then ensure renderdoccmd is on your PATH."
    )


def find_renderdoc_module() -> bool:
    """Check whether the renderdoc Python module is importable."""
    try:
        import renderdoc  # noqa: F401
        return True
    except ImportError:
        return False


def run_renderdoccmd(args: List[str], check: bool = True, **kwargs) -> subprocess.CompletedProcess:
    """Run renderdoccmd with the given arguments."""
    cmd = find_renderdoccmd()
    return subprocess.run(
        [cmd] + args,
        capture_output=True,
        text=True,
        check=check,
        **kwargs,
    )


def get_version() -> Dict[str, Any]:
    """Get RenderDoc version information."""
    result = run_renderdoccmd(["version"], check=False)
    return {
        "output": result.stdout.strip(),
        "returncode": result.returncode,
    }


def capture_executable(
    executable: str,
    working_dir: Optional[str] = None,
    capture_file: Optional[str] = None,
    wait_for_exit: bool = True,
    options: Optional[Dict[str, bool]] = None,
) -> Dict[str, Any]:
    """Launch an executable for capture using renderdoccmd.

    Args:
        executable: Path to the executable to capture.
        working_dir: Working directory for the launched process.
        capture_file: Template path for capture files.
        wait_for_exit: Whether to wait for the process to exit.
        options: Dict of capture options (e.g. api_validation, hook_children).

    Returns:
        Dict with result status and process identifier.
    """
    args = ["capture"]
    if working_dir:
        args.extend(["-d", working_dir])
    if capture_file:
        args.extend(["-c", capture_file])
    if wait_for_exit:
        args.append("-w")

    if options:
        opt_map = {
            "disallow_vsync": "--opt-disallow-vsync",
            "disallow_fullscreen": "--opt-disallow-fullscreen",
            "api_validation": "--opt-api-validation",
            "capture_callstacks": "--opt-capture-callstacks",
            "hook_children": "--opt-hook-children",
            "ref_all_resources": "--opt-ref-all-resources",
        }
        for key, flag in opt_map.items():
            if options.get(key):
                args.append(flag)

    args.append(executable)

    result = run_renderdoccmd(args, check=False)
    return {
        "command": ["renderdoccmd"] + args,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
    }


def extract_thumbnail(
    rdc_path: str,
    output_path: str,
    format: str = "png",
    max_size: int = 0,
) -> Dict[str, Any]:
    """Extract the embedded thumbnail from a .rdc capture file.

    Args:
        rdc_path: Path to the .rdc file.
        output_path: Destination image path.
        format: Output format (jpg, png, bmp, tga).
        max_size: Maximum dimension; 0 = unlimited.

    Returns:
        Dict with result status and output path.
    """
    args = ["thumb", "-o", output_path, "-f", format]
    if max_size > 0:
        args.extend(["-s", str(max_size)])
    args.append(rdc_path)

    result = run_renderdoccmd(args, check=False)
    success = result.returncode == 0 and os.path.isfile(output_path)
    return {
        "success": success,
        "output": output_path if success else None,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def convert_capture(
    input_path: str,
    output_path: str,
    input_format: Optional[str] = None,
    output_format: Optional[str] = None,
) -> Dict[str, Any]:
    """Convert a capture between formats using renderdoccmd.

    Args:
        input_path: Source capture file.
        output_path: Destination file.
        input_format: Source format (auto-detected if omitted).
        output_format: Destination format (auto-detected if omitted).

    Returns:
        Dict with result status.
    """
    args = ["convert", "-f", input_path, "-o", output_path]
    if input_format:
        args.extend(["-i", input_format])
    if output_format:
        args.extend(["-c", output_format])

    result = run_renderdoccmd(args, check=False)
    return {
        "success": result.returncode == 0,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def list_capture_formats() -> Dict[str, Any]:
    """List available capture file formats."""
    result = run_renderdoccmd(["convert", "--list-formats"], check=False)
    return {
        "output": result.stdout,
        "returncode": result.returncode,
    }


def embed_section(
    rdc_path: str,
    section_name: str,
    file_path: str,
    compress: Optional[str] = None,
) -> Dict[str, Any]:
    """Embed a data section into a capture file.

    Args:
        rdc_path: Path to the .rdc file.
        section_name: Name for the embedded section.
        file_path: Path to the file to embed.
        compress: Compression method ('lz4' or 'zstd'), or None.

    Returns:
        Dict with result status.
    """
    args = ["embed", "-s", section_name, "-f", file_path]
    if compress == "lz4":
        args.append("--lz4")
    elif compress == "zstd":
        args.append("--zstd")
    args.append(rdc_path)

    result = run_renderdoccmd(args, check=False)
    return {
        "success": result.returncode == 0,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def extract_section(
    rdc_path: str,
    section_name: str,
    output_path: str,
) -> Dict[str, Any]:
    """Extract a data section from a capture file.

    Args:
        rdc_path: Path to the .rdc file.
        section_name: Name of the section to extract.
        output_path: Destination file path.

    Returns:
        Dict with result status and output path.
    """
    args = ["extract", "-s", section_name, "-f", output_path, rdc_path]

    result = run_renderdoccmd(args, check=False)
    success = result.returncode == 0 and os.path.isfile(output_path)
    return {
        "success": success,
        "output": output_path if success else None,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
