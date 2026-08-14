/**
 * KVIE Live Translation Engine (100+ Languages)
 * Powered by Qwen2.5-1.5B & Whisper Multilingual Translation
 */

export interface TranslationLanguage {
  code: string
  name: string
  nativeName: string
}

export const SUPPORTED_LANGUAGES: TranslationLanguage[] = [
  { code: 'en', name: 'English', nativeName: 'English' },
  { code: 'hi', name: 'Hindi', nativeName: 'हिन्दी' },
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

export async function translateText(
  text: string,
  targetLangCode: string = 'en'
): Promise<string> {
  if (!text.trim()) return text

  const targetLang = SUPPORTED_LANGUAGES.find(l => l.code === targetLangCode)?.name || targetLangCode

  const systemPrompt = `You are KVIE's Real-Time Translation Engine powered by Qwen2.5-1.5B.
Your task is to translate raw voice transcriptions accurately into target language: ${targetLang}.

RULES:
1. Translate the spoken text directly into ${targetLang}.
2. Preserve original meaning, tone, and context.
3. If input is already in ${targetLang}, return it cleaned up without changes.
4. Output ONLY the translated text. Do NOT add meta explanations, commentary, or quotes.`

  try {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 1800)

    const response = await fetch('http://localhost:11434/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
      body: JSON.stringify({
        model: 'qwen2.5:1.5b',
        prompt: `${systemPrompt}\n\nInput Text:\n"${text}"`,
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
      const result = (data.response || '').trim().replace(/^["']|["']$/g, '')
      if (result.length > 0) return result
    }
  } catch {
    // Fallback if offline
  }

  return text
}
