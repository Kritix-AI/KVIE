/**
 * KVIE Voice Snippets & Text Expansion Engine
 */

export interface VoiceSnippet {
  id: string
  triggerCue: string
  expandedText: string
  enabled: boolean
}

export const DEFAULT_SNIPPETS: VoiceSnippet[] = [
  { id: '1', triggerCue: 'my meeting link', expandedText: 'https://calendly.com/your-username/30min', enabled: true },
  { id: '2', triggerCue: 'my email signature', expandedText: 'Best regards,\nYour Name', enabled: true },
  { id: '3', triggerCue: 'my office address', expandedText: 'Your Office Address', enabled: true },
  { id: '4', triggerCue: 'my phone number', expandedText: '+XX XXXXX XXXXX', enabled: true },
]

const MAX_SNIPPETS = 100
const MAX_SNIPPET_TEXT_LEN = 2000

export function getVoiceSnippets(): VoiceSnippet[] {
  const saved = localStorage.getItem('kvie_voice_snippets')
  if (saved) {
    try {
      const parsed = JSON.parse(saved)
      if (Array.isArray(parsed)) {
        return parsed.slice(0, MAX_SNIPPETS).map(s => ({
          ...s,
          triggerCue: String(s.triggerCue ?? '').slice(0, 200),
          expandedText: String(s.expandedText ?? '').slice(0, MAX_SNIPPET_TEXT_LEN),
        }))
      }
    } catch {
      // fallback
    }
  }
  return DEFAULT_SNIPPETS
}

export function saveVoiceSnippets(snippets: VoiceSnippet[]): void {
  localStorage.setItem('kvie_voice_snippets', JSON.stringify(snippets))
  window.dispatchEvent(new Event('storage'))
}

function escapeRegExp(string: string): string {
  return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

export function expandVoiceSnippets(text: string): { expandedText: string; matchedTrigger: string | null } {
  if (!text) return { expandedText: text, matchedTrigger: null }

  const snippets = getVoiceSnippets().filter(s => s.enabled)
  let resultText = text
  let matched: string | null = null

  for (const snippet of snippets) {
    const cue = snippet.triggerCue.trim().toLowerCase()
    if (!cue) continue

    // Word-boundary via lookarounds: \b fails for cues starting/ending with
    // punctuation ("...sig"), and a function replacement stops `$&`/`$1`
    // sequences in user-defined expanded text being read as replacement
    // patterns.
    let regex: RegExp
    try {
      regex = new RegExp(`(?<![\\w'’])${escapeRegExp(cue)}(?![\\w'’])`, 'gi')
    } catch {
      regex = new RegExp(`\\b${escapeRegExp(cue)}\\b`, 'gi')
    }
    if (regex.test(resultText)) {
      matched = snippet.triggerCue
      resultText = resultText.replace(regex, () => snippet.expandedText)
    }
  }

  return { expandedText: resultText, matchedTrigger: matched }
}
