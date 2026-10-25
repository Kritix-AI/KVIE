# KVIE Keyboard — Android starter

A minimal, working Android IME (custom keyboard) with a mic button that
dictates into any focused text field, in any app. Built to be the Android
half of the KVIE-mobile plan (see `KVIE-mobile-architecture.md`).

## What's here

- `KVIEInputMethodService.kt` — the keyboard itself. Bootstrapped with
  Android's built-in `SpeechRecognizer` for STT so it's testable
  immediately, with a clearly marked spot to swap in whisper.cpp for
  on-device transcription later.
- `AutoEditClient.kt` — stub client that POSTs the transcript to a
  `/autoedit` backend endpoint (Qwen2.5-1.5B cleanup) and swaps the
  committed text for the refined version when it returns. Point
  `BASE_URL` at your backend, or replace with an on-device LLM call.
- `SetupActivity.kt` — launcher screen with buttons to open system
  keyboard settings and request mic permission (a keyboard's own
  process can't trigger either of those itself).
- `stripFillerWords()` — placeholder Stage-1 cleanup. Replace with the
  actual regex rules from desktop KVIE's Stage 1 pass.

## Build & run

1. Open the `KVIEKeyboard/` folder in Android Studio (Jellyfish or
   newer). It'll sync Gradle automatically.
2. Run on a device or emulator (API 26+).
3. Open the app, tap through the two setup buttons:
   - enable "KVIE Keyboard" under system keyboard settings
   - grant microphone permission
4. Switch to the keyboard in any text field (long-press the space bar
   on most keyboards, or use the globe/keyboard-switch icon) and tap
   the mic.

## Next steps, in order

1. Deploy the `/autoedit` backend endpoint (see architecture doc,
   section 5) and point `AutoEditClient.BASE_URL` at it.
2. Replace `SpeechRecognizer` with `whisper.cpp` compiled for Android
   for on-device, private transcription.
3. Port Stage 1 regex rules, voice commands, snippets, and custom
   dictionary logic from desktop KVIE into this project's `core`
   equivalents.
4. Quantize Qwen2.5-1.5B (Q4) and run it on-device via llama.cpp or
   MLC-LLM instead of the backend call, once you've validated the
   pipeline end-to-end.
