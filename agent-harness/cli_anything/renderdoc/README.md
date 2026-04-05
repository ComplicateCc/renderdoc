# CLI-Anything: RenderDoc

CLI harness for **RenderDoc** — a frame-capture based graphics debugger.

## Prerequisites

- **Python** 3.8+
- **RenderDoc** installed with `renderdoccmd` on PATH
  - Windows: [Download MSI/ZIP](https://renderdoc.org/builds)
  - Linux: `sudo apt install renderdoc` or [download tarball](https://renderdoc.org/builds)
- **renderdoc Python module** on `PYTHONPATH` (optional, for replay/analysis commands)

## Installation

```bash
cd renderdoc/agent-harness
pip install -e .
```

Verify:

```bash
cli-anything-renderdoc --help
cli-anything-renderdoc version
```

## Quick Start

```bash
# Enter REPL mode (default)
cli-anything-renderdoc

# Show capture info
cli-anything-renderdoc info capture.rdc

# List draw calls
cli-anything-renderdoc actions capture.rdc

# List textures
cli-anything-renderdoc textures capture.rdc

# Save a texture
cli-anything-renderdoc save-texture 42 output.png --rdc capture.rdc

# Pipeline state at event
cli-anything-renderdoc pipeline 100 --rdc capture.rdc

# Disassemble pixel shader
cli-anything-renderdoc shader 100 --rdc capture.rdc --stage pixel

# Extract thumbnail
cli-anything-renderdoc thumb capture.rdc thumbnail.png

# JSON output
cli-anything-renderdoc --json info capture.rdc
```

## Commands

| Command | Description |
|---------|-------------|
| `info` | Show capture file metadata |
| `actions` | List draw calls / actions |
| `textures` | List all textures |
| `save-texture` | Export a texture to image file |
| `pipeline` | Inspect GPU pipeline state |
| `shader` | Disassemble shaders |
| `counters` | List GPU performance counters |
| `thumb` | Extract embedded thumbnail |
| `convert` | Convert capture formats |
| `capture` | Launch executable for capture |
| `version` | Show version info |
| `session status` | Session state |
| `session save/load` | Save/load session |
| `session undo/redo` | Undo/redo state changes |

All commands support `--json` for machine-readable output.

## REPL Mode

Running `cli-anything-renderdoc` without arguments enters interactive REPL:

```
renderdoc [no capture]> open capture.rdc
renderdoc [capture.rdc]> actions
renderdoc [capture.rdc]> goto 42
renderdoc [capture.rdc]> pipeline 42
renderdoc [capture.rdc]> quit
```

## Running Tests

```bash
cd renderdoc/agent-harness
python -m pytest cli_anything/renderdoc/tests/ -v
```
