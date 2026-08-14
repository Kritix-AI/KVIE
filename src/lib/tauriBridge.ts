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
  async injectText(text: string): Promise<void> {
    return invoke<void>('inject_text', { text })
  },
  async eraseAndInject(eraseCount: number, text: string): Promise<void> {
    return invoke<void>('erase_and_inject', { eraseCount, text })
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
  async getActiveAppInfo(): Promise<ActiveAppInfo> {
    return invoke<ActiveAppInfo>('get_active_app_info')
  },
  async getActiveAppContext(): Promise<ActiveAppContext> {
    return invoke<ActiveAppContext>('get_active_app_context')
  },
}
