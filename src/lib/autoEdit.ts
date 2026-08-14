/**
 * KVIE AI Auto-Edit & Smart Cleanup Engine
 * Model: Qwen2.5-1.5B-Instruct (Best for Hinglish + English)
 */

export interface AutoEditOptions {
  surroundingText?: string
  targetApp?: string
  modelId?: string
}

// Stage 1: Ultra-Fast Regex Hesitation & Filler Word Sanitizer (0ms Latency)
export function sanitizeRawTranscript(text: string): string {
  if (!text) return ''

  let cleaned = text
    // Strip vocal hesitation sounds
    .replace(/\b(um+|uh+|aah+|umm+|uhh+|er+)\b/gi, '')
    // Strip repetitive conversational fillers
    .replace(/\b(like|you know|i mean|basically|actually)\s*,?/gi, '')
    // Fix false starts like "at 2... actually 3" -> "at 3"
    .replace(/(\b\w+\b)\s+(\.\.\.|—|-)\s+(actually|i mean|no|wait)\s+/gi, '')
    // Remove duplicate consecutive words ("the the" -> "the")
    .replace(/\b(\w+)\s+\1\b/gi, '$1')
    // Fix spacing around punctuation
    .replace(/\s+([.,!?])/g, '$1')
    // Remove extra double spaces
    .replace(/\s+/g, ' ')
    .trim()

  if (cleaned.length > 0) {
    // Capitalize first character
    cleaned = cleaned.charAt(0).toUpperCase() + cleaned.slice(1)
  }

  return cleaned
}

import { expandVoiceSnippets } from './snippetsEngine'
import { applyCustomDictionary, getCustomVocabularyPrompt } from './customDictionary'
import { getTranslationSettings, translateText } from './translationEngine'

// Stage 2: Qwen2.5-1.5B-Instruct LLM Auto-Edit Engine + Snippet Expansion + Translation + Custom Dictionary
export async function runQwenAutoEdit(
  rawTranscript: string,
  options: AutoEditOptions = {}
): Promise<string> {
  const stage1Text = sanitizeRawTranscript(rawTranscript)
  if (!stage1Text) return ''

  // Live Translation check
  let workingText = stage1Text
  const translationConfig = getTranslationSettings()
  if (translationConfig.isEnabled) {
    workingText = await translateText(stage1Text, translationConfig.targetLanguage)
  }

  // First check if raw input contains voice snippet triggers
  const snippetCheck = expandVoiceSnippets(workingText)
  let candidateText = snippetCheck.expandedText

  const surroundingContext = options.surroundingText?.trim() || ''
  const appName = options.targetApp || 'Desktop App'
  const vocabPrompt = getCustomVocabularyPrompt()

  const systemPrompt = `You are KVIE's Voice Auto-Edit Engine powered by Qwen2.5-1.5B.
Your task is to clean up raw voice transcripts into polished prose.

STRICT RULES:
1. Strip filler words ("um", "uh", "aah", "like", "you know").
2. Resolve false starts (e.g. "meeting at 2... wait 3 PM" -> "meeting at 3 PM").
3. Fix capitalization and punctuation based on surrounding context.
4. PRESERVE HINGLISH: If text is in Hinglish (Roman Hindi), keep Roman script verbatim.
5. Output ONLY the final cleaned text. NO explanations, NO quotes, NO conversational filler.

${vocabPrompt}
Active Application: ${appName}
Surrounding Text Context: ${surroundingContext.slice(0, 300)}`

  const userPrompt = `Clean up this voice transcript:\n"${candidateText}"`

  try {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 1200) // 1.2s timeout fallback

    const response = await fetch('http://localhost:11434/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
      body: JSON.stringify({
        model: options.modelId || 'qwen2.5:1.5b',
        prompt: `${systemPrompt}\n\n${userPrompt}`,
        stream: false,
        options: {
          temperature: 0.1,
          top_p: 0.9,
          num_predict: 120,
        },
      }),
    })

    clearTimeout(timeoutId)

    if (response.ok) {
      const data = await response.json()
      const llmResult = (data.response || '').trim().replace(/^["']|["']$/g, '')
      if (llmResult.length > 0) {
        const postSnippet = expandVoiceSnippets(llmResult)
        return applyCustomDictionary(postSnippet.expandedText)
      }
    }
  } catch {
    // If Ollama is not running or takes >1.2s, fallback seamlessly to Stage 1 candidate text
  }

  const postSnippetFallback = expandVoiceSnippets(candidateText)
  return applyCustomDictionary(postSnippetFallback.expandedText)
}
