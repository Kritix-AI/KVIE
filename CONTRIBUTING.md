# Contributing to Kritix - Voice Intelligence Engine (KVIE)

Thank you for your interest in contributing to **KVIE**! We welcome bug reports, feature suggestions, and pull requests from developers around the world.

---

## 🛠️ Development Setup

1. **Prerequisites**:
   - Windows 10/11
   - Node.js (v18+)
   - Rust toolchain (1.75+) with `x86_64-pc-windows-msvc`
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

- `src-tauri/src/lib.rs`: Rust backend containing Win32 kernel low-level keyboard hooks (`WH_KEYBOARD_LL`), system tray initialization, process inspectors, and COM `IUIAutomation` surrounding text reader.
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
