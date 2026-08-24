/**
 * KVIE Voice Command & Intent Execution Engine
 * Supports Natural English & Hinglish commands with Structured JSON Protocol
 */

const COMMAND_TRIGGER_PATTERNS = [
  /^(?:please\s+|can\s+you\s+|kindly\s+|hey\s+kvie\s+)?(?:make\s+(?:this|it)\s+(?:formal|professional|casual|friendly|polite))/i,
  /^(?:please\s+|can\s+you\s+|kindly\s+|hey\s+kvie\s+)?(?:summarize|give\s+(?:a\s+)?summary|make\s+(?:a\s+)?bullet\s+points?)/i,
  /^(?:please\s+|can\s+you\s+|kindly\s+|hey\s+kvie\s+)?(?:fix\s+(?:the\s+)?(?:grammar|spelling|mistakes|errors)|correct\s+(?:the\s+)?grammar|polish\s+(?:this|the\s+text))/i,
  /^(?:please\s+|can\s+you\s+|kindly\s+|hey\s+kvie\s+)?(?:shorten\s+(?:this|it)|make\s+(?:this|it)\s+(?:shorter|concise|brief))/i,
  /^(?:please\s+|can\s+you\s+|kindly\s+|hey\s+kvie\s+)?(?:expand\s+(?:this|it)|elaborate|add\s+more\s+details)/i,
  /^(?:please\s+|can\s+you\s+|kindly\s+|hey\s+kvie\s+)?(?:rewrite|rephrase|paraphrase|change\s+(?:the\s+)?tone)/i,
  /^(?:please\s+|can\s+you\s+|kindly\s+|hey\s+kvie\s+)?(?:format\s+as|convert\s+to|turn\s+into)/i,
  /^(?:please\s+|can\s+you\s+|kindly\s+|hey\s+kvie\s+)?(?:translate\s+(?:this|it)\s+to)/i,
  /^(?:please\s+|can\s+you\s+|kindly\s+|hey\s+kvie\s+)?(?:capitalize\s+all|uppercase|lowercase)/i,
  /^(?:clear\s+(?:all|text|document)|delete\s+all|undo(?:\s+that)?|redo(?:\s+that)?)$/i,
  // Hinglish Commands
  /^(?:is\s+text\s+ko|isko)\s+(?:formal|professional|casual)\s+(?:banao|kardo)/i,
  /^(?:iska\s+summary|summary)\s+(?:banao|bana\s+do|kardo)/i,
  /^(?:bullet\s+points?\s+me\s+convert\s+karo|points\s+banao)/i,
  /^(?:grammar\s+sahi\s+karo|spelling\s+theek\s+karo|mistakes\s+fix\s+karo)/i,
  /^(?:chhota\s+karo|bada\s+karo|dobara\s+likho|sab\s+clear\s+karo|sab\s+delete\s+karo)/i,
]

export function isVoiceCommandIntent(spokenText: string): boolean {
  if (!spokenText) return false
  const trimmed = spokenText.trim()
  return COMMAND_TRIGGER_PATTERNS.some(trigger => trigger.test(trimmed))
}

let cachedCommandModel: string | null = null

async function getOllamaCommandModel(): Promise<string> {
  if (cachedCommandModel) return cachedCommandModel

  try {
    const res = await fetch('http://localhost:11434/api/tags', { signal: AbortSignal.timeout(1200) })
    if (res.ok) {
      const data = await res.json()
      const models = data.models || []
      const preferred = ['qwen2.5:1.5b', 'qwen', 'mistral:7b', 'mistral', 'phi3:mini', 'phi3', 'llama3']
      for (const pref of preferred) {
        const found = models.find((m: { name?: string }) => (m.name || '').toLowerCase().includes(pref))
        if (found) {
          cachedCommandModel = found.name
          return found.name
        }
      }
      if (models.length > 0) {
        cachedCommandModel = models[0].name
        return models[0].name
      }
    }
  } catch {
    // Fallback default
  }

  return 'phi3:mini'
}

export interface CommandExecutionResult {
  transformedText: string
  isSuccess: boolean
  intent: string
  action: 'replace_text' | 'clear' | 'undo' | 'none'
}

export async function executeVoiceCommand(
  commandText: string,
  existingText: string = '',
  appName: string = 'Desktop App'
): Promise<CommandExecutionResult> {
  const cmd = commandText.trim()
  if (!cmd) {
    return { transformedText: existingText, isSuccess: false, intent: 'none', action: 'none' }
  }

  const lower = cmd.toLowerCase()

  // Deterministic local actions
  if (/^(?:clear\s+(?:all|text|document)|delete\s+all|sab\s+clear\s+karo|sab\s+delete\s+karo)$/i.test(lower)) {
    return { transformedText: '', isSuccess: true, intent: 'clear', action: 'clear' }
  }
  if (/^(?:undo(?:\s+that)?|undo\s+karo)$/i.test(lower)) {
    return { transformedText: '', isSuccess: true, intent: 'undo', action: 'undo' }
  }

  // Tier 1: KVIE Python Local Service REST Endpoint (JSON Request & Response)
  try {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 2800)

    const response = await fetch('http://127.0.0.1:8765/api/command/execute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
      body: JSON.stringify({
        command: cmd,
        context: existingText,
        app_name: appName,
      }),
    })

    clearTimeout(timeout)

    if (response.ok) {
      const data = await response.json()
      if (data.ok && data.transformed_text !== undefined) {
        return {
          transformedText: data.transformed_text,
          isSuccess: true,
          intent: data.intent || 'command',
          action: data.action === 'clear' ? 'clear' : 'replace_text',
        }
      }
    }
  } catch {
    // Fallback to Tier 2: Direct Ollama LLM
  }

  // Tier 2: Direct Local Ollama LLM Execution (JSON / Text Generation)
  try {
    const model = await getOllamaCommandModel()
    const systemPrompt = `You are KVIE's Voice Command Intelligence Engine.
Execute the user's spoken command on the provided target text.

Target App: ${appName}
Voice Command: "${cmd}"

TARGET TEXT:
"${existingText.slice(0, 1200)}"

RULES:
1. Apply the command directly (e.g. make formal, summarize in bullet points, fix grammar, shorten, expand, rewrite).
2. If TARGET TEXT is empty, write a complete new response fulfilling the voice command.
3. If Roman Hinglish is used, preserve Roman script style.
4. Output ONLY the resulting transformed text with no commentary or quotes.`

    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 3500)

    const response = await fetch('http://localhost:11434/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
      body: JSON.stringify({
        model,
        prompt: systemPrompt,
        stream: false,
        options: {
          temperature: 0.2,
          top_p: 0.9,
          num_predict: 400,
        },
      }),
    })

    clearTimeout(timeout)

    if (response.ok) {
      const data = await response.json()
      const result = (data.response || '').trim().replace(/^["'`]|["'`]$/g, '').trim()
      if (result) {
        return {
          transformedText: result,
          isSuccess: true,
          intent: 'command',
          action: 'replace_text',
        }
      }
    }
  } catch {
    // Fallback if offline
  }

  return { transformedText: existingText || cmd, isSuccess: false, intent: 'fallback', action: 'none' }
}
