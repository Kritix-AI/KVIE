use std::path::PathBuf;
use std::sync::Mutex;

use arboard::Clipboard;
use enigo::{Direction, Enigo, Key, Keyboard, Settings};
use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
use tauri::menu::{Menu, MenuItem};
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

static LAST_ACTIVE_APP: Mutex<Option<ActiveAppInfo>> = Mutex::new(None);
static APP_HANDLE_FOR_HOTKEY: Mutex<Option<tauri::AppHandle>> = Mutex::new(None);
static IS_HOTKEY_DOWN: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);

#[derive(Deserialize)]
struct DocumentEdit {
    action: String,
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
    match edit.action.as_str() {
        "append" => {
            if !document.text.is_empty() && !document.text.ends_with(' ') && !document.text.ends_with('\n') { document.text.push(' '); }
            document.text.push_str(content.trim());
            document.cursor = document.text.len();
        }
        "insert" => {
            let position = edit.start.unwrap_or(document.cursor).min(document.text.len());
            document.text.insert_str(position, &content);
            document.cursor = position + content.len();
        }
        "replace" => {
            let start = edit.start.ok_or("replace requires start")?.min(document.text.len());
            let end = edit.end.ok_or("replace requires end")?.min(document.text.len());
            if start > end { return Err("replace start must be <= end".to_string()); }
            document.text.replace_range(start..end, &content);
            document.cursor = start + content.len();
        }
        "clear" => { document.text.clear(); document.cursor = 0; }
        _ => return Err(format!("unsupported document action: {}", edit.action)),
    }
    if before != document.text {
        document.undo.push(before.clone());
        document.redo.clear();
        document.version += 1;
        persist_document(&state.db_path, &document, &edit.action, &before)?;
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
fn erase_and_inject(erase_count: usize, text: String) -> Result<(), String> {
    let mut enigo = Enigo::new(&Settings::default()).map_err(|error| format!("keyboard unavailable: {error}"))?;
    if erase_count > 0 {
        for _ in 0..erase_count {
            let _ = enigo.key(Key::Backspace, Direction::Click);
        }
    }
    if !text.is_empty() {
        if text.len() <= 20 && !text.contains('\n') {
            let _ = enigo.text(&text);
        } else {
            let mut clipboard = Clipboard::new().map_err(|error| format!("clipboard unavailable: {error}"))?;
            clipboard.set_text(&text).map_err(|error| format!("clipboard write failed: {error}"))?;
            enigo.key(Key::Control, Direction::Press).map_err(|error| error.to_string())?;
            enigo.key(Key::Other(0x56), Direction::Click).map_err(|error| error.to_string())?;
            enigo.key(Key::Control, Direction::Release).map_err(|error| error.to_string())?;
        }
    }
    Ok(())
}

#[tauri::command]
fn start_window_drag(window: tauri::Window) -> Result<(), String> {
    window.start_dragging().map_err(|e| e.to_string())
}

#[tauri::command]
fn open_floating_mic(app_handle: tauri::AppHandle) -> Result<(), String> {
    if let Some(window) = app_handle.get_webview_window("floating_mic") {
        let _ = window.show();
        let _ = window.set_focus();
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
            let _ = window.show();
            let _ = window.set_focus();
        }
    }
    Ok(())
}

fn inspect_window_app(hwnd: isize) -> Option<ActiveAppInfo> {
    #[cfg(target_os = "windows")]
    {
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
        let title = if len > 0 {
            String::from_utf16_lossy(&title_buf[..len as usize])
        } else {
            String::new()
        };

        let friendly_name = if proc_lower.contains("whatsapp") {
            "WhatsApp Desktop".to_string()
        } else if proc_lower.contains("notepad") {
            "Notepad".to_string()
        } else if proc_lower.contains("chrome") {
            "Google Chrome".to_string()
        } else if proc_lower.contains("code") {
            "Visual Studio Code".to_string()
        } else if proc_lower.contains("word") || proc_lower.contains("winword") {
            "Microsoft Word".to_string()
        } else if proc_lower.contains("discord") {
            "Discord".to_string()
        } else if proc_lower.contains("slack") {
            "Slack".to_string()
        } else if proc_lower.contains("edge") || proc_lower.contains("msedge") {
            "Microsoft Edge".to_string()
        } else if !title.is_empty() && !proc_lower.contains("kritix") {
            title.clone()
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
    #[cfg(not(target_os = "windows"))]
    None
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
            CUIAutomation, IUIAutomation, IUIAutomationTextPattern, IUIAutomationValuePattern, UIA_TextPatternId, UIA_ValuePatternId,
        };

        unsafe {
            let _ = CoInitializeEx(None, COINIT_APARTMENTTHREADED);
            let mut extracted = String::new();

            if let Ok(automation) = CoCreateInstance::<_, IUIAutomation>(&CUIAutomation, None, CLSCTX_INPROC_SERVER) {
                if let Ok(element) = automation.GetFocusedElement() {
                    if let Ok(pattern) = element.GetCurrentPattern(UIA_TextPatternId) {
                        if let Ok(text_pattern) = pattern.cast::<IUIAutomationTextPattern>() {
                            if let Ok(range) = text_pattern.DocumentRange() {
                                if let Ok(bstr) = range.GetText(500) {
                                    extracted = bstr.to_string();
                                }
                            }
                        }
                    }

                    if extracted.trim().is_empty() {
                        if let Ok(pattern) = element.GetCurrentPattern(UIA_ValuePatternId) {
                            if let Ok(val_pattern) = pattern.cast::<IUIAutomationValuePattern>() {
                                if let Ok(bstr) = val_pattern.CurrentValue() {
                                    extracted = bstr.to_string();
                                }
                            }
                        }
                    }
                }
            }

            CoUninitialize();
            return extracted.trim().to_string();
        }
    }
    #[cfg(not(target_os = "windows"))]
    String::new()
}

#[tauri::command]
fn get_active_app_info() -> Result<ActiveAppInfo, String> {
    if let Ok(guard) = LAST_ACTIVE_APP.lock() {
        if let Some(app) = guard.clone() {
            return Ok(app);
        }
    }
    Ok(ActiveAppInfo {
        app_name: "Active App".to_string(),
        process_name: "app.exe".to_string(),
    })
}

#[tauri::command]
fn get_active_app_context() -> Result<ActiveAppContext, String> {
    let mut app_name = "Active App".to_string();
    let mut process_name = "app.exe".to_string();

    if let Ok(guard) = LAST_ACTIVE_APP.lock() {
        if let Some(app) = guard.clone() {
            app_name = app.app_name;
            process_name = app.process_name;
        }
    }

    let surrounding_text = extract_focused_surrounding_text();

    Ok(ActiveAppContext {
        app_name,
        process_name,
        surrounding_text,
    })
}

#[tauri::command]
fn inject_text(text: String) -> Result<(), String> {
    erase_and_inject(0, text)
}

fn snapshot(document: &DocumentState) -> DocumentSnapshot {
    DocumentSnapshot { text: document.text.clone(), cursor: document.cursor, version: document.version, can_undo: !document.undo.is_empty(), can_redo: !document.redo.is_empty() }
}

fn start_active_app_tracker() {
    #[cfg(target_os = "windows")]
    {
        std::thread::spawn(|| {
            use windows_sys::Win32::UI::WindowsAndMessaging::GetForegroundWindow;

            loop {
                unsafe {
                    let hwnd = GetForegroundWindow();
                    if hwnd != 0 {
                        if let Some(info) = inspect_window_app(hwnd as isize) {
                            let proc_lower = info.process_name.to_lowercase();
                            if !proc_lower.contains("kritix") {
                                if let Ok(mut guard) = LAST_ACTIVE_APP.lock() {
                                    *guard = Some(info);
                                }
                            }
                        }
                    }
                }
                std::thread::sleep(std::time::Duration::from_millis(150));
            }
        });
    }
}

fn start_global_hotkey_listener(app_handle: tauri::AppHandle) {
    if let Ok(mut guard) = APP_HANDLE_FOR_HOTKEY.lock() {
        *guard = Some(app_handle);
    }

    #[cfg(target_os = "windows")]
    {
        std::thread::spawn(|| {
            use windows_sys::Win32::UI::WindowsAndMessaging::{
                SetWindowsHookExW, UnhookWindowsHookEx, CallNextHookEx, GetMessageW,
                WH_KEYBOARD_LL, WM_KEYDOWN, WM_SYSKEYDOWN, WM_KEYUP, WM_SYSKEYUP, KBDLLHOOKSTRUCT, MSG
            };
            use windows_sys::Win32::UI::Input::KeyboardAndMouse::{
                VK_CONTROL, VK_LCONTROL, VK_RCONTROL, VK_MENU, VK_LMENU, VK_RMENU, GetAsyncKeyState
            };
            use windows_sys::Win32::Foundation::HINSTANCE;
            use std::sync::atomic::Ordering;

            unsafe extern "system" fn hook_proc(code: i32, wparam: usize, lparam: isize) -> isize {
                if code >= 0 {
                    let is_down = wparam == WM_KEYDOWN as usize || wparam == WM_SYSKEYDOWN as usize;
                    let is_up = wparam == WM_KEYUP as usize || wparam == WM_SYSKEYUP as usize;
                    
                    if lparam != 0 {
                        let kbd = *(lparam as *const KBDLLHOOKSTRUCT);
                        // 0x52 is Virtual Key Code for 'R'
                        if kbd.vkCode == 0x52 {
                            if is_down {
                                let ctrl_down = (GetAsyncKeyState(VK_CONTROL as i32) as u16 & 0x8000) != 0
                                    || (GetAsyncKeyState(VK_LCONTROL as i32) as u16 & 0x8000) != 0
                                    || (GetAsyncKeyState(VK_RCONTROL as i32) as u16 & 0x8000) != 0;

                                let alt_down = (GetAsyncKeyState(VK_MENU as i32) as u16 & 0x8000) != 0
                                    || (GetAsyncKeyState(VK_LMENU as i32) as u16 & 0x8000) != 0
                                    || (GetAsyncKeyState(VK_RMENU as i32) as u16 & 0x8000) != 0;

                                if ctrl_down && alt_down {
                                    if !IS_HOTKEY_DOWN.swap(true, Ordering::SeqCst) {
                                        if let Ok(guard) = APP_HANDLE_FOR_HOTKEY.lock() {
                                            if let Some(ref handle) = *guard {
                                                let _ = handle.emit("toggle_mic_shortcut", ());
                                            }
                                        }
                                    }
                                }
                            } else if is_up {
                                IS_HOTKEY_DOWN.store(false, Ordering::SeqCst);
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

fn setup_system_tray(app: &mut tauri::App) -> Result<(), String> {
    let open_i = MenuItem::with_id(app, "open", "Open KVIE Workspace", true, None::<&str>).map_err(|e| e.to_string())?;
    let floating_i = MenuItem::with_id(app, "toggle_floating", "Toggle Floating Mic", true, None::<&str>).map_err(|e| e.to_string())?;
    let toggle_mic_i = MenuItem::with_id(app, "toggle_mic", "Toggle Mic (Ctrl+Alt+R)", true, None::<&str>).map_err(|e| e.to_string())?;
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
                        let _ = window.show();
                        let _ = window.set_focus();
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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    start_active_app_tracker();

    tauri::Builder::default()
        .setup(|app| {
            let data_dir = app.path().app_data_dir().map_err(|error| error.to_string())?;
            std::fs::create_dir_all(&data_dir).map_err(|error| error.to_string())?;
            let db_path = data_dir.join("kvie.sqlite3");
            initialize_database(&db_path)?;
            let document = load_document(&db_path)?;
            app.manage(KvieState { document: Mutex::new(document), db_path });
            start_global_hotkey_listener(app.handle().clone());
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
            get_active_app_info,
            get_active_app_context
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
