import { isAndroid } from './androidKeyboard'
import { getServiceBaseUrl } from './modelsApi'

/**
 * KVIE Voice Command Execution Engine
 * Powered by Qwen2.5-1.5B-Instruct & IUIAutomation Context
 */

const COMMAND_TRIGGERS = [
  /^make\s+this\s+/i,
  /^make\s+it\s+/i,
  /^summarize\s+/i,
  /^rephrase\s+/i,
  /^change\s+tone\s+/i,
  /^fix\s+grammar\s+/i,
  /^translate\s+this\s+/i,
  /^format\s+as\s+/i,
  /^convert\s+to\s+/i,
  /^rewrite\s+/i,
  /^shorten\s+/i,
  /^expand\s+/i,
]

export function isVoiceCommandIntent(spokenText: string): boolean {
  if (!spokenText) return false
  const trimmed = spokenText.trim()
  return COMMAND_TRIGGERS.some(trigger => trigger.test(trimmed))
}

export async function executeVoiceCommand(
  commandText: string,
  existingText: string,
  appName: string = 'Desktop App'
): Promise<{ transformedText: string; isSuccess: boolean }> {
  if (!commandText.trim()) {
    return { transformedText: existingText, isSuccess: false }
  }

  // Sanitize inputs — strip control characters, cap lengths
  const safeCommand = commandText.replace(/[\x00-\x1F\x7F]/g, ' ').trim().slice(0, 500)
  const safeApp = appName.replace(/[\x00-\x1F\x7F]/g, ' ').trim().slice(0, 100)
  const contextText = existingText.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, '').trim()

  const systemPrompt = `You are KVIE's Voice Command Engine powered by Qwen2.5-1.5B.
Your task is to execute the user's voice instruction on the provided target text.

Target Application: ${safeApp}
Voice Instruction: "${safeCommand}"

[EXISTING TARGET TEXT]:
"${contextText.slice(0, 800)}"

STRICT RULES:
1. Apply the user's voice instruction (e.g. make formal, summarize into bullet points, shorten, fix grammar, rewrite).
2. If [EXISTING TARGET TEXT] is empty, compose a new draft matching the user's voice instruction.
3. PRESERVE HINGLISH: If the target text or command is in Roman Hinglish, keep Roman script verbatim.
4. Output ONLY the resulting transformed text. Do NOT add commentary, introductions, or quotes.`

  try {
    if (isAndroid()) throw new Error('Android uses its local keyboard engine')
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 2200)

    const response = await fetch(`${getServiceBaseUrl()}/api/ollama/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
      body: JSON.stringify({
        model: 'qwen2.5:1.5b',
        prompt: systemPrompt,
        temperature: 0.2,
        max_tokens: 300,
      }),
    })

    clearTimeout(timeoutId)

    if (response.ok) {
      const data = await response.json()
      const result = (data.response || '').trim().replace(/^["']|["']$/g, '').slice(0, 4000)
      if (result.length > 0) {
        return { transformedText: result, isSuccess: true }
      }
    }
  } catch {
    // Fallback if local LLM service is offline or times out
  }

  return { transformedText: existingText || commandText, isSuccess: false }
}
