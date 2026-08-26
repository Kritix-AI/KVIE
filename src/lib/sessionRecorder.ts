import { tauriBridge } from './tauriBridge'

export interface VoiceSession {
  id: string
  text: string
  targetApp: string
  timestamp: string
  wordCount: number
}

export const saveVoiceSession = async (sessionOrText: string | VoiceSession, overrideApp?: string) => {
  let cleanText = ''
  let targetApp = overrideApp || 'Kritix Workspace'

  if (typeof sessionOrText === 'string') {
    cleanText = sessionOrText.trim()
  } else if (sessionOrText && typeof sessionOrText === 'object') {
    cleanText = (sessionOrText.text || '').trim()
    if (sessionOrText.targetApp) {
      targetApp = sessionOrText.targetApp
    }
  }

  if (!cleanText || cleanText.length < 2) return

  if (!overrideApp && typeof sessionOrText === 'string') {
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

  try {
    window.AndroidKeyboardBridge?.recordSession?.(cleanText, targetApp)
  } catch {}

  window.dispatchEvent(new Event('storage'))
}

export const getRecordedVoiceSessions = (): VoiceSession[] => {
  let localList: VoiceSession[] = []
  try {
    const raw = localStorage.getItem('kvie_voice_sessions')
    if (raw) {
      localList = JSON.parse(raw)
    }
  } catch {}

  // Fetch native Android sessions from SharedPreferences
  let androidList: VoiceSession[] = []
  try {
    const nativeRaw = window.AndroidKeyboardBridge?.getRecordedSessions?.()
    if (nativeRaw) {
      androidList = JSON.parse(nativeRaw)
    }
  } catch {}

  if (androidList.length === 0) {
    return localList
  }

  // Merge unique sessions by text + timestamp or id
  const map = new Map<string, VoiceSession>()
  for (const s of [...androidList, ...localList]) {
    const key = `${s.text.trim()}_${s.timestamp}`
    if (!map.has(key)) {
      map.set(key, s)
    }
  }

  const merged = Array.from(map.values()).sort((a, b) => Number(b.id || 0) - Number(a.id || 0))
  try {
    localStorage.setItem('kvie_voice_sessions', JSON.stringify(merged))
  } catch {}

  return merged
}

export const clearVoiceSessions = () => {
  localStorage.removeItem('kvie_voice_sessions')
  try {
    window.AndroidKeyboardBridge?.clearRecordedSessions?.()
  } catch {}
  window.dispatchEvent(new Event('storage'))
}
