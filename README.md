# 🎙️ Kritix - Voice Intelligence Engine (KVIE)

> **Local-First, Ultra-Fast AI Voice Typing & System-Wide Auto-Injection Engine for Windows.**  
> *100% Wispr Flow Parity with Complete Privacy & Zero Cloud Lag.*

[![Tauri v2](https://img.shields.io/badge/Tauri-v2.0-blue.svg?logo=tauri)](https://tauri.app)
[![Rust](https://img.shields.io/badge/Rust-1.75+-orange.svg?logo=rust)](https://www.rust-lang.org/)
[![React](https://img.shields.io/badge/React-18-cyan.svg?logo=react)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0-blue.svg?logo=typescript)](https://www.typescriptlang.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## ✨ Overview

**Kritix Voice Intelligence Engine (KVIE)** is an open-source, local-first voice productivity shell that turns your speech into polished prose across **any Windows application** (Notepad, WhatsApp Desktop, Chrome, VS Code, MS Word, Slack, Discord).

Engineered with a high-performance **Tauri v2 + Rust** core, native **Win32 Low-Level Keyboard Hooks (`WH_KEYBOARD_LL`)**, and **Windows UI Automation COM interfaces (`IUIAutomation`)**, KVIE reads surrounding text context and executes intelligent real-time auto-editing via **Qwen2.5-1.5B-Instruct**.

---

## 📊 KVIE vs. Wispr Flow Feature Parity Matrix

| Feature / Architecture Layer | Wispr Flow | Kritix (KVIE) | Status |
| :--- | :--- | :--- | :--- |
| **System-Wide Global Hotkey** | ✅ `Ctrl + Alt + R` | ✅ `Ctrl + Alt + R` (Native Windows Low-Level Hook `WH_KEYBOARD_LL`) | 🟢 **COMPLETED** |
| **Active App Detection** | ✅ Process Name & Title | ✅ Dual Win32 Process Inspector (`OpenProcess` + `K32GetProcessImageFileNameW`) | 🟢 **COMPLETED** |
| **Real-Time Cross-App Auto-Inject** | ✅ Instant System Injection | ✅ Differential `eraseAndInject` + Clipboard Simulation | 🟢 **COMPLETED** |
| **System Tray & Close-to-Tray** | ✅ Yes | ✅ Rust `setup_system_tray` + `CloseRequested` Intercept | 🟢 **COMPLETED** |
| **Floating Mic Overlay Widget** | ✅ Sleek Floating Pill | ✅ Compact Floating Pill Widget (Always-On-Top, Non-Obtrusive) | 🟢 **COMPLETED** |
| **Local / Privacy-First Engine** | ❌ Cloud-Only (Requires Internet) | ✅ **100% Local & Private** (Faster-Whisper / Whisper Large-v3 Turbo) | 🟢 **KVIE ADVANTAGE!** |
| **Surrounding Text Context Extraction** | ✅ Reads screen text via OS Accessibility | ✅ **Windows UI Automation COM (`IUIAutomation` / `IUIAutomationTextPattern`)** | 🟢 **COMPLETED** |
| **AI LLM Post-Processing (Auto-Edit)** | ✅ Strips "um/ah", fixes grammar & formatting | ✅ **Dual-Stage Engine: 0ms Regex + Qwen2.5-1.5B-Instruct Model** | 🟢 **COMPLETED** |
| **Voice Snippets & Text Expansion** | ✅ Spoken triggers expand to long templates | ✅ **Spoken Cue Engine** (Calendly, Signatures, Addresses, Phone) | 🟢 **COMPLETED** |
| **Voice Command Mode** | ✅ Spoken instructions (*"Make this email formal"*) | ✅ **Voice Instruction Execution Engine** (*"Make formal"*, *"Summarize"*) | 🟢 **COMPLETED** |
| **Personalized Custom Dictionary** | ✅ Custom names, acronyms, jargon | ✅ **Vocabulary Bias Engine** (Kritix, Tauri, Hinglish, Custom terms) | 🟢 **COMPLETED** |
| **Live Translation (100+ Languages)** | ✅ Translate spoken voice to target language | ✅ **Live Voice Translation Engine** (English, Hindi, Spanish, French, etc.) | 🟢 **COMPLETED** |

---

## 🚀 Key Features

### 1. ⌨️ System-Wide Low-Level Keyboard Hook (`Ctrl + Alt + R`)
* Uses native Windows kernel driver hook `SetWindowsHookExW(WH_KEYBOARD_LL)` in Rust to capture hotkeys system-wide before any other app (Radeon, Shadowplay, Chrome) can block them.

### 2. 👁️ Windows UI Automation COM Reader (`IUIAutomation`)
* Uses official Windows COM interface pointers (`IUIAutomationTextPattern` & `IUIAutomationValuePattern`) to read up to **500 characters of surrounding text** surrounding the active cursor in Notepad, Chrome, WhatsApp, VS Code, Word, and Slack.

### 3. 🧠 Dual-Stage AI Auto-Edit (Qwen2.5-1.5B-Instruct)
* **Stage 1 (0ms Regex Filter)**: Strips hesitations (*"um"*, *"uh"*, *"aah"*, *"like"*), fixes spacing, and cleans duplicate words.
* **Stage 2 (Qwen2.5-1.5B-Instruct)**: Resolves false starts (*"meeting at 2... wait 3 PM"* → *"meeting at 3 PM"*) and formats text while strictly preserving **Verbatim Roman Hinglish** script (*"Aaj ka kya plan hai bhai"*).

### 4. 🪄 Voice Command Mode
* Execute spoken instructions on existing text:
  * *"Make this email formal and polite"*
  * *"Summarize this into 3 bullet points"*
  * *"Shorten this draft"*

### 5. ⚡ Voice Snippets & Text Expansion
* Define spoken trigger cues that expand into templates:
  * *"my meeting link"* → `https://calendly.com/kritix/30min`
  * *"my email signature"* → `Best regards,\nKritix Voice Intelligence Engine Team`

### 6. 📖 Personalized Custom Dictionary
* Register custom jargon, brand names, and phonetic sound-alikes (*"critics"* → *"Kritix"*, *"towel"* → *"Tauri"*) to bias STT transcription and LLM auto-correction.

### 7. 🌐 Live Translation Engine (100+ Languages)
* Real-time spoken translation into English, Hindi, Spanish, French, German, Japanese, Chinese, Russian, Arabic, etc.

---

## 🏗️ System Architecture

```
                               ┌─────────────────────────────────────────┐
                               │     Windows OS Kernel & Active Apps     │
                               │  (Notepad, WhatsApp, Chrome, VS Code)   │
                               └────────────────────┬────────────────────┘
                                                    │
                 ┌──────────────────────────────────┴──────────────────────────────────┐
                 │                                                                     │
                 ▼                                                                     ▼
   ┌───────────────────────────┐                                         ┌───────────────────────────┐
   │  WH_KEYBOARD_LL Hotkey    │                                         │ Windows UI Automation COM │
   │  (Ctrl + Alt + R Trigger)  │                                         │ (IUIAutomationTextPattern)│
   └─────────────┬─────────────┘                                         └─────────────┬─────────────┘
                 │                                                                     │
                 └──────────────────────────────────┬──────────────────────────────────┘
                                                    │
                                                    ▼
                                     ┌─────────────────────────────┐
                                     │     Rust Tauri v2 Core      │
                                     │   (eraseAndInject Bridge)   │
                                     └──────────────┬──────────────┘
                                                    │
                                                    ▼
                                     ┌─────────────────────────────┐
                                     │   Qwen2.5-1.5B Auto-Edit    │
                                     │ & Voice Snippets Engine     │
                                     └──────────────┬──────────────┘
                                                    │
                                                    ▼
                                     ┌─────────────────────────────┐
                                     │   Compact Floating Mic Pill │
                                     │    Overlay (React + Vite)   │
                                     └─────────────────────────────┘
```

---

## 📦 Quick Start & Installation

### Prerequisites
* **Windows 10/11**
* **Node.js** (v18+) & **npm**
* **Rust** (1.75+) with `cargo`
* **Ollama** (Optional for local Qwen2.5 execution: `ollama run qwen2.5:1.5b`)

### Build & Run Locally

```bash
# 1. Clone Repository
git clone https://github.com/Aryan-sourcee/KVIE.git
cd KVIE

# 2. Install Frontend Dependencies
npm install

# 3. Check Rust Compilation
cd src-tauri
cargo check
cd ..

# 4. Run KVIE Desktop Application
npm run tauri:dev
```

---

## 📄 License

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for more details.

---

<p align="center">
  Developed with ❤️ by the <b>Kritix Open-Source Team</b>.
</p>
