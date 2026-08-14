import { tauriBridge } from './tauriBridge'

export interface VoiceSession {
  id: string
  text: string
  targetApp: string
  timestamp: string
  wordCount: number
}

export const saveVoiceSession = async (text: string, overrideApp?: string) => {
  const cleanText = text.trim()
  if (!cleanText || cleanText.length < 2) return

  let targetApp = overrideApp || 'Kritix Workspace'
  if (!overrideApp) {
    try {
      const appInfo = await tauriBridge.getActiveAppInfo()
      if (appInfo && appInfo.app_name) {
        targetApp = appInfo.app_name
      }
    } catch {
      targetApp = 'Active App'
    }
  }

  const existingSaved = localStorage.getItem('kvie_voice_sessions')
  let currentSessions: VoiceSession[] = []
  if (existingSaved) {
    try {
      currentSessions = JSON.parse(existingSaved)
    } catch {
      currentSessions = []
    }
  }

  // Avoid duplicate entry if identical to the latest recorded session
  if (currentSessions.length > 0 && currentSessions[0].text === cleanText) {
    return
  }

  const newSession: VoiceSession = {
    id: String(Date.now()),
    text: cleanText,
    targetApp,
    timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    wordCount: cleanText.split(/\s+/).length,
  }

  const updatedSessions = [newSession, ...currentSessions]
  localStorage.setItem('kvie_voice_sessions', JSON.stringify(updatedSessions))
  window.dispatchEvent(new Event('storage'))
}
