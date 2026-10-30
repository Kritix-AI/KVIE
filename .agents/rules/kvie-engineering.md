---
description: Shared engineering conventions, verified build commands, and dictation rules for KVIE
trigger: always_on
---

# KVIE Engineering Rules

## 1. Verified Project Commands
- **Frontend / Shell Build**: `npm run build` (Vite production build)
- **Desktop Tauri Verification**: `cargo check` (Run inside `src-tauri/` or via `--manifest-path src-tauri/Cargo.toml`)
- **Backend Tests**: `pytest tests/test_kvie_service.py`
- **Tauri Dev Server**: `npm run tauri dev`

## 2. Core Dictation & Real-Time Typing Conventions
- **Speaker Intent Integrity**: In dictation mode, do not silently add words or change what the speaker meant.
- **Hardware Modifier Release**: When simulating keystrokes in Windows while `Alt` is held (e.g. `Alt + \`` push-to-talk), temporarily release `VK_MENU` via `keybd_event` before simulated Backspaces or Unicode inputs, and restore it immediately after.
- **Direct Unicode Typing vs. Clipboard**: Use direct Unicode typing (`enigo.text`) for real-time streaming deltas (`do_verify: false`) to avoid Windows clipboard lockouts. Reserve clipboard paste (`Ctrl+V`) for verified atomic replacements.
- **Sliding Overlap**: Preserve word-overlap detection (`stripCommittedOverlap`) to prevent word doubling across sliding audio windows.

## 3. Team Safety & Coordination
- **Investigator Immutability**: Investigators (`backend-investigator`, `voice-quality-investigator`, `security-auditor`) are strictly read-only and must never edit files.
- **Hypothesis Labeling**: Clearly label hypotheses as `[Hypothesis]`; never report them as confirmed bugs.
- **Single-Writer Safety**: Avoid assigning multiple agents to edit the same files at the same time.
- **Independent Verification**: Fixes must be verified independently by `kvie-verifier` against original reproduction steps.
- **System Boundaries**: Do not run destructive commands, access production systems, or expose credentials.
- **Push Policy**: Never push code to remote repositories without explicit user permission.
