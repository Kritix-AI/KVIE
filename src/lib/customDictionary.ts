/**
 * KVIE Personalized Custom Dictionary & Vocabulary Bias Engine
 */

export interface CustomWord {
  id: string
  word: string
  phoneticVariants: string[] // Misspellings or phonetic sound-alikes to auto-correct
  enabled: boolean
}

export const DEFAULT_CUSTOM_WORDS: CustomWord[] = [
  { id: '1', word: 'Kritix', phoneticVariants: ['critics', 'critic', 'kritiks', 'kritik', 'kritcs', 'kritic', 'critis'], enabled: true },
  { id: '2', word: 'Tauri', phoneticVariants: ['towel', 'tori', 'taury'], enabled: true },
  { id: '3', word: 'Hinglish', phoneticVariants: ['hinglesh'], enabled: true },
  { id: '4', word: 'Qwen', phoneticVariants: ['q-wen', 'quwen'], enabled: true },
]

export function getCustomDictionary(): CustomWord[] {
  const saved = localStorage.getItem('kvie_custom_dictionary')
  if (saved) {
    try {
      return JSON.parse(saved)
    } catch {
      // fallback
    }
  }
  return DEFAULT_CUSTOM_WORDS
}

export function saveCustomDictionary(words: CustomWord[]): void {
  localStorage.setItem('kvie_custom_dictionary', JSON.stringify(words))
  window.dispatchEvent(new Event('storage'))
}

function escapeRegExp(string: string): string {
  return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

// Applies custom dictionary word corrections to text
export function applyCustomDictionary(text: string): string {
  if (!text) return text

  const customWords = getCustomDictionary().filter(w => w.enabled)
  let resultText = text

  for (const item of customWords) {
    const targetWord = item.word.trim()
    if (!targetWord) continue

    // Replace phonetic variants / misspellings (e.g. "critics", "kritiks" -> "Kritix")
    if (Array.isArray(item.phoneticVariants)) {
      for (const variant of item.phoneticVariants) {
        const vTrim = variant.trim()
        if (!vTrim) continue
        const regex = new RegExp(`(^|\\s|[.,!?;:()"-])${escapeRegExp(vTrim)}(?=$|\\s|[.,!?;:()"-])`, 'gi')
        resultText = resultText.replace(regex, (_, prefix) => `${prefix}${targetWord}`)
      }
    }

    // Replace case-insensitive occurrences of exact target word with correct casing (e.g. "kritix" -> "Kritix")
    const exactRegex = new RegExp(`(^|\\s|[.,!?;:()"-])${escapeRegExp(targetWord)}(?=$|\\s|[.,!?;:()"-])`, 'gi')
    resultText = resultText.replace(exactRegex, (_, prefix) => `${prefix}${targetWord}`)
  }

  return resultText
}

// Generates vocabulary prompt for LLM system prompt & STT initial prompt
export function getCustomVocabularyPrompt(): string {
  const activeWords = getCustomDictionary()
    .filter(w => w.enabled)
    .map(w => w.word.trim())
    .filter(Boolean)

  if (activeWords.length === 0) return ''
  return `Custom Preferred Vocabulary: ${activeWords.join(', ')}`
}
