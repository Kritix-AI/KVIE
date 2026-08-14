export interface ElectronAPI {
  system: {
    lock: () => Promise<{ success: boolean; error?: string }>
    shutdown: () => Promise<{ success: boolean; error?: string }>
    restart: () => Promise<{ success: boolean; error?: string }>
    volume: (action: 'up' | 'down' | 'mute') => Promise<{ success: boolean; error?: string }>
    openApp: (path: string) => Promise<{ success: boolean; error?: string }>
    openUrl: (url: string) => Promise<{ success: boolean; error?: string }>
    openYouTube: () => Promise<{ success: boolean; error?: string }>
    openReminder: () => Promise<{ success: boolean; error?: string }>
  }
  window: {
    minimize: () => void
    maximize: () => void
    close: () => void
  }
  env: {
    get: () => Promise<{ username: string; Assistantname: string }>
  }
  ai: {
    sendMessage: (message: string) => Promise<{ success: boolean; response: string }>
  }
  platform: string
}

declare global {
  interface Window {
    electronAPI: ElectronAPI
  }
}