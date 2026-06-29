# TEST.md — CLI-Anything RenderDoc Test Plan & Results

## Test Inventory Plan

- `test_core.py`: 12+ unit tests planned
- `test_full_e2e.py`: 6+ E2E tests planned

## Unit Test Plan (`test_core.py`)

### Session Module
- `test_session_create` — Create session with default values
- `test_session_set_capture` — Set capture path
- `test_session_set_event` — Navigate to event
- `test_session_undo` — Undo state change
- `test_session_redo` — Redo after undo
- `test_session_undo_empty` — Undo with nothing to undo
- `test_session_redo_empty` — Redo with nothing to redo
- `test_session_save_load` — Round-trip save/load
- `test_session_status` — Status dict structure
- `test_session_command_log` — Command history logging

### Backend Utils
- `test_find_renderdoccmd_not_found` — Error message when not installed
- `test_find_renderdoc_module` — Module availability check

## E2E Test Plan (`test_full_e2e.py`)

### CLI Subprocess Tests
- `test_help` — `--help` exits cleanly
- `test_version` — `version` command outputs version
- `test_info_no_capture` — Error when no capture specified
- `test_session_save_load_subprocess` — Session save/load via CLI
- `test_json_output` — `--json` flag produces valid JSON

### Real Backend Tests (require RenderDoc + .rdc file)
- `test_thumb_real_capture` — Extract thumbnail from real .rdc
- `test_actions_real_capture` — List actions from real .rdc
- `test_textures_real_capture` — List textures from real .rdc

## Realistic Workflow Scenarios

### Scenario 1: Capture Analysis Pipeline
- **Simulates**: Developer debugging a graphics frame
- **Operations**: open capture → list actions → goto event → inspect pipeline → save texture
- **Verified**: Each command succeeds, JSON output valid

### Scenario 2: Texture Extraction Batch
- **Simulates**: Extracting all render targets for comparison
- **Operations**: open capture → list textures → save-texture for each
- **Verified**: Output files exist, size > 0, correct format

### Scenario 3: Session Persistence
- **Simulates**: Resuming a debug session
- **Operations**: set capture → navigate → save session → load session → verify state
- **Verified**: State round-trips correctly
