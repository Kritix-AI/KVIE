/**
 * KVIE Live Translation Engine (100+ Languages)
 * Powered by Local LLMs (Ollama Mistral / Phi-3 / Qwen) & Multi-Tier Fast Fallback
 */

export interface TranslationLanguage {
  code: string
  name: string
  nativeName: string
}

export const SUPPORTED_LANGUAGES: TranslationLanguage[] = [
  { code: 'en', name: 'English', nativeName: 'English' },
  { code: 'hi', name: 'Hindi', nativeName: 'हिन्दी' },
  { code: 'bn', name: 'Bengali', nativeName: 'বাংলা' },
  { code: 'mr', name: 'Marathi', nativeName: 'मराठी' },
  { code: 'te', name: 'Telugu', nativeName: 'తెలుగు' },
  { code: 'ta', name: 'Tamil', nativeName: 'தமிழ்' },
  { code: 'gu', name: 'Gujarati', nativeName: 'ગુજરાતી' },
  { code: 'ur', name: 'Urdu', nativeName: 'اردو' },
  { code: 'pa', name: 'Punjabi', nativeName: 'ਪੰਜਾਬੀ' },
  { code: 'es', name: 'Spanish', nativeName: 'Español' },
  { code: 'fr', name: 'French', nativeName: 'Français' },
  { code: 'de', name: 'German', nativeName: 'Deutsch' },
  { code: 'ja', name: 'Japanese', nativeName: '日本語' },
  { code: 'zh', name: 'Chinese', nativeName: '中文' },
  { code: 'ru', name: 'Russian', nativeName: 'Русский' },
  { code: 'ar', name: 'Arabic', nativeName: 'العربية' },
  { code: 'pt', name: 'Portuguese', nativeName: 'Português' },
  { code: 'it', name: 'Italian', nativeName: 'Italiano' },
  { code: 'ko', name: 'Korean', nativeName: '한국어' },
]

export function getTranslationSettings(): { isEnabled: boolean; targetLanguage: string } {
  const isEnabled = localStorage.getItem('kvie_translation_mode') === 'true'
  const targetLanguage = localStorage.getItem('kvie_target_language') || 'en'
  return { isEnabled, targetLanguage }
}

export function saveTranslationSettings(isEnabled: boolean, targetLanguage: string): void {
  localStorage.setItem('kvie_translation_mode', String(isEnabled))
  localStorage.setItem('kvie_target_language', targetLanguage)
  window.dispatchEvent(new Event('storage'))
}

let cachedOllamaModel: string | null = null
let lastModelCheckTime = 0

async function getAvailableOllamaModel(): Promise<string | null> {
  const now = Date.now()
  if (cachedOllamaModel && now - lastModelCheckTime < 60000) {
    return cachedOllamaModel
  }

  try {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 1200)
    const res = await fetch('http://localhost:11434/api/tags', { signal: controller.signal })
    clearTimeout(timeout)

    if (res.ok) {
      const data = await res.json()
      const models = data.models || []
      if (models.length > 0) {
        // Preferred models in priority order
        const preferred = ['qwen2.5:1.5b', 'qwen', 'mistral:7b', 'mistral', 'phi3:mini', 'phi3', 'llama3', 'gemma']
        for (const pref of preferred) {
          const found = models.find((m: { name?: string; model?: string }) => (m.name || m.model || '').toLowerCase().includes(pref))
          if (found) {
            cachedOllamaModel = found.name || found.model
            lastModelCheckTime = now
            return cachedOllamaModel
          }
        }
        cachedOllamaModel = models[0].name || models[0].model
        lastModelCheckTime = now
        return cachedOllamaModel
      }
    }
  } catch {
    // Ollama not reachable
  }

  return null
}

function sanitizeTranslationOutput(raw: string): string {
  if (!raw) return ''
  return raw
    .trim()
    .replace(/^["'`]|["'`]$/g, '') // remove quotes
    .replace(/\([^)]*\)/g, '') // remove parenthetical remarks like (Hello...)
    .replace(/\[[^\]]*\]/g, '') // remove bracketed notes
    .replace(/^(Here is the translation|Translation|Translated text):\s*/i, '')
    .trim()
}

export async function translateText(
  text: string,
  targetLangCode: string = 'en'
): Promise<string> {
  const trimmed = text.trim()
  if (!trimmed) return text

  const targetLangObj = SUPPORTED_LANGUAGES.find(l => l.code === targetLangCode)
  const targetLangName = targetLangObj?.name || targetLangCode

  // Tier 1: Local Ollama Model (Mistral / Phi-3 / Qwen)
  const ollamaModel = await getAvailableOllamaModel()
  if (ollamaModel) {
    try {
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), 2500)

      const prompt = `Translate the following spoken sentence accurately into ${targetLangName}. Output ONLY the translated sentence with no commentary, no notes, and no quotes:\n\n"${trimmed}"`

      const response = await fetch('http://localhost:11434/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({
          model: ollamaModel,
          prompt,
          stream: false,
          options: {
            temperature: 0.1,
            top_p: 0.9,
            num_predict: 180,
          },
        }),
      })

      clearTimeout(timeoutId)

      if (response.ok) {
        const data = await response.json()
        const cleaned = sanitizeTranslationOutput(data.response || '')
        if (cleaned) return cleaned
      }
    } catch {
      // Fallback to Tier 2
    }
  }

  // Tier 2: Free Public MyMemory API Fallback (Auto-detect source -> target language)
  try {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 2000)
    const url = `https://api.mymemory.translated.net/get?q=${encodeURIComponent(trimmed)}&langpair=autodetect|${targetLangCode}`

    const res = await fetch(url, { signal: controller.signal })
    clearTimeout(timeoutId)

    if (res.ok) {
      const data = await res.json()
      const translated = data.responseData?.translatedText
      if (translated && !translated.startsWith('MYMEMORY WARNING')) {
        const cleaned = sanitizeTranslationOutput(translated)
        if (cleaned) return cleaned
      }
    }
  } catch {
    // Fallback
  }

  return trimmed
}
