/**
 * Verbal Backtrack Stripping (Wispr Flow parity)
 *
 * When speakers correct themselves mid-dictation, the abandoned clause and the
 * correction cue must not be typed: "meeting at 3, actually 4" -> "4".
 *
 * Guardrails:
 * - Only strips when the cue starts the segment or follows a clause boundary
 *   (comma/period), so "I actually liked it" is never mangled.
 * - Discard cues ("scratch that", "never mind", ...) are intentionally NOT
 *   handled here — in KVIE those are voice commands handled by the command
 *   engine, and swallowing them would break delete-that.
 */

const CORRECTION_CUES = /\b(i mean|no wait|wait no|or rather|correction|actually)\b\s*[:,\-]?\s*/gi

export function stripVerbalBacktracks(text: string): string {
  const trimmed = text.trim()
  if (!trimmed) return trimmed

  const matches = [...trimmed.matchAll(CORRECTION_CUES)]
  for (let index = matches.length - 1; index >= 0; index -= 1) {
    const match = matches[index]
    if (match.index === undefined) continue
    const before = trimmed.slice(0, match.index).trimEnd()
    const after = trimmed.slice(match.index + match[0].length).trim()
    // Nothing said after the cue — it is not a backtrack ("wait, what?").
    if (!after) continue
    // The cue must start the segment or follow a clause boundary.
    if (before.length === 0 || /[.,!?;:\n]$/.test(before)) {
      return after
    }
  }
  return trimmed
}
