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
  { id: '1', triggerCue: 'my meeting link', expandedText: 'https://calendly.com/kritix/30min', enabled: true },
  { id: '2', triggerCue: 'my email signature', expandedText: 'Best regards,\nKritix Voice Intelligence Engine Team', enabled: true },
  { id: '3', triggerCue: 'my office address', expandedText: 'Kritix AI Labs, Cyber City, Suite 402, New Delhi, India', enabled: true },
  { id: '4', triggerCue: 'my phone number', expandedText: '+91 98765 43210', enabled: true },
]

export function getVoiceSnippets(): VoiceSnippet[] {
  const saved = localStorage.getItem('kvie_voice_snippets')
  if (saved) {
    try {
      return JSON.parse(saved)
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

    const regex = new RegExp(`\\b${escapeRegExp(cue)}\\b`, 'gi')
    if (regex.test(resultText)) {
      matched = snippet.triggerCue
      resultText = resultText.replace(regex, snippet.expandedText)
    }
  }

  return { expandedText: resultText, matchedTrigger: matched }
}
