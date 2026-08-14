# Contributing to Kritix - Voice Intelligence Engine (KVIE)

Thank you for your interest in contributing to **KVIE**! We welcome bug reports, feature suggestions, and pull requests from developers around the world.

---

## 🛠️ Development Setup

1. **Prerequisites**:
   - macOS (Apple Silicon M1-M4 / Intel) or Windows 10/11
   - Node.js (v18+) & npm
   - Rust toolchain (1.75+) with `cargo`
   - Xcode Command Line Tools (on macOS: `xcode-select --install`)
   - Ollama (optional for local LLM inference)

2. **Setup Repository**:
   ```bash
   git clone https://github.com/Aryan-sourcee/KVIE.git
   cd KVIE
   npm install
   ```

3. **Running Dev Server**:
   ```bash
   npm run tauri:dev
   ```

---

## 📁 Codebase Structure

- `src-tauri/src/lib.rs`: Cross-platform Rust engine supporting:
  - **Windows**: Win32 low-level keyboard hooks (`WH_KEYBOARD_LL`), COM `IUIAutomation` surrounding text reader, and process inspectors.
  - **macOS**: `CGEventTap` global hotkey listener, `AXUIElement` accessibility context extraction, and Cocoa `NSWorkspace` app tracker.
- `src-tauri/Info.plist`: macOS application bundle permissions and usage descriptions.
- `src/lib/autoEdit.ts`: Dual-Stage AI Auto-Edit pipeline (0ms Regex sanitizer + Qwen2.5-1.5B model).
- `src/lib/snippetsEngine.ts`: Spoken trigger cue text expansion engine.
- `src/lib/voiceCommandEngine.ts`: Voice Instruction Execution Engine (*"Make formal"*, *"Summarize"*).
- `src/lib/customDictionary.ts`: Personalized custom dictionary & phonetic sound-alike correction engine.
- `src/lib/translationEngine.ts`: Real-time multilingual voice translation engine.
- `src/components/FloatingMicWidget.tsx`: Compact Always-On-Top floating mic overlay widget.

---

## 🧪 Pre-Commit Verification

Before submitting a Pull Request, please run:
```bash
# 1. TypeCheck Frontend
npx tsc --noEmit

# 2. Check Rust Compilation
cd src-tauri
cargo check
cd ..
```

---

## 📜 Pull Request Guidelines

1. Create a clear branch name: `feature/my-feature` or `fix/my-bugfix`.
2. Follow standard commit message formatting.
3. Ensure no local `.env` keys or temporary log files are committed.
