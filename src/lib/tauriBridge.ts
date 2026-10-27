import { invoke } from '@tauri-apps/api/core'

export interface DocumentSnapshot {
  text: string
  cursor: number
  version: number
  can_undo: boolean
  can_redo: boolean
}

export interface RuntimeStatus {
  desktop: boolean
  stt: string
  storage: string
}

export interface ActiveAppInfo {
  app_name: string
  process_name: string
}

export interface ActiveAppContext {
  app_name: string
  process_name: string
  surrounding_text: string
}

export interface DocumentEdit {
  action: 'append' | 'insert' | 'replace' | 'clear'
  text?: string
  start?: number
  end?: number
}

export interface InjectionOutcome {
  verification: 'verified' | 'unverified' | 'skipped'
}

export const tauriBridge = {
  async runtimeStatus(): Promise<RuntimeStatus> {
    return invoke<RuntimeStatus>('runtime_status')
  },
  async getDocument(): Promise<DocumentSnapshot> {
    return invoke<DocumentSnapshot>('get_document')
  },
  async apply(edit: DocumentEdit): Promise<DocumentSnapshot> {
    return invoke<DocumentSnapshot>('apply_document_edit', { edit })
  },
  async undo(): Promise<DocumentSnapshot> {
    return invoke<DocumentSnapshot>('undo_document')
  },
  async redo(): Promise<DocumentSnapshot> {
    return invoke<DocumentSnapshot>('redo_document')
  },
  async injectText(text: string): Promise<InjectionOutcome> {
    if (!text || text.trim().length === 0) throw new Error('inject_text: text must not be empty')
    if (text.length > 100_000) throw new Error('inject_text: text exceeds maximum length')
    return invoke<InjectionOutcome>('inject_text', { text })
  },
  /**
   * `verify` runs a UIA read-back after the paste to confirm the text landed
   * (adds ~60ms) — use true for finals/commands, false for live interim deltas.
   */
  async eraseAndInject(eraseCount: number, text: string, verify = false): Promise<InjectionOutcome> {
    const safeErase = Math.max(0, Math.min(Math.floor(eraseCount), 500))
    const safeText = text.slice(0, 100_000)
    return invoke<InjectionOutcome>('erase_and_inject', { eraseCount: safeErase, text: safeText, verify })
  },
  async startWindowDrag(): Promise<void> {
    return invoke<void>('start_window_drag')
  },
  async openFloatingMic(): Promise<void> {
    return invoke<void>('open_floating_mic')
  },
  async closeFloatingMic(): Promise<void> {
    return invoke<void>('close_floating_mic')
  },
  async toggleFloatingMic(): Promise<void> {
    return invoke<void>('toggle_floating_mic')
  },
  async centerTopNotch(): Promise<void> {
    return invoke<void>('center_top_notch')
  },
  async getActiveAppInfo(): Promise<ActiveAppInfo> {
    return invoke<ActiveAppInfo>('get_active_app_info')
  },
  async getActiveAppContext(): Promise<ActiveAppContext> {
    return invoke<ActiveAppContext>('get_active_app_context')
  },
  async setHotkeyEnabled(enabled: boolean): Promise<void> {
    return invoke<void>('set_hotkey_enabled', { enabled })
  },
  async resetHotkeyState(): Promise<void> {
    return invoke<void>('reset_hotkey_state')
  },
}
