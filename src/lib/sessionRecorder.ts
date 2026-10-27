import { tauriBridge } from './tauriBridge'
import { getServiceBaseUrl } from './modelsApi'

export interface VoiceSession {
  id: string
  text: string
  targetApp: string
  timestamp: string
  wordCount: number
}

const MAX_SESSIONS = 200
const MAX_SESSION_TEXT_LEN = 10000

export const saveVoiceSession = async (sessionOrText: string | VoiceSession, overrideApp?: string) => {
  let cleanText = ''
  let targetApp = overrideApp || 'Kritix Workspace'

  if (typeof sessionOrText === 'string') {
    cleanText = sessionOrText.trim().slice(0, MAX_SESSION_TEXT_LEN)
  } else if (sessionOrText && typeof sessionOrText === 'object') {
    cleanText = (sessionOrText.text || '').trim().slice(0, MAX_SESSION_TEXT_LEN)
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

  const updatedSessions = [newSession, ...currentSessions].slice(0, MAX_SESSIONS)
  try {
    localStorage.setItem('kvie_voice_sessions', JSON.stringify(updatedSessions))
  } catch {
    // Quota exceeded — drop the session rather than crash an unawaited save.
    return
  }

  try {
    window.AndroidKeyboardBridge?.recordSession?.(cleanText, targetApp)
  } catch {}

  // Mirror into the backend's dictation-history DB (Wispr-style History table).
  // Fire-and-forget: the local service may be offline, localStorage is primary.
  void fetch(`${getServiceBaseUrl()}/api/history`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ raw_text: cleanText, final_text: cleanText, app_name: targetApp }),
  }).catch(() => {})

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
