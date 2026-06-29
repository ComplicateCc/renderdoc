"""CLI-Anything harness for RenderDoc — main Click CLI with REPL support.

Usage:
    cli-anything-renderdoc [OPTIONS] COMMAND [ARGS]...
    cli-anything-renderdoc                          # enters REPL mode

Supports --json for machine-readable output on every command.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Optional

import click

from cli_anything.renderdoc import __version__
from cli_anything.renderdoc.core import Session


# ── Globals ──────────────────────────────────────────────────────────────────
_session = Session()
_json_mode = False


def _output(data, human_lines=None):
    """Print output in JSON or human-readable format."""
    if _json_mode:
        click.echo(json.dumps(data, indent=2, default=str))
    elif human_lines:
        for line in human_lines:
            click.echo(line)
    else:
        click.echo(json.dumps(data, indent=2, default=str))


def _error(msg: str, data=None):
    """Print an error message."""
    if _json_mode:
        click.echo(json.dumps({"error": msg, **(data or {})}, indent=2, default=str))
    else:
        click.echo(f"Error: {msg}", err=True)


# ── Main group ───────────────────────────────────────────────────────────────
@click.group(invoke_without_command=True)
@click.option("--json", "use_json", is_flag=True, help="Machine-readable JSON output.")
@click.option("--capture", "-c", type=click.Path(), help="Set the active capture file (.rdc).")
@click.option("--session", "-s", "session_file", type=click.Path(), help="Load a session file.")
@click.version_option(__version__, prog_name="cli-anything-renderdoc")
@click.pass_context
def cli(ctx, use_json, capture, session_file):
    """CLI-Anything harness for RenderDoc — frame-capture graphics debugger.

    If no subcommand is given, enters interactive REPL mode.
    """
    global _json_mode, _session
    _json_mode = use_json

    ctx.ensure_object(dict)
    ctx.obj["json"] = use_json

    if session_file and os.path.isfile(session_file):
        _session = Session.load(session_file)

    if capture:
        _session.set_capture(capture)

    if ctx.invoked_subcommand is None:
        ctx.invoke(repl_cmd)


# ── info ─────────────────────────────────────────────────────────────────────
@cli.command("info")
@click.argument("rdc_path", required=False, type=click.Path(exists=True))
def info_cmd(rdc_path):
    """Show metadata about a capture file."""
    path = rdc_path or _session.capture_path
    if not path:
        _error("No capture file specified. Use --capture or provide a path.")
        return

    try:
        from cli_anything.renderdoc.utils.renderdoc_backend import get_capture_info
        data = get_capture_info(path)
        human = [
            f"Capture: {data['path']}",
            f"  Size:    {data['file_size']:,} bytes",
            f"  Driver:  {data.get('driver_name', 'unknown')}",
            f"  Replay:  {'yes' if data['local_replay_support'] else 'no'}",
        ]
        if "sections" in data:
            human.append(f"  Sections ({data['section_count']}):")
            for s in data["sections"]:
                human.append(f"    [{s['index']}] {s['name']} ({s['type']})")
        _output(data, human)
    except Exception as e:
        # Fallback to file-only info
        if os.path.isfile(path):
            data = {
                "path": path,
                "file_size": os.path.getsize(path),
                "note": f"Full replay info unavailable: {e}",
            }
            human = [
                f"Capture: {path}",
                f"  Size: {data['file_size']:,} bytes",
                f"  Note: Full replay info unavailable ({e})",
            ]
            _output(data, human)
        else:
            _error(str(e))


# ── actions ──────────────────────────────────────────────────────────────────
@cli.command("actions")
@click.argument("rdc_path", required=False, type=click.Path(exists=True))
@click.option("--flat", is_flag=True, help="Flatten the action tree.")
@click.option("--limit", "-n", type=int, default=50, help="Max actions to display.")
def actions_cmd(rdc_path, flat, limit):
    """List draw calls / actions in a capture."""
    path = rdc_path or _session.capture_path
    if not path:
        _error("No capture file specified.")
        return

    try:
        from cli_anything.renderdoc.utils.renderdoc_backend import list_actions
        data = list_actions(path, flat=flat)
        displayed = data["actions"][:limit]
        human = [f"Actions in {path} ({data['count']} total, showing {len(displayed)}):"]
        for a in displayed:
            flags_str = ""
            human.append(f"  [{a['eventId']:>6}] {a['name']}"
                        + (f"  ({a['childCount']} children)" if a["childCount"] > 0 else ""))
        if data["count"] > limit:
            human.append(f"  ... and {data['count'] - limit} more (use --limit to see more)")
        _output(data, human)
    except Exception as e:
        _error(str(e))


# ── textures ─────────────────────────────────────────────────────────────────
@cli.command("textures")
@click.argument("rdc_path", required=False, type=click.Path(exists=True))
@click.option("--limit", "-n", type=int, default=50, help="Max textures to display.")
def textures_cmd(rdc_path, limit):
    """List all textures in a capture."""
    path = rdc_path or _session.capture_path
    if not path:
        _error("No capture file specified.")
        return

    try:
        from cli_anything.renderdoc.utils.renderdoc_backend import list_textures
        data = list_textures(path)
        displayed = data["textures"][:limit]
        human = [f"Textures in {path} ({data['count']} total, showing {len(displayed)}):"]
        for t in displayed:
            human.append(
                f"  ID {t['resourceId']:>8}  {t['width']}x{t['height']}"
                f"  mips={t['mips']}  fmt={t['format']}"
            )
        if data["count"] > limit:
            human.append(f"  ... and {data['count'] - limit} more")
        _output(data, human)
    except Exception as e:
        _error(str(e))


# ── save-texture ─────────────────────────────────────────────────────────────
@cli.command("save-texture")
@click.argument("resource_id", type=int)
@click.argument("output_path", type=click.Path())
@click.option("--rdc", type=click.Path(exists=True), help="Capture file path.")
@click.option("--format", "-f", "file_type", default="png",
              type=click.Choice(["png", "jpg", "bmp", "tga", "hdr", "dds"]),
              help="Output image format.")
@click.option("--event", "-e", type=int, help="Navigate to event before saving.")
@click.option("--mip", type=int, default=0, help="Mip level (0-based, -1 for all in DDS).")
@click.option("--slice", "slice_idx", type=int, default=0, help="Array slice (0-based).")
def save_texture_cmd(resource_id, output_path, rdc, file_type, event, mip, slice_idx):
    """Save a texture from the capture to an image file."""
    path = rdc or _session.capture_path
    if not path:
        _error("No capture file specified.")
        return

    try:
        from cli_anything.renderdoc.utils.renderdoc_backend import save_texture
        data = save_texture(path, resource_id, output_path,
                           file_type=file_type, event_id=event,
                           mip=mip, slice_index=slice_idx)
        human = []
        if data["success"]:
            human.append(f"Saved texture {resource_id} to {output_path}")
            human.append(f"  Format: {file_type}  Size: {data['file_size']:,} bytes")
        else:
            human.append(f"Failed to save texture {resource_id}")
        _output(data, human)
    except Exception as e:
        _error(str(e))


# ── pipeline ─────────────────────────────────────────────────────────────────
@cli.command("pipeline")
@click.argument("event_id", type=int)
@click.option("--rdc", type=click.Path(exists=True), help="Capture file path.")
def pipeline_cmd(event_id, rdc):
    """Inspect the GPU pipeline state at a specific event."""
    path = rdc or _session.capture_path
    if not path:
        _error("No capture file specified.")
        return

    try:
        from cli_anything.renderdoc.utils.renderdoc_backend import get_pipeline_state
        data = get_pipeline_state(path, event_id)
        human = [
            f"Pipeline state at event {event_id}:",
            f"  Graphics pipeline: {data.get('graphics_pipeline', 'N/A')}",
        ]
        for stage in ["vertex_shader", "fragment_shader"]:
            s = data.get(stage)
            if s:
                human.append(f"  {stage}: entry={s['entry_point']}  id={s['resourceId']}")
            else:
                human.append(f"  {stage}: not bound")
        if "outputs" in data:
            human.append(f"  Render targets: {', '.join(data['outputs'])}")
        _output(data, human)
    except Exception as e:
        _error(str(e))


# ── shader ───────────────────────────────────────────────────────────────────
@cli.command("shader")
@click.argument("event_id", type=int)
@click.option("--rdc", type=click.Path(exists=True), help="Capture file path.")
@click.option("--stage", "-s", default="pixel",
              type=click.Choice(["vertex", "pixel", "fragment", "compute",
                                 "geometry", "hull", "domain"]),
              help="Shader stage to disassemble.")
@click.option("--target", "-t", type=int, default=0,
              help="Disassembly target format index.")
def shader_cmd(event_id, rdc, stage, target):
    """Disassemble a shader at a specific event."""
    path = rdc or _session.capture_path
    if not path:
        _error("No capture file specified.")
        return

    try:
        from cli_anything.renderdoc.utils.renderdoc_backend import disassemble_shader
        data = disassemble_shader(path, event_id, stage=stage, target_index=target)
        if "error" in data:
            _error(data["error"])
        else:
            human = [
                f"Shader disassembly at event {event_id} ({stage} stage):",
                f"  Target: {data['target']}",
                f"  Available: {', '.join(data['available_targets'])}",
                "",
                data["disassembly"],
            ]
            _output(data, human)
    except Exception as e:
        _error(str(e))


# ── counters ─────────────────────────────────────────────────────────────────
@cli.command("counters")
@click.argument("rdc_path", required=False, type=click.Path(exists=True))
def counters_cmd(rdc_path):
    """List available GPU performance counters."""
    path = rdc_path or _session.capture_path
    if not path:
        _error("No capture file specified.")
        return

    try:
        from cli_anything.renderdoc.utils.renderdoc_backend import list_counters
        data = list_counters(path)
        human = [f"GPU Counters ({data['count']}):"]
        for c in data["counters"]:
            human.append(f"  [{c['id']:>6}] {c['name']}")
            human.append(f"          {c['description']}")
        _output(data, human)
    except Exception as e:
        _error(str(e))


# ── thumb ────────────────────────────────────────────────────────────────────
@cli.command("thumb")
@click.argument("rdc_path", type=click.Path(exists=True))
@click.argument("output_path", type=click.Path())
@click.option("--format", "-f", "fmt", default="png",
              type=click.Choice(["png", "jpg", "bmp", "tga"]))
@click.option("--max-size", "-s", type=int, default=0,
              help="Maximum thumbnail dimension (0 = unlimited).")
def thumb_cmd(rdc_path, output_path, fmt, max_size):
    """Extract the embedded thumbnail from a capture file."""
    try:
        from cli_anything.renderdoc.utils import extract_thumbnail
        data = extract_thumbnail(rdc_path, output_path, format=fmt, max_size=max_size)
        human = []
        if data["success"]:
            human.append(f"Thumbnail saved to {output_path}")
        else:
            human.append("Failed to extract thumbnail")
            if data.get("stderr"):
                human.append(data["stderr"])
        _output(data, human)
    except Exception as e:
        _error(str(e))


# ── convert ──────────────────────────────────────────────────────────────────
@cli.command("convert")
@click.argument("input_path", type=click.Path(exists=True))
@click.argument("output_path", type=click.Path())
@click.option("--input-format", "-i", help="Input format (auto-detected if omitted).")
@click.option("--output-format", "-o", "out_fmt", help="Output format (auto-detected if omitted).")
@click.option("--list-formats", is_flag=True, help="List available formats and exit.")
def convert_cmd(input_path, output_path, input_format, out_fmt, list_formats):
    """Convert between capture file formats."""
    try:
        from cli_anything.renderdoc.utils import convert_capture, list_capture_formats

        if list_formats:
            data = list_capture_formats()
            _output(data, [data["output"]])
            return

        data = convert_capture(input_path, output_path,
                              input_format=input_format, output_format=out_fmt)
        human = []
        if data["success"]:
            human.append(f"Converted {input_path} → {output_path}")
        else:
            human.append("Conversion failed")
            if data.get("stderr"):
                human.append(data["stderr"])
        _output(data, human)
    except Exception as e:
        _error(str(e))


# ── capture ──────────────────────────────────────────────────────────────────
@cli.command("capture")
@click.argument("executable", type=click.Path())
@click.option("--working-dir", "-d", type=click.Path(), help="Working directory.")
@click.option("--capture-file", "-o", type=click.Path(), help="Capture file template path.")
@click.option("--wait/--no-wait", default=True, help="Wait for process exit.")
@click.option("--api-validation", is_flag=True, help="Enable API validation.")
@click.option("--hook-children", is_flag=True, help="Hook child processes.")
def capture_cmd(executable, working_dir, capture_file, wait, api_validation, hook_children):
    """Launch an executable for frame capture."""
    try:
        from cli_anything.renderdoc.utils import capture_executable

        options = {}
        if api_validation:
            options["api_validation"] = True
        if hook_children:
            options["hook_children"] = True

        data = capture_executable(
            executable,
            working_dir=working_dir,
            capture_file=capture_file,
            wait_for_exit=wait,
            options=options or None,
        )
        human = [
            f"Launched: {executable}",
            f"  Return code: {data['returncode']}",
        ]
        if data.get("stdout"):
            human.append(data["stdout"])
        if data.get("stderr"):
            human.append(data["stderr"])
        _output(data, human)
    except Exception as e:
        _error(str(e))


# ── version ──────────────────────────────────────────────────────────────────
@cli.command("version")
def version_cmd():
    """Show RenderDoc and harness version info."""
    data = {"harness_version": __version__}
    human = [f"cli-anything-renderdoc v{__version__}"]

    try:
        from cli_anything.renderdoc.utils import get_version
        rd_ver = get_version()
        data["renderdoc"] = rd_ver
        human.append(f"RenderDoc: {rd_ver['output']}")
    except Exception as e:
        data["renderdoc_error"] = str(e)
        human.append(f"RenderDoc: not found ({e})")

    _output(data, human)


# ── session ──────────────────────────────────────────────────────────────────
@cli.group("session")
def session_group():
    """Session state management (save, load, status, undo, redo)."""
    pass


@session_group.command("status")
def session_status():
    """Show current session status."""
    data = _session.status()
    human = [
        "Session status:",
        f"  Capture: {data['capture_path'] or '(none)'}",
        f"  Event:   {data['current_event_id']}",
        f"  Undo:    {data['undo_depth']} steps",
        f"  Redo:    {data['redo_depth']} steps",
        f"  Commands: {data['command_count']}",
        f"  Modified: {'yes' if data['modified'] else 'no'}",
    ]
    _output(data, human)


@session_group.command("save")
@click.argument("path", type=click.Path())
def session_save(path):
    """Save the current session to a file."""
    _session.save(path)
    _output({"saved": path}, [f"Session saved to {path}"])


@session_group.command("load")
@click.argument("path", type=click.Path(exists=True))
def session_load(path):
    """Load a session from a file."""
    global _session
    _session = Session.load(path)
    data = _session.status()
    _output(data, [f"Session loaded from {path}", f"  Capture: {data['capture_path']}"])


@session_group.command("undo")
def session_undo():
    """Undo the last state change."""
    if _session.undo():
        data = _session.status()
        _output(data, [f"Undone. Now at event {data['current_event_id']}"])
    else:
        _error("Nothing to undo.")


@session_group.command("redo")
def session_redo():
    """Redo the last undone change."""
    if _session.redo():
        data = _session.status()
        _output(data, [f"Redone. Now at event {data['current_event_id']}"])
    else:
        _error("Nothing to redo.")


# ── REPL ─────────────────────────────────────────────────────────────────────
@cli.command("repl", hidden=True)
def repl_cmd():
    """Enter interactive REPL mode."""
    global _session

    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.history import InMemoryHistory
        has_pt = True
    except ImportError:
        has_pt = False

    click.echo(f"┌─────────────────────────────────────────────┐")
    click.echo(f"│  CLI-Anything: RenderDoc  v{__version__:<17}│")
    click.echo(f"│  Graphics debugger CLI harness              │")
    click.echo(f"├─────────────────────────────────────────────┤")
    click.echo(f"│  Type 'help' for commands, 'quit' to exit   │")
    click.echo(f"└─────────────────────────────────────────────┘")

    if _session.capture_path:
        click.echo(f"  Active capture: {_session.capture_path}")
    click.echo()

    commands = {
        "help": "Show this help message",
        "info [path]": "Show capture file metadata",
        "actions [path]": "List draw calls / actions",
        "textures [path]": "List textures in capture",
        "save-texture <id> <path>": "Save a texture to file",
        "pipeline <event_id>": "Inspect pipeline state",
        "shader <event_id>": "Disassemble shader",
        "counters [path]": "List GPU counters",
        "thumb <rdc> <output>": "Extract thumbnail",
        "convert <input> <output>": "Convert capture format",
        "capture <exe>": "Launch app for capture",
        "version": "Show version info",
        "open <path>": "Set active capture file",
        "goto <event_id>": "Navigate to event",
        "status": "Show session status",
        "undo": "Undo last change",
        "redo": "Redo last change",
        "save-session <path>": "Save session",
        "load-session <path>": "Load session",
        "quit / exit": "Exit REPL",
    }

    if has_pt:
        pt_session = PromptSession(history=InMemoryHistory())

    while True:
        try:
            capture_name = os.path.basename(_session.capture_path) if _session.capture_path else "no capture"
            modified = "*" if _session.modified else ""
            prompt_str = f"renderdoc [{capture_name}{modified}]> "

            if has_pt:
                line = pt_session.prompt(prompt_str).strip()
            else:
                line = input(prompt_str).strip()

            if not line:
                continue

            parts = line.split()
            cmd = parts[0].lower()
            args = parts[1:]

            if cmd in ("quit", "exit", "q"):
                click.echo("Goodbye!")
                break
            elif cmd == "help":
                click.echo("Available commands:")
                for k, v in commands.items():
                    click.echo(f"  {k:<30} {v}")
            elif cmd == "open":
                if args:
                    path = args[0]
                    if os.path.isfile(path):
                        _session.set_capture(path)
                        click.echo(f"Opened: {path}")
                    else:
                        click.echo(f"File not found: {path}")
                else:
                    click.echo("Usage: open <path.rdc>")
            elif cmd == "goto":
                if args:
                    try:
                        eid = int(args[0])
                        _session.set_event(eid)
                        click.echo(f"Moved to event {eid}")
                    except ValueError:
                        click.echo("Event ID must be an integer")
                else:
                    click.echo("Usage: goto <event_id>")
            elif cmd == "status":
                ctx = click.Context(session_status)
                session_status.invoke(ctx)
            elif cmd == "undo":
                if _session.undo():
                    click.echo(f"Undone. Event: {_session.current_event_id}")
                else:
                    click.echo("Nothing to undo.")
            elif cmd == "redo":
                if _session.redo():
                    click.echo(f"Redone. Event: {_session.current_event_id}")
                else:
                    click.echo("Nothing to redo.")
            elif cmd == "save-session":
                if args:
                    _session.save(args[0])
                    click.echo(f"Session saved to {args[0]}")
                else:
                    click.echo("Usage: save-session <path>")
            elif cmd == "load-session":
                if args and os.path.isfile(args[0]):
                    _session = Session.load(args[0])
                    click.echo(f"Session loaded from {args[0]}")
                else:
                    click.echo("Usage: load-session <path>")
            else:
                # Delegate to Click commands
                try:
                    cli.main(args=parts, standalone_mode=False)
                except SystemExit:
                    pass
                except Exception as e:
                    click.echo(f"Error: {e}")

        except (KeyboardInterrupt, EOFError):
            click.echo("\nGoodbye!")
            break


# ── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    cli()
