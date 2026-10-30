use std::path::PathBuf;
use std::sync::Mutex;
use std::time::Duration;

use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
#[cfg(not(any(target_os = "android", target_os = "ios")))]
use arboard::Clipboard;
#[cfg(not(any(target_os = "android", target_os = "ios")))]
use enigo::{Direction, Enigo, Key, Keyboard, Settings};
#[cfg(not(any(target_os = "android", target_os = "ios")))]
use tauri::menu::{Menu, MenuItem};
#[cfg(not(any(target_os = "android", target_os = "ios")))]
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{Emitter, Manager};

struct KvieState {
    document: Mutex<DocumentState>,
    db_path: PathBuf,
}

#[derive(Default, Clone)]
struct DocumentState {
    text: String,
    cursor: usize,
    version: u64,
    undo: Vec<String>,
    redo: Vec<String>,
}

const MAX_ERASE_COUNT: usize = 500;
const MAX_UNDO_STACK: usize = 100;
const MAX_SURROUNDING_TEXT_LEN: usize = 500;

#[cfg(not(any(target_os = "android", target_os = "ios")))]
static LAST_INJECT_MS: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
#[cfg(not(any(target_os = "android", target_os = "ios")))]
const INJECT_RATE_LIMIT_MS: u64 = 25;

#[cfg(not(any(target_os = "android", target_os = "ios")))]
static INJECT_CLOCK: std::sync::OnceLock<std::time::Instant> = std::sync::OnceLock::new();

#[cfg(not(any(target_os = "android", target_os = "ios")))]
fn inject_clock_ms() -> u64 {
    INJECT_CLOCK.get_or_init(std::time::Instant::now).elapsed().as_millis() as u64
}

static HOTKEY_ENABLED: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(true);

/// Result of a text injection, reported back to the UI so it can tell the
/// user when a paste may not have landed.
#[derive(Serialize)]
struct InjectionOutcome {
    verification: &'static str, // "verified" | "unverified" | "skipped"
}

// Terminal shells paste with Shift+Insert; Ctrl+V is not universal there.
#[cfg(target_os = "windows")]
const TERMINAL_PROCESSES: &[&str] = &[
    "windowsterminal.exe",
    "wt.exe",
    "cmd.exe",
    "powershell.exe",
    "pwsh.exe",
    "conhost.exe",
    "openconsole.exe",
    "alacritty.exe",
    "wezterm-gui.exe",
    "mintty.exe",
    "hyper.exe",
];

#[derive(Serialize)]
struct RuntimeStatus {
    desktop: bool,
    stt: &'static str,
    storage: &'static str,
}

#[derive(Serialize, Clone)]
struct DocumentSnapshot {
    text: String,
    cursor: usize,
    version: u64,
    can_undo: bool,
    can_redo: bool,
}

#[derive(Serialize, Clone, Debug)]
pub struct ActiveAppInfo {
    pub app_name: String,
    pub process_name: String,
}

#[cfg(target_os = "windows")]
static LAST_ACTIVE_APP: Mutex<Option<ActiveAppInfo>> = Mutex::new(None);
#[cfg(target_os = "windows")]
static LAST_ACTIVE_WINDOW: std::sync::atomic::AtomicIsize = std::sync::atomic::AtomicIsize::new(0);
#[cfg(target_os = "windows")]
static LAST_ACTIVE_WINDOW_PID: std::sync::atomic::AtomicU32 = std::sync::atomic::AtomicU32::new(0);
// Lock-free handle access: the WH_KEYBOARD_LL callback must never block on a mutex.
#[cfg(target_os = "windows")]
static APP_HANDLE_FOR_HOTKEY: std::sync::OnceLock<tauri::AppHandle> = std::sync::OnceLock::new();
// Modifier state — used ONLY to suppress the voice key when it is part of a
// shortcut or character chord (Ctrl+` = terminal, Shift+` = ~, AltGr, ...).
#[cfg(target_os = "windows")]
static IS_CTRL_L_HELD: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);
#[cfg(target_os = "windows")]
static IS_CTRL_R_HELD: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);
#[cfg(target_os = "windows")]
static IS_ALT_L_HELD: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);
#[cfg(target_os = "windows")]
static IS_ALT_R_HELD: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);
#[cfg(target_os = "windows")]
static IS_SHIFT_L_HELD: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);
#[cfg(target_os = "windows")]
static IS_SHIFT_R_HELD: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);

// Voice-key (`) state machine: hold = push-to-talk, double-tap = continuous
// listening (tap again to stop), single quick tap = stops itself.
#[cfg(target_os = "windows")]
const HOTKEY_STATE_IDLE: u8 = 0;
#[cfg(target_os = "windows")]
const HOTKEY_STATE_HELD: u8 = 1;
#[cfg(target_os = "windows")]
const HOTKEY_STATE_WAIT_SECOND_TAP: u8 = 2;
#[cfg(target_os = "windows")]
const HOTKEY_STATE_CONTINUOUS: u8 = 3;
#[cfg(target_os = "windows")]
const HOTKEY_STATE_CONTINUOUS_WAIT_RELEASE: u8 = 4;
// Held longer than this = plain push-to-talk (release stops).
#[cfg(target_os = "windows")]
const HOTKEY_HOLD_MS: u64 = 280;
// Second press within this window after a quick tap = double-tap.
#[cfg(target_os = "windows")]
const HOTKEY_TAP_WINDOW_MS: u64 = 320;
#[cfg(target_os = "windows")]
static HOTKEY_STATE: std::sync::atomic::AtomicU8 = std::sync::atomic::AtomicU8::new(HOTKEY_STATE_IDLE);
#[cfg(target_os = "windows")]
static HOTKEY_DOWN_MS: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
// Bumped on every state transition; lets the double-tap timer detect that
// something happened meanwhile and retire itself.
#[cfg(target_os = "windows")]
static HOTKEY_EVENT_GENERATION: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);

#[cfg(target_os = "windows")]
static APP_CHILD_JOB: std::sync::OnceLock<isize> = std::sync::OnceLock::new();

#[derive(Deserialize, Debug)]
#[serde(rename_all = "lowercase")]
enum DocumentAction {
    Append,
    Insert,
    Replace,
    Clear,
}

#[derive(Deserialize)]
struct DocumentEdit {
    action: DocumentAction,
    text: Option<String>,
    start: Option<usize>,
    end: Option<usize>,
}

fn initialize_database(path: &PathBuf) -> Result<(), String> {
    let connection = Connection::open(path).map_err(|error| error.to_string())?;
    connection.execute_batch(
        "CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            text TEXT NOT NULL,
            cursor INTEGER NOT NULL,
            version INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS document_operations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id TEXT NOT NULL,
            action TEXT NOT NULL,
            before_text TEXT NOT NULL,
            after_text TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );",
    ).map_err(|error| error.to_string())
}

fn load_document(path: &PathBuf) -> Result<DocumentState, String> {
    let connection = Connection::open(path).map_err(|error| error.to_string())?;
    let row = connection.query_row(
        "SELECT text, cursor, version FROM documents WHERE id = 'active'",
        [],
        |row| Ok((row.get::<_, String>(0)?, row.get::<_, usize>(1)?, row.get::<_, u64>(2)?)),
    ).optional().map_err(|error| error.to_string())?;
    Ok(row.map(|(text, cursor, version)| DocumentState { text, cursor, version, ..Default::default() }).unwrap_or_default())
}

fn persist_document(path: &PathBuf, document: &DocumentState, action: &str, before: &str) -> Result<(), String> {
    let connection = Connection::open(path).map_err(|error| error.to_string())?;
    let now = chrono_like_now();
    connection.execute(
        "INSERT INTO documents(id, text, cursor, version, updated_at) VALUES('active', ?, ?, ?, ?)
         ON CONFLICT(id) DO UPDATE SET text=excluded.text, cursor=excluded.cursor, version=excluded.version, updated_at=excluded.updated_at",
        params![document.text, document.cursor, document.version, now],
    ).map_err(|error| error.to_string())?;
    if before != document.text {
        connection.execute(
            "INSERT INTO document_operations(document_id, action, before_text, after_text, created_at) VALUES('active', ?, ?, ?, ?)",
            params![action, before, document.text, now],
        ).map_err(|error| error.to_string())?;
        // The op log is never read back; keep it bounded so the DB cannot grow forever.
        connection.execute(
            "DELETE FROM document_operations WHERE id NOT IN (SELECT id FROM document_operations ORDER BY id DESC LIMIT 500)",
            [],
        ).map_err(|error| error.to_string())?;
    }
    Ok(())
}

fn chrono_like_now() -> i64 {
    std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap_or_default().as_millis() as i64
}

#[tauri::command]
fn runtime_status() -> RuntimeStatus {
    RuntimeStatus { desktop: true, stt: "faster-whisper-service", storage: "sqlite" }
}

#[tauri::command]
fn get_document(state: tauri::State<'_, KvieState>) -> Result<DocumentSnapshot, String> {
    let document = state.document.lock().map_err(|_| "document lock poisoned".to_string())?;
    Ok(snapshot(&document))
}

#[tauri::command]
fn apply_document_edit(edit: DocumentEdit, state: tauri::State<'_, KvieState>) -> Result<DocumentSnapshot, String> {
    let mut document = state.document.lock().map_err(|_| "document lock poisoned".to_string())?;
    let before = document.text.clone();

    let content = edit.text.unwrap_or_default();
    if content.len() > 100 * 1024 {
        return Err("edit text exceeds maximum allowed size".to_string());
    }
    let sanitized: String = content.chars().filter(|c| !c.is_control() || *c == '\n' || *c == '\t').collect();

    match edit.action {
        DocumentAction::Append => {
            if !document.text.is_empty() && !document.text.ends_with(' ') && !document.text.ends_with('\n') { document.text.push(' '); }
            document.text.push_str(sanitized.trim());
            document.cursor = document.text.len();
        }
        DocumentAction::Insert => {
            let default_position = byte_index_to_utf16(&document.text, document.cursor);
            let position = utf16_index_to_byte(&document.text, edit.start.unwrap_or(default_position))?;
            document.text.insert_str(position, &sanitized);
            document.cursor = position + sanitized.len();
        }
        DocumentAction::Replace => {
            let start_utf16 = edit.start.ok_or("replace requires start")?;
            let end_utf16 = edit.end.ok_or("replace requires end")?;
            if start_utf16 > end_utf16 { return Err("replace start must be <= end".to_string()); }
            let start = utf16_index_to_byte(&document.text, start_utf16)?;
            let end = utf16_index_to_byte(&document.text, end_utf16)?;
            document.text.replace_range(start..end, &sanitized);
            document.cursor = start + sanitized.len();
        }
        DocumentAction::Clear => { document.text.clear(); document.cursor = 0; }
    }
    if before != document.text {
        document.undo.push(before.clone());
        if document.undo.len() > MAX_UNDO_STACK {
            document.undo.remove(0);
        }
        document.redo.clear();
        document.version += 1;
        persist_document(&state.db_path, &document, &format!("{:?}", edit.action).to_lowercase(), &before)?;
    }
    Ok(snapshot(&document))
}

#[tauri::command]
fn undo_document(state: tauri::State<'_, KvieState>) -> Result<DocumentSnapshot, String> {
    let mut document = state.document.lock().map_err(|_| "document lock poisoned".to_string())?;
    if let Some(previous) = document.undo.pop() {
        let current = document.text.clone();
        document.redo.push(current.clone());
        document.text = previous;
        document.cursor = document.text.len();
        document.version += 1;
        persist_document(&state.db_path, &document, "undo", &current)?;
    }
    Ok(snapshot(&document))
}

#[tauri::command]
fn redo_document(state: tauri::State<'_, KvieState>) -> Result<DocumentSnapshot, String> {
    let mut document = state.document.lock().map_err(|_| "document lock poisoned".to_string())?;
    if let Some(next) = document.redo.pop() {
        let current = document.text.clone();
        document.undo.push(current.clone());
        document.text = next;
        document.cursor = document.text.len();
        document.version += 1;
        persist_document(&state.db_path, &document, "redo", &current)?;
    }
    Ok(snapshot(&document))
}

#[tauri::command]
fn erase_and_inject(erase_count: usize, text: String, verify: Option<bool>) -> Result<InjectionOutcome, String> {
    #[cfg(not(any(target_os = "android", target_os = "ios")))]
    {
        use std::thread;
        use std::sync::atomic::Ordering;

        // Monotonic clock: a backward wall-clock step must not disable injections.
        let now_ms = inject_clock_ms();
        let last = LAST_INJECT_MS.load(Ordering::Relaxed);
        let elapsed = now_ms.saturating_sub(last);
        if last != 0 && elapsed < INJECT_RATE_LIMIT_MS {
            thread::sleep(Duration::from_millis(INJECT_RATE_LIMIT_MS - elapsed));
        }
        // Interim deltas skip verification to keep live typing fast; finals,
        // commands and one-shot injections verify by default.
        let do_verify = verify.unwrap_or(true);

        let capped_erase = erase_count.min(MAX_ERASE_COUNT);
        let sanitized: String = text.chars().filter(|c| !c.is_control() || *c == '\n' || *c == '\t').collect();
        if sanitized.is_empty() && capped_erase == 0 {
            return Ok(InjectionOutcome { verification: "skipped" });
        }

        #[cfg(target_os = "windows")]
        {
            let target_window = resolve_last_external_window()?;
            if window_is_elevated(target_window) {
                return Err("KVIE cannot type into apps running as administrator — Windows blocks simulated input into elevated apps (UIPI). Run KVIE as administrator to dictate into them.".to_string());
            }
            focus_window(target_window)?;
        }

        // Snapshot of the text before the caret, taken before erasing — used to
        // distinguish "UIA cannot read this app" from "paste did not land".
        #[cfg(target_os = "windows")]
        let pre_paste_context = if do_verify { extract_focused_surrounding_text() } else { String::new() };

        #[cfg(target_os = "windows")]
        use windows_sys::Win32::UI::Input::KeyboardAndMouse::{
            keybd_event, GetAsyncKeyState, KEYEVENTF_KEYUP, VK_MENU, VK_LMENU, VK_RMENU
        };

        #[cfg(target_os = "windows")]
        let alt_physically_down = unsafe { GetAsyncKeyState(VK_MENU as i32) < 0 }
            || IS_ALT_L_HELD.load(Ordering::SeqCst)
            || IS_ALT_R_HELD.load(Ordering::SeqCst);

        // Temporarily release Alt so simulated Backspaces, Unicode typing, and Ctrl+V
        // are never combined with Alt (Alt+Backspace = Undo, Alt+Ctrl+V = ignored).
        #[cfg(target_os = "windows")]
        if alt_physically_down {
            unsafe {
                keybd_event(VK_LMENU as u8, 0x38, KEYEVENTF_KEYUP, 0);
                keybd_event(VK_RMENU as u8, 0x38, KEYEVENTF_KEYUP, 0);
                keybd_event(VK_MENU as u8, 0x38, KEYEVENTF_KEYUP, 0);
            }
        }

        let mut enigo = Enigo::new(&Settings::default()).map_err(|error| format!("keyboard unavailable: {error}"))?;

        if capped_erase > 0 {
            for index in 0..capped_erase {
                enigo.key(Key::Backspace, Direction::Click)
                    .map_err(|error| format!("could not erase target text: {error}"))?;
                if index % 10 == 9 {
                    thread::sleep(Duration::from_millis(2));
                }
            }
            thread::sleep(Duration::from_millis(10));
        }

        if sanitized.is_empty() {
            #[cfg(target_os = "windows")]
            if alt_physically_down {
                unsafe {
                    if IS_ALT_L_HELD.load(Ordering::SeqCst) {
                        keybd_event(VK_LMENU as u8, 0x38, 0, 0);
                    } else if IS_ALT_R_HELD.load(Ordering::SeqCst) {
                        keybd_event(VK_RMENU as u8, 0x38, 0, 0);
                    } else {
                        keybd_event(VK_MENU as u8, 0x38, 0, 0);
                    }
                }
            }
            LAST_INJECT_MS.store(inject_clock_ms(), Ordering::Relaxed);
            return Ok(InjectionOutcome { verification: "skipped" });
        }

        // Live real-time streaming injection: type directly via native Unicode SendInput without clipboard thrashing
        if !do_verify {
            let type_result = enigo.text(&sanitized);

            #[cfg(target_os = "windows")]
            if alt_physically_down {
                unsafe {
                    if IS_ALT_L_HELD.load(Ordering::SeqCst) {
                        keybd_event(VK_LMENU as u8, 0x38, 0, 0);
                    } else if IS_ALT_R_HELD.load(Ordering::SeqCst) {
                        keybd_event(VK_RMENU as u8, 0x38, 0, 0);
                    } else {
                        keybd_event(VK_MENU as u8, 0x38, 0, 0);
                    }
                }
            }

            type_result.map_err(|error| format!("could not type target text: {error}"))?;
            LAST_INJECT_MS.store(inject_clock_ms(), Ordering::Relaxed);
            return Ok(InjectionOutcome { verification: "skipped" });
        }

        // Verified / Final injection: paste via clipboard, restoring previous user clipboard
        let previous_clipboard: Option<String> = Clipboard::new().ok().and_then(|mut clipboard| clipboard.get_text().ok());
        {
            let mut clipboard = Clipboard::new().map_err(|error| format!("clipboard unavailable: {error}"))?;
            clipboard.set_text(sanitized.clone()).map_err(|error| format!("clipboard write failed: {error}"))?;
        }

        let pre_paste_sleep = if do_verify { 25 } else { 10 };
        thread::sleep(Duration::from_millis(pre_paste_sleep));

        #[cfg(target_os = "windows")]
        let use_terminal_paste = {
            let target_process = LAST_ACTIVE_APP
                .lock()
                .ok()
                .and_then(|guard| guard.as_ref().map(|info| info.process_name.to_lowercase()))
                .unwrap_or_default();
            TERMINAL_PROCESSES.contains(&target_process.as_str())
        };
        #[cfg(not(target_os = "windows"))]
        let use_terminal_paste = false;

        let paste_result = if use_terminal_paste {
            // Terminals: Shift+Insert instead of Ctrl+V.
            enigo.key(Key::Shift, Direction::Press)
                .and_then(|_| enigo.key(Key::Insert, Direction::Click))
                .and_then(|_| enigo.key(Key::Shift, Direction::Release))
        } else {
            enigo.key(Key::Control, Direction::Press)
                .and_then(|_| enigo.key(Key::V, Direction::Click))
                .and_then(|_| enigo.key(Key::Control, Direction::Release))
        };

        #[cfg(target_os = "windows")]
        if alt_physically_down {
            unsafe {
                if IS_ALT_L_HELD.load(Ordering::SeqCst) {
                    keybd_event(VK_LMENU as u8, 0x38, 0, 0);
                } else if IS_ALT_R_HELD.load(Ordering::SeqCst) {
                    keybd_event(VK_RMENU as u8, 0x38, 0, 0);
                } else {
                    keybd_event(VK_MENU as u8, 0x38, 0, 0);
                }
            }
        }

        paste_result.map_err(|error| format!("could not paste into target app: {error}"))?;

        // Record the timestamp only after a successful injection so a failed
        // attempt never consumes the rate-limit budget.
        LAST_INJECT_MS.store(inject_clock_ms(), Ordering::Relaxed);

        if let Some(previous) = previous_clipboard {
            let pasted_text = sanitized.clone();
            thread::spawn(move || {
                thread::sleep(Duration::from_millis(400));
                if let Ok(mut clipboard) = Clipboard::new() {
                    // Keep a newer clipboard copy made by the user.
                    if clipboard.get_text().ok().as_deref() == Some(pasted_text.as_str()) {
                        let _ = clipboard.set_text(previous);
                    }
                }
            });
        }

        // Insertion verification (Wispr-style): re-read the focused element and
        // confirm the pasted tail is present. Interim deltas skip this to keep
        // live typing fast.
        #[cfg(target_os = "windows")]
        let verification: &'static str = if !do_verify {
            "skipped"
        } else {
            thread::sleep(Duration::from_millis(60));
            let post_context = extract_focused_surrounding_text();
            if post_context.trim().is_empty() && pre_paste_context.trim().is_empty() {
                "skipped"
            } else if paste_tail_matches(&post_context, &sanitized) {
                "verified"
            } else {
                "unverified"
            }
        };
        #[cfg(not(target_os = "windows"))]
        let verification: &'static str = "skipped";

        Ok(InjectionOutcome { verification })
    }
    #[cfg(any(target_os = "android", target_os = "ios"))]
    {
        let _ = (erase_count, text, verify);
        Err("injection is not supported on this platform".to_string())
    }
}

/// Compares the tail of the text-before-caret (re-read after pasting) against
/// the injected text, ignoring carriage returns and tabs.
fn paste_tail_matches(post_context: &str, injected: &str) -> bool {
    let normalize = |s: &str| s.replace(['\r', '\t'], " ");
    let post = normalize(post_context.trim_end());
    let char_count = injected.chars().count();
    let tail_len = char_count.min(80);
    let tail: String = normalize(
        injected
            .chars()
            .skip(char_count - tail_len)
            .collect::<String>()
            .trim_end(),
    );
    if tail.is_empty() {
        return true;
    }
    post.ends_with(&tail)
}

#[cfg(target_os = "windows")]
fn resolve_last_external_window() -> Result<isize, String> {
    use windows_sys::Win32::System::Threading::GetCurrentProcessId;
    use windows_sys::Win32::UI::WindowsAndMessaging::{GetWindowThreadProcessId, IsWindow};

    let target = LAST_ACTIVE_WINDOW.load(std::sync::atomic::Ordering::Acquire);
    if target == 0 || unsafe { IsWindow(target) } == 0 {
        return Err("No target app is available. Focus the app and text field you want to type into, then retry.".to_string());
    }

    // HWND values can be recycled by other processes; require the window to
    // still belong to the process recorded by the tracker.
    let recorded_pid = LAST_ACTIVE_WINDOW_PID.load(std::sync::atomic::Ordering::Acquire);
    let mut current_pid = 0u32;
    unsafe { GetWindowThreadProcessId(target, &mut current_pid) };
    if recorded_pid != 0 && current_pid != recorded_pid {
        return Err("No target app is available. Focus the app and text field you want to type into, then retry.".to_string());
    }

    if current_pid == unsafe { GetCurrentProcessId() } {
        return Err("The last active window belongs to KVIE. Focus the target app and retry.".to_string());
    }

    Ok(target)
}

/// Detects Windows UIPI restrictions: a non-elevated process cannot send
/// simulated input into an elevated (run-as-administrator) target.
#[cfg(target_os = "windows")]
fn window_is_elevated(hwnd: isize) -> bool {
    use windows_sys::Win32::Foundation::{CloseHandle, HANDLE};
    use windows_sys::Win32::Security::{GetTokenInformation, TokenElevation, TOKEN_ELEVATION, TOKEN_QUERY};
    use windows_sys::Win32::System::Threading::{OpenProcess, OpenProcessToken, PROCESS_QUERY_LIMITED_INFORMATION};
    use windows_sys::Win32::UI::WindowsAndMessaging::GetWindowThreadProcessId;

    unsafe {
        let mut pid = 0u32;
        GetWindowThreadProcessId(hwnd as _, &mut pid);
        if pid == 0 {
            return false;
        }
        let process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid);
        if process == 0 {
            return false;
        }
        let mut elevated = false;
        let mut token: HANDLE = 0;
        if OpenProcessToken(process, TOKEN_QUERY, &mut token) != 0 {
            let mut elevation = TOKEN_ELEVATION { TokenIsElevated: 0 };
            let mut returned = 0u32;
            let status = GetTokenInformation(
                token,
                TokenElevation,
                &mut elevation as *mut TOKEN_ELEVATION as *mut core::ffi::c_void,
                std::mem::size_of::<TOKEN_ELEVATION>() as u32,
                &mut returned,
            );
            elevated = status != 0 && elevation.TokenIsElevated != 0;
            CloseHandle(token);
        }
        CloseHandle(process);
        elevated
    }
}

#[cfg(target_os = "windows")]
fn focus_window(target: isize) -> Result<(), String> {
    use std::thread;
    use windows_sys::Win32::System::Threading::{AttachThreadInput, GetCurrentThreadId};
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        BringWindowToTop, GetForegroundWindow, GetWindowThreadProcessId, IsIconic,
        SetForegroundWindow, ShowWindow, SW_RESTORE,
    };

    let foreground = unsafe { GetForegroundWindow() };
    if foreground == target {
        return Ok(());
    }

    if unsafe { IsIconic(target) } != 0 {
        unsafe { ShowWindow(target, SW_RESTORE) };
    }

    let target_thread = unsafe { GetWindowThreadProcessId(target, std::ptr::null_mut()) };
    let current_thread = unsafe { GetCurrentThreadId() };
    let foreground_thread = if foreground != 0 {
        let mut foreground_pid = 0u32;
        unsafe { GetWindowThreadProcessId(foreground, &mut foreground_pid) }
    } else {
        0
    };
    let attached_foreground = foreground_thread != 0
        && foreground_thread != current_thread
        && unsafe { AttachThreadInput(current_thread, foreground_thread, 1) } != 0;
    let attached_target = target_thread != 0
        && target_thread != current_thread
        && unsafe { AttachThreadInput(current_thread, target_thread, 1) } != 0;

    unsafe {
        BringWindowToTop(target);
        SetForegroundWindow(target);
    }
    thread::sleep(Duration::from_millis(100));
    let focused = unsafe { GetForegroundWindow() == target };

    if attached_target {
        unsafe { AttachThreadInput(current_thread, target_thread, 0) };
    }
    if attached_foreground {
        unsafe { AttachThreadInput(current_thread, foreground_thread, 0) };
    }

    if !focused {
        return Err("Windows did not activate the target app. Bring it to the foreground and retry.".to_string());
    }
    Ok(())
}

#[tauri::command]
fn start_window_drag(window: tauri::Window) -> Result<(), String> {
    #[cfg(not(any(target_os = "android", target_os = "ios")))]
    {
        window.start_dragging().map_err(|e| e.to_string())
    }
    #[cfg(any(target_os = "android", target_os = "ios"))]
    {
        let _ = window;
        Ok(())
    }
}

#[cfg(target_os = "windows")]
fn position_top_notch(window: &tauri::WebviewWindow) {
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        GetSystemMetrics, SetWindowPos, SM_CXSCREEN, SWP_NOACTIVATE, SWP_NOZORDER, SWP_SHOWWINDOW, SWP_FRAMECHANGED
    };
    use windows_sys::Win32::Graphics::Gdi::{
        GetMonitorInfoW, MonitorFromWindow, MONITOR_DEFAULTTONEAREST, MONITORINFO
    };

    if let Ok(hwnd) = window.hwnd() {
        unsafe {
            let mut info: MONITORINFO = std::mem::zeroed();
            info.cbSize = std::mem::size_of::<MONITORINFO>() as u32;
            let hmon = MonitorFromWindow(hwnd.0 as isize, MONITOR_DEFAULTTONEAREST);
            let (mon_x, mon_w, mon_top) = if hmon != 0 && GetMonitorInfoW(hmon, &mut info) != 0 {
                (info.rcMonitor.left, info.rcMonitor.right - info.rcMonitor.left, info.rcMonitor.top)
            } else {
                (0, GetSystemMetrics(SM_CXSCREEN), 0)
            };

            let monitor = window.current_monitor().ok().flatten().or_else(|| window.primary_monitor().ok().flatten());
            let scale = monitor.as_ref().map(|m| m.scale_factor()).unwrap_or(1.0);
            let phys_w = (270.0 * scale).round() as i32;
            let phys_h = (58.0 * scale).round() as i32;

            let x = mon_x + (mon_w - phys_w) / 2;
            let y = mon_top;

            SetWindowPos(
                hwnd.0 as isize,
                0,
                x,
                y,
                phys_w,
                phys_h,
                SWP_NOACTIVATE | SWP_NOZORDER | SWP_SHOWWINDOW | SWP_FRAMECHANGED,
            );
        }
    }
}

#[cfg(not(target_os = "windows"))]
fn position_top_notch(_window: &tauri::WebviewWindow) {}

#[tauri::command]
fn center_top_notch(app_handle: tauri::AppHandle) -> Result<(), String> {
    if let Some(window) = app_handle.get_webview_window("floating_mic") {
        #[cfg(target_os = "windows")]
        position_top_notch(&window);
    }
    Ok(())
}

#[tauri::command]
fn open_floating_mic(app_handle: tauri::AppHandle) -> Result<(), String> {
    #[cfg(target_os = "windows")]
    remember_foreground_external_window();
    if let Some(window) = app_handle.get_webview_window("floating_mic") {
        position_top_notch(&window);
        let _ = window.show();
        let _ = apply_pill_window_shape(&window);
    }
    Ok(())
}

#[tauri::command]
fn close_floating_mic(app_handle: tauri::AppHandle) -> Result<(), String> {
    if let Some(window) = app_handle.get_webview_window("floating_mic") {
        let _ = window.hide();
    }
    Ok(())
}

#[tauri::command]
fn toggle_floating_mic(app_handle: tauri::AppHandle) -> Result<(), String> {
    if let Some(window) = app_handle.get_webview_window("floating_mic") {
        if window.is_visible().unwrap_or(false) {
            let _ = window.hide();
        } else {
            #[cfg(target_os = "windows")]
            remember_foreground_external_window();
            position_top_notch(&window);
            let _ = window.show();
            let _ = apply_pill_window_shape(&window);
        }
    }
    Ok(())
}

#[cfg(target_os = "windows")]
fn apply_pill_window_shape(window: &tauri::WebviewWindow) -> Result<(), String> {
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        GetWindowLongPtrW, SetWindowLongPtrW, SetWindowPos,
        GWL_STYLE, GWL_EXSTYLE,
        WS_CAPTION, WS_THICKFRAME, WS_MINIMIZEBOX, WS_MAXIMIZEBOX, WS_SYSMENU, WS_BORDER, WS_DLGFRAME,
        WS_POPUP, WS_VISIBLE,
        WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW, WS_EX_TOPMOST,
        SWP_NOMOVE, SWP_NOSIZE, SWP_NOZORDER, SWP_NOACTIVATE, SWP_FRAMECHANGED,
    };

    let _ = window.set_decorations(false);
    let _ = window.set_shadow(false);

    let hwnd = window.hwnd().map_err(|e| e.to_string())?;

    unsafe {
        // Strip all titlebar, borders, system menu, min/max/close controls and set WS_POPUP
        let style = GetWindowLongPtrW(hwnd.0 as isize, GWL_STYLE);
        let unwanted_styles = (WS_CAPTION | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU | WS_BORDER | WS_DLGFRAME) as isize;
        let new_style = (style & !unwanted_styles) | (WS_POPUP as isize) | (WS_VISIBLE as isize);
        SetWindowLongPtrW(hwnd.0 as isize, GWL_STYLE, new_style);

        // Add WS_EX_NOACTIVATE and WS_EX_TOOLWINDOW so it never steals focus and suppresses titlebars completely
        let ex_style = GetWindowLongPtrW(hwnd.0 as isize, GWL_EXSTYLE);
        let new_ex_style = ex_style | (WS_EX_NOACTIVATE as isize) | (WS_EX_TOOLWINDOW as isize) | (WS_EX_TOPMOST as isize);
        SetWindowLongPtrW(hwnd.0 as isize, GWL_EXSTYLE, new_ex_style);

        // Crucial: SWP_FRAMECHANGED forces Windows DWM to recalculate the frame and discard the title bar completely
        SetWindowPos(
            hwnd.0 as _,
            0,
            0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
        );
    }

    Ok(())
}

#[cfg(not(target_os = "windows"))]
fn apply_pill_window_shape(_window: &tauri::WebviewWindow) -> Result<(), String> {
    Ok(())
}

/// Makes an overlay window chrome-proof on Windows: strips any caption/frame
/// styles, opts out of Windows 11 automatic corner rounding, and disables the
/// DWM system backdrop (Mica/Acrylic). Without this, transparent overlay
/// windows can show an opaque white band or stray title-bar fragments.
#[cfg(target_os = "windows")]
fn harden_overlay_window(window: &tauri::WebviewWindow) {
    use windows_sys::Win32::Graphics::Dwm::{
        DwmSetWindowAttribute, DWMWA_SYSTEMBACKDROP_TYPE, DWMWA_WINDOW_CORNER_PREFERENCE,
        DWMWCP_DONOTROUND,
    };
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        GetWindowLongPtrW, SetWindowLongPtrW, GWL_STYLE, WS_CAPTION, WS_THICKFRAME,
    };

    let Ok(hwnd) = window.hwnd() else { return };
    let hwnd = hwnd.0 as isize;
    unsafe {
        // Strip title bar and thick frame in case any style ever leaks in.
        let style = GetWindowLongPtrW(hwnd, GWL_STYLE);
        SetWindowLongPtrW(hwnd, GWL_STYLE, style & !((WS_CAPTION | WS_THICKFRAME) as isize));

        // Opt out of Windows 11 DWM corner rounding (draws opaque corners on
        // transparent windows).
        let corner_preference: u32 = DWMWCP_DONOTROUND as u32;
        let _ = DwmSetWindowAttribute(
            hwnd,
            DWMWA_WINDOW_CORNER_PREFERENCE as u32,
            &corner_preference as *const u32 as *const core::ffi::c_void,
            std::mem::size_of::<u32>() as u32,
        );

        // Disable the system backdrop (Mica/Acrylic renders an opaque layer
        // behind transparent windows on Windows 11 22H2+). DWMSBT_NONE = 1.
        let backdrop: u32 = 1;
        let _ = DwmSetWindowAttribute(
            hwnd,
            DWMWA_SYSTEMBACKDROP_TYPE as u32,
            &backdrop as *const u32 as *const core::ffi::c_void,
            std::mem::size_of::<u32>() as u32,
        );
    }
}

#[cfg(not(target_os = "windows"))]
fn harden_overlay_window(_window: &tauri::WebviewWindow) {}

/// Forces the WebView2 surface itself to be transparent. `transparent: true`
/// normally handles this, but on some WebView2 runtime builds the handshake is
/// missed and the webview paints an opaque white background — which shows as
/// light square corners around the rounded pill.
#[cfg(target_os = "windows")]
fn force_transparent_webview(window: &tauri::WebviewWindow) {
    use webview2_com::Microsoft::Web::WebView2::Win32::{COREWEBVIEW2_COLOR, ICoreWebView2Controller2};
    use windows_core61::Interface as _;

    let _ = window.with_webview(move |webview| unsafe {
        let controller = webview.controller();
        // The background color lives on the versioned Controller2 interface.
        if let Ok(controller2) = controller.cast::<ICoreWebView2Controller2>() {
            // A = 0 → fully transparent webview background.
            let _ = controller2.SetDefaultBackgroundColor(COREWEBVIEW2_COLOR { A: 0, R: 255, G: 255, B: 255 });
        }
    });
}

#[cfg(not(target_os = "windows"))]
fn force_transparent_webview(_window: &tauri::WebviewWindow) {}

#[cfg(target_os = "windows")]
fn inspect_window_app(hwnd: isize) -> Option<ActiveAppInfo> {
    use windows_sys::Win32::UI::WindowsAndMessaging::GetWindowTextW;
    use windows_sys::Win32::UI::WindowsAndMessaging::GetWindowThreadProcessId;
    use windows_sys::Win32::System::Threading::{OpenProcess, PROCESS_QUERY_LIMITED_INFORMATION, PROCESS_QUERY_INFORMATION};
    use windows_sys::Win32::Foundation::CloseHandle;
    use windows_sys::Win32::System::ProcessStatus::{K32GetModuleBaseNameW, K32GetProcessImageFileNameW};

    if hwnd == 0 {
        return None;
    }

    let mut pid = 0u32;
    unsafe { GetWindowThreadProcessId(hwnd as _, &mut pid) };
    if pid == 0 {
        return None;
    }

    let mut process_name = String::new();
    unsafe {
        let mut handle = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid);
        if handle == 0 {
            handle = OpenProcess(PROCESS_QUERY_INFORMATION, 0, pid);
        }
        if handle != 0 {
            let mut name_buf = [0u16; 512];
            let name_len = K32GetModuleBaseNameW(handle, 0, name_buf.as_mut_ptr(), 512);
            if name_len > 0 {
                process_name = String::from_utf16_lossy(&name_buf[..name_len as usize]);
            } else {
                let img_len = K32GetProcessImageFileNameW(handle, name_buf.as_mut_ptr(), 512);
                if img_len > 0 {
                    let full_path = String::from_utf16_lossy(&name_buf[..img_len as usize]);
                    if let Some(filename) = full_path.split('\\').last() {
                        process_name = filename.to_string();
                    }
                }
            }
            CloseHandle(handle);
        }
    }

    let proc_lower = process_name.to_lowercase();
    if proc_lower.is_empty() {
        return None;
    }

    let mut title_buf = [0u16; 512];
    let len = unsafe { GetWindowTextW(hwnd as _, title_buf.as_mut_ptr(), 512) };
    let _title = if len > 0 {
        String::from_utf16_lossy(&title_buf[..len as usize])
    } else {
        String::new()
    };

    // Exact file-name matching avoids false positives like any process
    // containing "code" (encoders, codecs) being labelled VS Code.
    let known_name = match proc_lower.as_str() {
        "whatsapp.exe" => "WhatsApp Desktop",
        "notepad.exe" | "notepad++.exe" => "Notepad",
        "chrome.exe" => "Google Chrome",
        "msedge.exe" => "Microsoft Edge",
        "code.exe" => "Visual Studio Code",
        "winword.exe" => "Microsoft Word",
        "discord.exe" => "Discord",
        "slack.exe" => "Slack",
        "obsidian.exe" => "Obsidian",
        "telegram.exe" => "Telegram",
        _ => "",
    };

    let friendly_name = if !known_name.is_empty() {
        known_name.to_string()
    } else {
        let base = process_name.replace(".exe", "");
        let mut c = base.chars();
        match c.next() {
            None => String::new(),
            Some(f) => f.to_uppercase().collect::<String>() + c.as_str(),
        }
    };

    Some(ActiveAppInfo {
        app_name: friendly_name,
        process_name,
    })
}

#[derive(Serialize, Clone, Debug)]
pub struct ActiveAppContext {
    pub app_name: String,
    pub process_name: String,
    pub surrounding_text: String,
}

fn extract_focused_surrounding_text() -> String {
    #[cfg(target_os = "windows")]
    {
        use windows::core::Interface;
        use windows::Win32::System::Com::{CoCreateInstance, CoInitializeEx, CoUninitialize, CLSCTX_INPROC_SERVER, COINIT_APARTMENTTHREADED};
        use windows::Win32::UI::Accessibility::{
            CUIAutomation, IUIAutomation, IUIAutomationTextPattern, IUIAutomationTextPattern2,
            IUIAutomationValuePattern, TextPatternRangeEndpoint_Start, TextUnit_Character,
            UIA_TextPatternId, UIA_ValuePatternId,
        };

        unsafe {
            // Only balance with CoUninitialize when this call actually initialized COM;
            // RPC_E_CHANGED_MODE means COM was already initialized on another model.
            let com_initialized = CoInitializeEx(None, COINIT_APARTMENTTHREADED).is_ok();
            let mut extracted = String::new();

            if let Ok(automation) = CoCreateInstance::<_, IUIAutomation>(&CUIAutomation, None, CLSCTX_INPROC_SERVER) {
                if let Ok(element) = automation.GetFocusedElement() {
                    let mut context = String::new();

                    if let Ok(pattern) = element.GetCurrentPattern(UIA_TextPatternId) {
                        // Prefer text immediately BEFORE the caret (IUIAutomationTextPattern2,
                        // Windows 8+). Voice commands and tone detection need caret-relative
                        // context; document-start text would erase the wrong range.
                        if let Ok(pattern2) = pattern.cast::<IUIAutomationTextPattern2>() {
                            if let Ok(caret_range) = pattern2.GetCaretRange(std::ptr::null_mut()) {
                                if let Ok(range_copy) = caret_range.Clone() {
                                    let _ = range_copy.MoveEndpointByUnit(
                                        TextPatternRangeEndpoint_Start,
                                        TextUnit_Character,
                                        -(MAX_SURROUNDING_TEXT_LEN as i32),
                                    );
                                    if let Ok(bstr) = range_copy.GetText(MAX_SURROUNDING_TEXT_LEN as i32) {
                                        context = bstr.to_string();
                                    }
                                }
                            }
                        }

                        if context.trim().is_empty() {
                            if let Ok(text_pattern) = pattern.cast::<IUIAutomationTextPattern>() {
                                if let Ok(range) = text_pattern.DocumentRange() {
                                    if let Ok(bstr) = range.GetText(MAX_SURROUNDING_TEXT_LEN as i32) {
                                        context = bstr.to_string();
                                    }
                                }
                            }
                        }
                    }

                    if !context.trim().is_empty() {
                        extracted = context;
                    } else if let Ok(pattern) = element.GetCurrentPattern(UIA_ValuePatternId) {
                        if let Ok(val_pattern) = pattern.cast::<IUIAutomationValuePattern>() {
                            if let Ok(bstr) = val_pattern.CurrentValue() {
                                extracted = bstr.to_string();
                            }
                        }
                    }
                }
            }

            if com_initialized {
                CoUninitialize();
            }
            extracted.trim().to_string()
        }
    }
    #[cfg(not(target_os = "windows"))]
    String::new()
}

#[tauri::command]
fn get_active_app_info() -> Result<ActiveAppInfo, String> {
    #[cfg(target_os = "windows")]
    {
        if let Ok(guard) = LAST_ACTIVE_APP.lock() {
            if let Some(app) = guard.clone() {
                return Ok(app);
            }
        }
    }
    Ok(ActiveAppInfo {
        app_name: "Active App".to_string(),
        process_name: "app.exe".to_string(),
    })
}

#[tauri::command]
fn get_active_app_context() -> Result<ActiveAppContext, String> {
    #[cfg(target_os = "windows")]
    let (app_name, process_name) = {
        if let Ok(guard) = LAST_ACTIVE_APP.lock() {
            if let Some(app) = guard.clone() {
                (app.app_name, app.process_name)
            } else {
                ("Active App".to_string(), "app.exe".to_string())
            }
        } else {
            ("Active App".to_string(), "app.exe".to_string())
        }
    };

    #[cfg(not(target_os = "windows"))]
    let (app_name, process_name) = ("Active App".to_string(), "app.exe".to_string());

    let raw_surrounding = extract_focused_surrounding_text();
    // Truncate and strip control characters before sending to frontend
    let surrounding_text: String = raw_surrounding
        .chars()
        .filter(|c| !c.is_control() || *c == '\n' || *c == '\t')
        .take(MAX_SURROUNDING_TEXT_LEN)
        .collect();

    Ok(ActiveAppContext {
        app_name,
        process_name,
        surrounding_text,
    })
}

#[tauri::command]
fn inject_text(text: String) -> Result<InjectionOutcome, String> {
    if text.trim().is_empty() {
        return Err("inject_text: text must not be empty or whitespace-only".to_string());
    }
    erase_and_inject(0, text, Some(true))
}

fn snapshot(document: &DocumentState) -> DocumentSnapshot {
    DocumentSnapshot { text: document.text.clone(), cursor: byte_index_to_utf16(&document.text, document.cursor), version: document.version, can_undo: !document.undo.is_empty(), can_redo: !document.redo.is_empty() }
}

/// Convert the JavaScript-facing UTF-16 string offset to a valid Rust byte offset.
fn utf16_index_to_byte(text: &str, target: usize) -> Result<usize, String> {
    let mut utf16_offset = 0;
    for (byte_offset, ch) in text.char_indices() {
        if utf16_offset == target {
            return Ok(byte_offset);
        }
        utf16_offset += ch.len_utf16();
        if utf16_offset > target {
            return Err("edit position splits a UTF-16 character".to_string());
        }
    }
    if utf16_offset == target {
        Ok(text.len())
    } else {
        Err("edit position is out of bounds".to_string())
    }
}

/// Convert an internal Rust byte cursor to the UTF-16 offset expected by JavaScript.
fn byte_index_to_utf16(text: &str, byte_index: usize) -> usize {
    let bounded = byte_index.min(text.len());
    text.char_indices()
        .take_while(|(offset, _)| *offset < bounded)
        .map(|(_, ch)| ch.len_utf16())
        .sum()
}

#[cfg(target_os = "windows")]
fn remember_foreground_external_window() {
    use windows_sys::Win32::System::Threading::GetCurrentProcessId;
    use windows_sys::Win32::UI::WindowsAndMessaging::{GetForegroundWindow, GetWindowThreadProcessId};

    unsafe {
        let hwnd = GetForegroundWindow();
        if hwnd == 0 {
            return;
        }
        let mut process_id = 0u32;
        GetWindowThreadProcessId(hwnd, &mut process_id);
        if process_id == 0 || process_id == GetCurrentProcessId() {
            return;
        }

        // Injection only needs the HWND and PID. Process-name inspection is
        // best-effort because protected/UWP apps can deny query access.
        LAST_ACTIVE_WINDOW_PID.store(process_id, std::sync::atomic::Ordering::Release);
        LAST_ACTIVE_WINDOW.store(hwnd as isize, std::sync::atomic::Ordering::Release);
        if let Some(info) = inspect_window_app(hwnd as isize) {
            if !info.process_name.to_lowercase().contains("kritix") {
                if let Ok(mut guard) = LAST_ACTIVE_APP.lock() {
                    *guard = Some(info);
                }
            }
        }
    }
}

#[cfg(target_os = "windows")]
fn start_active_app_tracker() {
    std::thread::spawn(|| loop {
        remember_foreground_external_window();
        std::thread::sleep(std::time::Duration::from_millis(75));
    });
}

#[cfg(target_os = "windows")]
fn start_global_hotkey_listener(app_handle: tauri::AppHandle) {
    let _ = APP_HANDLE_FOR_HOTKEY.set(app_handle);

    #[cfg(target_os = "windows")]
    {
        std::thread::spawn(|| {
            use windows_sys::Win32::UI::WindowsAndMessaging::{
                SetWindowsHookExW, UnhookWindowsHookEx, CallNextHookEx, GetMessageW,
                WH_KEYBOARD_LL, WM_KEYDOWN, WM_SYSKEYDOWN, WM_KEYUP, WM_SYSKEYUP, KBDLLHOOKSTRUCT, MSG
            };
            use windows_sys::Win32::UI::Input::KeyboardAndMouse::{
                VK_LCONTROL, VK_RCONTROL, VK_LMENU, VK_RMENU, VK_LSHIFT, VK_RSHIFT, VK_OEM_3,
            };
            use windows_sys::Win32::Foundation::HINSTANCE;
            use std::sync::atomic::Ordering;

            const LLKHF_INJECTED: u32 = 0x10;

            unsafe extern "system" fn hook_proc(code: i32, wparam: usize, lparam: isize) -> isize {
                if code >= 0 && lparam != 0 {
                    let is_down = wparam == WM_KEYDOWN as usize || wparam == WM_SYSKEYDOWN as usize;
                    let is_up = wparam == WM_KEYUP as usize || wparam == WM_SYSKEYUP as usize;

                    if is_down || is_up {
                        let kbd = *(lparam as *const KBDLLHOOKSTRUCT);

                        // Never track synthetic input: our own Ctrl+V paste injection
                        // would corrupt the physical modifier state.
                        if kbd.flags & LLKHF_INJECTED == 0 {
                            // Modifiers are tracked only to suppress the voice key
                            // when it appears inside a shortcut or character chord.
                            if kbd.vkCode == VK_LCONTROL as u32 {
                                IS_CTRL_L_HELD.store(is_down, Ordering::SeqCst);
                            } else if kbd.vkCode == VK_RCONTROL as u32 {
                                IS_CTRL_R_HELD.store(is_down, Ordering::SeqCst);
                            } else if kbd.vkCode == VK_LMENU as u32 {
                                IS_ALT_L_HELD.store(is_down, Ordering::SeqCst);
                                if !is_down && !IS_ALT_R_HELD.load(Ordering::SeqCst) {
                                    hotkey_alt_released();
                                }
                            } else if kbd.vkCode == VK_RMENU as u32 {
                                IS_ALT_R_HELD.store(is_down, Ordering::SeqCst);
                                if !is_down && !IS_ALT_L_HELD.load(Ordering::SeqCst) {
                                    hotkey_alt_released();
                                }
                            } else if kbd.vkCode == VK_LSHIFT as u32 {
                                IS_SHIFT_L_HELD.store(is_down, Ordering::SeqCst);
                            } else if kbd.vkCode == VK_RSHIFT as u32 {
                                IS_SHIFT_R_HELD.store(is_down, Ordering::SeqCst);
                            }

                            if kbd.vkCode == VK_OEM_3 as u32 {
                                // Key repeat sends WM_KEYDOWN continuously while
                                // held; the state machine ignores repeats in the
                                // Held state.
                                if is_down {
                                    hotkey_key_start_or_tap();
                                } else {
                                    hotkey_key_release();
                                }
                            }
                        }
                    }
                }

                CallNextHookEx(0, code, wparam, lparam)
            }

            unsafe {
                let hook = SetWindowsHookExW(WH_KEYBOARD_LL, Some(hook_proc), 0 as HINSTANCE, 0);
                if hook != 0 {
                    let mut msg: MSG = std::mem::zeroed();
                    while GetMessageW(&mut msg, 0, 0, 0) > 0 {}
                    UnhookWindowsHookEx(hook);
                }
            }
        });
    }
}

/// Called when the Alt key is physically released while in a hotkey interaction.
#[cfg(target_os = "windows")]
fn hotkey_alt_released() {
    use std::sync::atomic::Ordering;
    let state = HOTKEY_STATE.load(Ordering::SeqCst);
    if state == HOTKEY_STATE_HELD {
        hotkey_key_release();
    } else if state == HOTKEY_STATE_CONTINUOUS_WAIT_RELEASE {
        HOTKEY_STATE.store(HOTKEY_STATE_CONTINUOUS, Ordering::SeqCst);
    }
}

/// Voice-key combo (Alt + `) down: begins push-to-talk, or (within the double-tap window)
/// switches the running session into continuous listening. Plain ` is ignored and
/// passed through normally to apps when Alt is not held.
#[cfg(target_os = "windows")]
fn hotkey_key_start_or_tap() {
    use std::sync::atomic::Ordering;

    if !HOTKEY_ENABLED.load(Ordering::SeqCst) {
        return;
    }

    let is_alt = IS_ALT_L_HELD.load(Ordering::SeqCst) || IS_ALT_R_HELD.load(Ordering::SeqCst);
    let other_modifier = IS_CTRL_L_HELD.load(Ordering::SeqCst)
        || IS_CTRL_R_HELD.load(Ordering::SeqCst)
        || IS_SHIFT_L_HELD.load(Ordering::SeqCst)
        || IS_SHIFT_R_HELD.load(Ordering::SeqCst);

    // Require Alt to be held, and forbid other modifiers (Ctrl, Shift)
    if !is_alt || other_modifier {
        return;
    }

    match HOTKEY_STATE.load(Ordering::SeqCst) {
        HOTKEY_STATE_IDLE => {
            HOTKEY_DOWN_MS.store(inject_clock_ms(), Ordering::SeqCst);
            HOTKEY_EVENT_GENERATION.fetch_add(1, Ordering::SeqCst);
            HOTKEY_STATE.store(HOTKEY_STATE_HELD, Ordering::SeqCst);
            begin_push_to_talk();
        }
        HOTKEY_STATE_WAIT_SECOND_TAP => {
            // Double tap → continuous listening; the microphone is already
            // running, so just cancel the pending single-tap stop timer.
            HOTKEY_EVENT_GENERATION.fetch_add(1, Ordering::SeqCst);
            HOTKEY_STATE.store(HOTKEY_STATE_CONTINUOUS_WAIT_RELEASE, Ordering::SeqCst);
            notify_push_to_talk_mode("continuous");
        }
        HOTKEY_STATE_HELD => {
            // Key repeat while already held — ignore.
        }
        HOTKEY_STATE_CONTINUOUS_WAIT_RELEASE => {
            // Key repeat during the second tap of double-tap — ignore.
        }
        HOTKEY_STATE_CONTINUOUS => {
            // A tap begins inside continuous mode; the stop decision happens
            // on release.
            HOTKEY_DOWN_MS.store(inject_clock_ms(), Ordering::SeqCst);
        }
        _ => {}
    }
}

/// Voice-key (`) up: a long hold releases push-to-talk; a quick tap either
/// waits for a possible double-tap or stops the continuous session.
#[cfg(target_os = "windows")]
fn hotkey_key_release() {
    use std::sync::atomic::Ordering;

    match HOTKEY_STATE.load(Ordering::SeqCst) {
        HOTKEY_STATE_HELD => {
            let held_ms = inject_clock_ms().saturating_sub(HOTKEY_DOWN_MS.load(Ordering::SeqCst));
            if held_ms >= HOTKEY_HOLD_MS {
                // Plain push-to-talk: release stops the microphone.
                HOTKEY_STATE.store(HOTKEY_STATE_IDLE, Ordering::SeqCst);
                HOTKEY_EVENT_GENERATION.fetch_add(1, Ordering::SeqCst);
                end_push_to_talk();
            } else {
                // Quick tap — wait briefly for a second press (double-tap means
                // "keep listening continuously"); otherwise stop.
                let generation = HOTKEY_EVENT_GENERATION.fetch_add(1, Ordering::SeqCst) + 1;
                HOTKEY_STATE.store(HOTKEY_STATE_WAIT_SECOND_TAP, Ordering::SeqCst);
                schedule_hotkey_double_tap_timeout(generation);
            }
        }
        HOTKEY_STATE_CONTINUOUS_WAIT_RELEASE => {
            // Releasing the second tap of double-tap engages hands-free continuous mode.
            HOTKEY_STATE.store(HOTKEY_STATE_CONTINUOUS, Ordering::SeqCst);
        }
        HOTKEY_STATE_CONTINUOUS => {
            // A tap inside continuous mode stops listening.
            HOTKEY_STATE.store(HOTKEY_STATE_IDLE, Ordering::SeqCst);
            HOTKEY_EVENT_GENERATION.fetch_add(1, Ordering::SeqCst);
            end_push_to_talk();
        }
        _ => {}
    }
}

/// After a single quick tap, wait for a possible second press. If none arrives
/// within the window, the tap was a plain toggle-off → stop listening.
#[cfg(target_os = "windows")]
fn schedule_hotkey_double_tap_timeout(generation: u64) {
    std::thread::spawn(move || {
        std::thread::sleep(Duration::from_millis(HOTKEY_TAP_WINDOW_MS));
        use std::sync::atomic::Ordering;
        if HOTKEY_EVENT_GENERATION.load(Ordering::SeqCst) == generation
            && HOTKEY_STATE.load(Ordering::SeqCst) == HOTKEY_STATE_WAIT_SECOND_TAP
        {
            HOTKEY_STATE.store(HOTKEY_STATE_IDLE, Ordering::SeqCst);
            end_push_to_talk();
        }
    });
}

// Lock-free OnceLock read: the low-level keyboard hook must return fast or
// Windows silently removes it.
#[cfg(target_os = "windows")]
fn begin_push_to_talk() {
    if let Some(handle) = APP_HANDLE_FOR_HOTKEY.get().cloned() {
        let _ = handle.clone().run_on_main_thread(move || {
            let _ = handle.emit("push_to_talk_start", ());
        });
    }
}

#[cfg(target_os = "windows")]
fn end_push_to_talk() {
    if let Some(handle) = APP_HANDLE_FOR_HOTKEY.get().cloned() {
        let _ = handle.clone().run_on_main_thread(move || {
            let _ = handle.emit("push_to_talk_stop", ());
        });
    }
}

#[cfg(target_os = "windows")]
fn notify_push_to_talk_mode(mode: &'static str) {
    if let Some(handle) = APP_HANDLE_FOR_HOTKEY.get().cloned() {
        let _ = handle.emit("push_to_talk_mode", mode);
    }
}

#[tauri::command]
fn set_hotkey_enabled(enabled: bool) {
    HOTKEY_ENABLED.store(enabled, std::sync::atomic::Ordering::SeqCst);
    #[cfg(target_os = "windows")]
    {
        use std::sync::atomic::Ordering;
        // Disabling the hotkey mid-listening must release the microphone too.
        if !enabled && HOTKEY_STATE.load(Ordering::SeqCst) != HOTKEY_STATE_IDLE {
            HOTKEY_EVENT_GENERATION.fetch_add(1, Ordering::SeqCst);
            HOTKEY_STATE.store(HOTKEY_STATE_IDLE, Ordering::SeqCst);
            end_push_to_talk();
        }
    }
}

#[tauri::command]
fn reset_hotkey_state() {
    #[cfg(target_os = "windows")]
    {
        use std::sync::atomic::Ordering;
        HOTKEY_EVENT_GENERATION.fetch_add(1, Ordering::SeqCst);
        HOTKEY_STATE.store(HOTKEY_STATE_IDLE, Ordering::SeqCst);
    }
}

/// All spawned Python children join a job object that is killed when the app
/// exits, so service/downloader processes never outlive KVIE or squat on port
/// 8765 after quit.
#[cfg(target_os = "windows")]
fn confine_process_to_app_job(child: &std::process::Child) {
    use std::os::windows::io::AsRawHandle;
    use windows_sys::Win32::System::JobObjects::{
        AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
        SetInformationJobObject,
    };

    let job = *APP_CHILD_JOB.get_or_init(|| unsafe {
        let job = CreateJobObjectW(std::ptr::null(), std::ptr::null());
        if job != 0 {
            let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            SetInformationJobObject(
                job,
                JobObjectExtendedLimitInformation,
                &info as *const _ as *const core::ffi::c_void,
                std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
            );
        }
        job
    });
    if job != 0 {
        unsafe {
            let _ = AssignProcessToJobObject(job as _, child.as_raw_handle() as _);
        }
    }
}

#[cfg(not(any(target_os = "android", target_os = "ios")))]
fn setup_system_tray(app: &mut tauri::App) -> Result<(), String> {
    let open_i = MenuItem::with_id(app, "open", "Open KVIE Workspace", true, None::<&str>).map_err(|e| e.to_string())?;
    let floating_i = MenuItem::with_id(app, "toggle_floating", "Toggle Floating Mic", true, None::<&str>).map_err(|e| e.to_string())?;
    let toggle_mic_i = MenuItem::with_id(app, "toggle_mic", "Toggle Mic", true, None::<&str>).map_err(|e| e.to_string())?;
    let quit_i = MenuItem::with_id(app, "quit", "Exit Kritix", true, None::<&str>).map_err(|e| e.to_string())?;

    let menu = Menu::with_items(app, &[&open_i, &floating_i, &toggle_mic_i, &quit_i]).map_err(|e| e.to_string())?;

    let mut builder = TrayIconBuilder::new()
        .menu(&menu)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "open" => {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.show();
                    let _ = window.set_focus();
                }
            }
            "toggle_floating" => {
                if let Some(window) = app.get_webview_window("floating_mic") {
                    if window.is_visible().unwrap_or(false) {
                        let _ = window.hide();
                    } else {
                        position_top_notch(&window);
                        let _ = window.show();
                        let _ = apply_pill_window_shape(&window);
                    }
                }
            }
            "toggle_mic" => {
                let _ = app.emit("toggle_mic_shortcut", ());
            }
            "quit" => {
                app.exit(0);
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                let app = tray.app_handle();
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.show();
                    let _ = window.set_focus();
                }
            }
        });

    if let Some(icon) = app.default_window_icon() {
        builder = builder.icon(icon.clone());
    }

    builder.build(app).map_err(|e| e.to_string())?;
    Ok(())
}

fn get_project_root() -> PathBuf {
    // Installed builds can point KVIE at a checked-out project via this env var.
    if let Ok(from_env) = std::env::var("KVIE_PROJECT_ROOT") {
        let candidate = PathBuf::from(from_env);
        if candidate.join("Backend").exists() {
            return candidate;
        }
    }
    if let Ok(cwd) = std::env::current_dir() {
        if cwd.join("Backend").exists() {
            return cwd;
        }
        if let Some(parent) = cwd.parent() {
            if parent.join("Backend").exists() {
                return parent.to_path_buf();
            }
        }
    }
    if let Ok(exe) = std::env::current_exe() {
        let mut current = exe.as_path();
        while let Some(parent) = current.parent() {
            if parent.join("Backend").exists() {
                return parent.to_path_buf();
            }
            current = parent;
        }
    }
    PathBuf::from(".")
}

fn start_python_service() {
    #[cfg(not(any(target_os = "android", target_os = "ios")))]
    std::thread::spawn(|| {
        let service_ready = || {
            use std::io::{Read, Write};
            let Ok(mut stream) = std::net::TcpStream::connect_timeout(
                &"127.0.0.1:8765".parse().expect("valid loopback address"),
                std::time::Duration::from_millis(250),
            ) else {
                return false;
            };
            let _ = stream.set_read_timeout(Some(std::time::Duration::from_millis(500)));
            let _ = stream.set_write_timeout(Some(std::time::Duration::from_millis(500)));
            if stream.write_all(b"GET /health HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n").is_err() {
                return false;
            }
            let mut response = [0u8; 64];
            let Ok(bytes_read) = stream.read(&mut response) else {
                return false;
            };
            std::str::from_utf8(&response[..bytes_read])
                .ok()
                .is_some_and(|status| status.starts_with("HTTP/1.1 200") || status.starts_with("HTTP/1.0 200"))
        };
        if service_ready() {
            return;
        }

        let root = get_project_root();

        let candidates: Vec<(PathBuf, Vec<&str>)> = {
            let mut paths = Vec::new();
            #[cfg(target_os = "windows")]
            {
                let venv_python = root.join(".venv").join("Scripts").join("python.exe");
                if venv_python.is_file() {
                    paths.push((venv_python, vec!["-m", "Backend.kvie.service"]));
                }
                paths.push((PathBuf::from("python"), vec!["-m", "Backend.kvie.service"]));
                paths.push((PathBuf::from("py"), vec!["-3", "-m", "Backend.kvie.service"]));
                paths.push((PathBuf::from("python3"), vec!["-m", "Backend.kvie.service"]));
            }
            #[cfg(not(target_os = "windows"))]
            {
                let venv_python = root.join(".venv").join("bin").join("python3");
                if venv_python.is_file() {
                    paths.push((venv_python, vec!["-m", "Backend.kvie.service"]));
                }
                paths.push((PathBuf::from("python3"), vec!["-m", "Backend.kvie.service"]));
                paths.push((PathBuf::from("python"), vec!["-m", "Backend.kvie.service"]));
            }
            paths
        };

        for (program, arguments) in candidates {
            let mut cmd = std::process::Command::new(program);
            cmd.args(arguments);
            cmd.current_dir(&root);
            cmd.env("PYTHONPATH", &root);
            #[cfg(target_os = "windows")]
            {
                use std::os::windows::process::CommandExt;
                cmd.creation_flags(0x08000000); // CREATE_NO_WINDOW
            }

            let Ok(mut child) = cmd.spawn() else { continue };
            #[cfg(target_os = "windows")]
            confine_process_to_app_job(&child);
            for _ in 0..75 {
                if service_ready() {
                    return;
                }
                if child.try_wait().ok().flatten().is_some() {
                    break;
                }
                std::thread::sleep(std::time::Duration::from_millis(200));
            }
            // A slow but still starting service can continue; don't launch a duplicate.
            if child.try_wait().ok().flatten().is_none() {
                return;
            }
        }
    });
}

#[tauri::command]
fn download_model_native(app_handle: tauri::AppHandle, model_id: String) -> Result<(), String> {
    #[cfg(any(target_os = "android", target_os = "ios"))]
    {
        let _ = (app_handle, model_id);
        return Err("Desktop model downloads are not available on Android or iOS".into());
    }

    #[cfg(not(any(target_os = "android", target_os = "ios")))]
    {
    std::thread::spawn(move || {
        let normalized = model_id.trim().to_lowercase();

        const ALLOWED_MODELS: &[&str] = &["kritix-stt"];
        if !ALLOWED_MODELS.contains(&normalized.as_str()) {
            let _ = app_handle.emit(
                "model-download-error",
                serde_json::json!({
                    "model_id": normalized,
                    "error": format!("model_id '{}' is not an allowed identifier", model_id),
                }),
            );
            return;
        }

        let root = get_project_root();
        let root_str = root.to_string_lossy().replace('\\', "/");

        let script = r#"import sys, os, json
root = os.environ["__KVIE_ROOT__"]
if root and root not in sys.path:
    sys.path.insert(0, root)
try:
    if os.path.exists(root):
        os.chdir(root)
except Exception:
    pass

from Backend.voice import ModelManager

def on_progress(p):
    print("PROGRESS_JSON:" + json.dumps(p), flush=True)

ModelManager.download_model_stream(os.environ["__MODEL_ID__"], on_progress)
"#;

        #[cfg(target_os = "windows")]
        use std::os::windows::process::CommandExt;

        let spawn_downloader = |program: &std::ffi::OsStr, arguments: &[&str]| {
            let mut cmd = std::process::Command::new(program);
            cmd.args(arguments);
            cmd.current_dir(&root);
            cmd.env("PYTHONPATH", &root);
            cmd.env("PYTHONUNBUFFERED", "1");
            cmd.env("__KVIE_ROOT__", &root_str);
            cmd.env("__MODEL_ID__", &normalized);
            cmd.stdout(std::process::Stdio::piped());
            cmd.stderr(std::process::Stdio::null());
            #[cfg(target_os = "windows")]
            cmd.creation_flags(0x08000000);
            cmd.spawn()
        };

        #[cfg(target_os = "windows")]
        let child_result = {
            let venv_python = root.join(".venv").join("Scripts").join("python.exe");
            let local_result = if venv_python.is_file() {
                spawn_downloader(venv_python.as_os_str(), &["-u", "-c", script])
            } else {
                Err(std::io::Error::new(std::io::ErrorKind::NotFound, "project Python environment is missing"))
            };
            local_result
                .or_else(|_| spawn_downloader(std::ffi::OsStr::new("python"), &["-u", "-c", script]))
                .or_else(|_| spawn_downloader(std::ffi::OsStr::new("py"), &["-3", "-u", "-c", script]))
                .or_else(|_| spawn_downloader(std::ffi::OsStr::new("python3"), &["-u", "-c", script]))
        };
        #[cfg(not(target_os = "windows"))]
        let child_result = {
            let venv_python = root.join(".venv").join("bin").join("python3");
            let local_result = if venv_python.is_file() {
                spawn_downloader(venv_python.as_os_str(), &["-u", "-c", script])
            } else {
                Err(std::io::Error::new(std::io::ErrorKind::NotFound, "project Python environment is missing"))
            };
            local_result
                .or_else(|_| spawn_downloader(std::ffi::OsStr::new("python3"), &["-u", "-c", script]))
                .or_else(|_| spawn_downloader(std::ffi::OsStr::new("python"), &["-u", "-c", script]))
        };

        match child_result {
            Ok(mut child) => {
                #[cfg(target_os = "windows")]
                confine_process_to_app_job(&child);
                if let Some(stdout) = child.stdout.take() {
                    use std::io::{BufRead, BufReader};
                    let reader = BufReader::new(stdout);
                    for line in reader.lines().filter_map(|l| l.ok()) {
                        if let Some(json_str) = line.strip_prefix("PROGRESS_JSON:") {
                            let _ = app_handle.emit("model-download-progress", json_str.to_string());
                        }
                    }
                }
                if !child.wait().map(|status| status.success()).unwrap_or(false) {
                    let _ = app_handle.emit("model-download-error", serde_json::json!({
                        "model_id": normalized,
                        "error": "Model downloader exited unexpectedly",
                    }));
                }
            }
            Err(_) => {
                let _ = app_handle.emit("model-download-error", serde_json::json!({
                    "model_id": normalized,
                    "error": "Could not start the model downloader",
                }));
            }
        }
    });
    Ok(())
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    #[cfg(target_os = "windows")]
    start_active_app_tracker();
    start_python_service();

    tauri::Builder::default()
        .setup(|app| {
            // A read-only %APPDATA% or full disk must not hard-crash the app:
            // degrade to a temp-path database instead of failing the build.
            let data_dir = app.path().app_data_dir().unwrap_or_else(|_| std::env::temp_dir());
            let _ = std::fs::create_dir_all(&data_dir);
            let db_path = data_dir.join("kvie.sqlite3");
            let document = match initialize_database(&db_path) {
                Ok(()) => load_document(&db_path).unwrap_or_default(),
                Err(error) => {
                    eprintln!("KVIE: database init failed, document persistence degraded: {error}");
                    Default::default()
                }
            };
            app.manage(KvieState { document: Mutex::new(document), db_path });
            #[cfg(target_os = "windows")]
            start_global_hotkey_listener(app.handle().clone());
            if let Some(window) = app.get_webview_window("floating_mic") {
                position_top_notch(&window);
                let _ = apply_pill_window_shape(&window);
                harden_overlay_window(&window);
                force_transparent_webview(&window);
                // The window is created hidden (visible:false in the config) so
                // the decorated "KVIE Mic" title bar and default background can
                // never flash on screen — show it only once fully stripped.
                let _ = window.show();
            }
            #[cfg(not(any(target_os = "android", target_os = "ios")))]
            setup_system_tray(app)?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            runtime_status,
            get_document,
            apply_document_edit,
            undo_document,
            redo_document,
            inject_text,
            erase_and_inject,
            start_window_drag,
            open_floating_mic,
            close_floating_mic,
            toggle_floating_mic,
            center_top_notch,
            get_active_app_info,
            get_active_app_context,
            set_hotkey_enabled,
            reset_hotkey_state,
            download_model_native
        ])
        .build(tauri::generate_context!())
        .expect("error while building Kritix")
        .run(|app_handle, event| match event {
            tauri::RunEvent::WindowEvent { label, event: tauri::WindowEvent::CloseRequested { api, .. }, .. } => {
                if label == "main" {
                    api.prevent_close();
                    if let Some(window) = app_handle.get_webview_window("main") {
                        let _ = window.hide();
                    }
                }
            }
            _ => {}
        });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sqlite_round_trip_persists_active_document() {
        let path = std::env::temp_dir().join(format!("kvie-test-{}.sqlite3", chrono_like_now()));
        initialize_database(&path).expect("database should initialize");
        let document = DocumentState { text: "persisted draft".to_string(), cursor: 15, version: 1, ..Default::default() };
        persist_document(&path, &document, "append", "").expect("document should persist");
        let loaded = load_document(&path).expect("document should load");
        assert_eq!(loaded.text, "persisted draft");
        assert_eq!(loaded.version, 1);
        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn empty_injection_is_rejected_before_touching_keyboard() {
        assert!(inject_text("  ".to_string()).is_err());
    }

}
