// Must match the Rust-side MAX_ERASE_COUNT — a single inject can never erase more.
const MAX_ERASE_CHUNK = 500

// Editors delete one grapheme cluster per Backspace (Word, Chromium, modern
// Notepad) — counting UTF-16 code units would over-erase Hindi combining marks
// and emoji, the core Hinglish use case.
interface GraphemeSegmenter {
  segment(text: string): Iterable<{ segment: string }>
}

const graphemeSegmenter: GraphemeSegmenter | undefined =
  typeof Intl !== 'undefined' && 'Segmenter' in Intl
    ? new (Intl as unknown as { Segmenter: new (locale: string, options: { granularity: string }) => GraphemeSegmenter }).Segmenter('en', { granularity: 'grapheme' })
    : undefined

const toGraphemes = (text: string): string[] => {
  if (graphemeSegmenter) {
    return Array.from(graphemeSegmenter.segment(text), segment => segment.segment)
  }
  return Array.from(text)
}

/**
 * KVIE Smart Incremental Typing & Overlap Analysis Engine
 * 
 * Solves the sentence rewriting problem on pauses:
 * - Analyzes tail words of committed text (last N words) to prevent duplicating words across audio chunks.
 * - Ensures that once text is committed after a pause, it is NEVER erased or rewritten.
 * - Only calculates backspaces/appends for the currently active uncommitted interim clause.
 * - Automatically handles smart spacing and punctuation attachment between sentences.
 */

import { applyCustomDictionary } from './customDictionary'
import { expandVoiceSnippets } from './snippetsEngine'
import { getTranslationSettings, translateText } from './translationEngine'

export const normalizeWord = (w: string): string => {
  return w.toLowerCase().replace(/[^\p{L}\p{N}]/gu, '')
}

/**
 * Finds how many words at the end of `leftText` match the beginning of `rightText`.
 * Uses punctuation-insensitive comparison (e.g. "hai." matches "hai").
 */
export const findWordOverlap = (leftText: string, rightText: string, maxWords = 10): number => {
  const leftWords = leftText.trim().split(/\s+/).filter(Boolean)
  const rightWords = rightText.trim().split(/\s+/).filter(Boolean)
  if (!leftWords.length || !rightWords.length) return 0

  let overlap = 0
  const maxCheck = Math.min(leftWords.length, rightWords.length, maxWords)

  for (let size = maxCheck; size >= 1; size -= 1) {
    // Compare over normalized forms but count over RAW words: punctuation-only
    // tokens (e.g. the Hindi danda) must keep the word indices aligned with the
    // raw slices the callers perform.
    const tail = leftWords.slice(-size).map(normalizeWord).join(' ')
    const head = rightWords.slice(0, size).map(normalizeWord).join(' ')
    if (tail && tail === head) {
      overlap = size
      break
    }
  }

  return overlap
}

/**
 * Merges rolling / sliding window text without duplicating overlapping tail words.
 */
export const mergeRollingText = (existing: string, incoming: string): string => {
  const left = existing.trim()
  const right = incoming.trim()
  if (!left) return right
  if (!right) return left

  const leftLower = left.toLowerCase()
  const rightLower = right.toLowerCase()
  if (leftLower.endsWith(rightLower)) return left
  if (leftLower.includes(rightLower) && left.length > right.length + 5) return left
  if (rightLower.startsWith(leftLower)) return right

  const overlap = findWordOverlap(left, right)
  const rightWords = right.split(/\s+/).filter(Boolean)

  if (overlap > 0) {
    const nonOverlapping = rightWords.slice(overlap).join(' ')
    if (!nonOverlapping) return left
    // Determine connector spacing
    const connector = left.endsWith(' ') || left.endsWith('\n') ? '' : ' '
    return `${left}${connector}${nonOverlapping}`.trim()
  }

  const connector = left.endsWith(' ') || left.endsWith('\n') ? '' : ' '
  return `${left}${connector}${right}`.trim()
}

/**
 * Strips any words from `incomingText` that already exist at the tail of `committedText`.
 * Also formats proper spacing before the continuation.
 */
export const stripCommittedOverlap = (
  committedText: string,
  incomingText: string
): { cleanText: string; overlapWords: number } => {
  const committed = committedText.trim()
  const incoming = incomingText.trim()

  if (!committed) {
    return { cleanText: incoming, overlapWords: 0 }
  }
  if (!incoming) {
    return { cleanText: '', overlapWords: 0 }
  }

  // Check if incoming is already a full cumulative transcript containing committed
  const committedLower = committed.toLowerCase()
  const incomingLower = incoming.toLowerCase()

  if (incomingLower.startsWith(committedLower)) {
    const remainder = incoming.slice(committed.length).trim()
    const needsSpace = committedText.length > 0 && !/[\s\n]$/.test(committedText) && !/^[.,!?]/.test(remainder)
    return {
      cleanText: remainder ? (needsSpace ? ` ${remainder}` : remainder) : '',
      overlapWords: committed.split(/\s+/).length,
    }
  }

  // Check word-level overlap with the tail of committed text
  const overlap = findWordOverlap(committed, incoming)
  const incomingWords = incoming.split(/\s+/).filter(Boolean)

  let remainder = incoming
  if (overlap > 0) {
    remainder = incomingWords.slice(overlap).join(' ').trim()
    if (!remainder) {
      // The overlap covered every incoming word, but the raw strings can
      // still differ by trailing punctuation ("today" → "today.") — keep
      // that suffix instead of silently dropping it.
      const committedTailWords = committed.split(/\s+/).filter(Boolean)
      const tailCount = Math.min(overlap, committedTailWords.length)
      const committedTail = committedTailWords.slice(-tailCount).join(' ')
      if (
        committedTail.length > 0 &&
        incoming.length > committedTail.length &&
        incoming.startsWith(committedTail)
      ) {
        const extra = incoming.slice(committedTail.length)
        const needsSpace =
          committedText.length > 0 &&
          !/[\s\n]$/.test(committedText) &&
          !/^[.,!?;:]/.test(extra)
        return { cleanText: needsSpace ? ` ${extra}` : extra, overlapWords: overlap }
      }
      return { cleanText: '', overlapWords: overlap }
    }
  }

  if (!remainder) {
    return { cleanText: '', overlapWords: overlap }
  }

  // Smart inter-sentence spacing:
  // If committed text ends with a character and remainder starts with a word, prepend space
  const needsLeadingSpace =
    committedText.length > 0 &&
    !/[\s\n]$/.test(committedText) &&
    !/^[.,!?;:]/.test(remainder)

  const formatted = needsLeadingSpace ? ` ${remainder}` : remainder
  return { cleanText: formatted, overlapWords: overlap }
}

export interface TypingDelta {
  eraseCount: number
  appendText: string
  committedText: string
  uncommittedInterim: string
}

/**
 * Manages stateful incremental typing into external applications.
 * Ensures committed text is NEVER erased, and only the active interim phrase is delta-updated.
 */
export class IncrementalTypingSession {
  private committedText = ''
  private uncommittedInterim = ''
  private lastProcessedLen = 0  // Track length of last processed text for safety

  public getCommittedText(): string {
    return this.committedText
  }

  public getUncommittedInterim(): string {
    return this.uncommittedInterim
  }

  public getFullText(): string {
    return `${this.committedText}${this.uncommittedInterim}`.trim()
  }

  public reset(): void {
    this.committedText = ''
    this.uncommittedInterim = ''
    this.lastProcessedLen = 0
  }

  /** State before a delta — used to roll back when an inject is rejected. */
  public snapshot(): { committedText: string; uncommittedInterim: string } {
    return { committedText: this.committedText, uncommittedInterim: this.uncommittedInterim }
  }

  public restoreTo(state: { committedText: string; uncommittedInterim: string }): void {
    this.committedText = state.committedText
    this.uncommittedInterim = state.uncommittedInterim
    this.lastProcessedLen = (this.committedText + this.uncommittedInterim).length
  }

  public commitCurrent(): void {
    if (this.uncommittedInterim) {
      this.committedText = `${this.committedText}${this.uncommittedInterim}`
      this.uncommittedInterim = ''
    }
    this.lastProcessedLen = this.committedText.length
  }

  /**
   * Process an incoming speech segment (interim or final) and compute the exact
   * keyboard delta (how many backspaces to press, and what text to type).
   *
   * IMPORTANT: rawIncoming must be the SAME text that was sent to the backend
   * for typing. If processing (dictionary/snippets) changes between interim and
   * final, the delta will be wrong. Use the same pipeline for both.
   */
  public processSegment(rawIncoming: string, isFinal: boolean): TypingDelta {
    const raw = rawIncoming.trim()
    const previousInterim = this.uncommittedInterim

    if (!raw) {
      if (isFinal && previousInterim) {
        // The STT withdrew everything it had shown as interim — erase it from
        // the target app instead of leaving orphaned text on screen.
        const eraseCount = Math.min(toGraphemes(previousInterim).length, MAX_ERASE_CHUNK)
        this.uncommittedInterim = ''
        this.lastProcessedLen = this.committedText.length
        return { eraseCount, appendText: '', committedText: this.committedText, uncommittedInterim: '' }
      }
      return {
        eraseCount: 0,
        appendText: '',
        committedText: this.committedText,
        uncommittedInterim: previousInterim,
      }
    }

    // Step 1: Strip any tail overlap with committed text
    const { cleanText } = stripCommittedOverlap(this.committedText, raw)

    if (previousInterim === cleanText && !isFinal) {
      return {
        eraseCount: 0,
        appendText: '',
        committedText: this.committedText,
        uncommittedInterim: previousInterim,
      }
    }

    // Step 2: Delta against uncommittedInterim ONLY (never touch committedText!)
    // Counted in grapheme clusters so the erase count matches how editors
    // actually delete text.
    const previousGraphemes = toGraphemes(previousInterim)
    const targetGraphemes = toGraphemes(cleanText)
    let commonPrefixLen = 0
    const minLen = Math.min(previousGraphemes.length, targetGraphemes.length)
    while (commonPrefixLen < minLen && previousGraphemes[commonPrefixLen] === targetGraphemes[commonPrefixLen]) {
      commonPrefixLen += 1
    }

    const eraseNeeded = previousGraphemes.length - commonPrefixLen
    if (eraseNeeded > MAX_ERASE_CHUNK) {
      // A single inject cannot erase more than the Rust-side cap. Erase what we
      // can and keep the engine state matching what will actually be on screen,
      // so the next delta retries the remainder instead of desyncing.
      const erasedRemainder = previousGraphemes.slice(0, commonPrefixLen + MAX_ERASE_CHUNK).join('')
      if (isFinal) {
        this.committedText = `${this.committedText}${erasedRemainder}`
        this.uncommittedInterim = ''
      } else {
        this.uncommittedInterim = erasedRemainder
      }
      this.lastProcessedLen = (this.committedText + this.uncommittedInterim).length
      return {
        eraseCount: MAX_ERASE_CHUNK,
        appendText: '',
        committedText: this.committedText,
        uncommittedInterim: this.uncommittedInterim,
      }
    }

    const eraseCount = Math.max(0, eraseNeeded)
    const appendText = targetGraphemes.slice(commonPrefixLen).join('')

    if (isFinal) {
      // Finalize this segment into committedText and reset uncommittedInterim
      this.committedText = `${this.committedText}${cleanText}`
      this.uncommittedInterim = ''
    } else {
      this.uncommittedInterim = cleanText
    }

    this.lastProcessedLen = (this.committedText + this.uncommittedInterim).length

    return {
      eraseCount,
      appendText,
      committedText: this.committedText,
      uncommittedInterim: this.uncommittedInterim,
    }
  }
}

/**
 * Transforms raw transcribed speech through the full KVIE intelligence pipeline:
 * 1. Personalized Custom Dictionary & Jargon Auto-Correction
 * 2. Voice Snippets Expansion
 * 3. Real-Time Multilingual Live Translation (if enabled)
 */
export async function processSpokenVoiceText(
  rawText: string,
  options: {
    applyDictionary?: boolean
    expandSnippets?: boolean
    applyTranslation?: boolean
    targetLanguage?: string
  } = {}
): Promise<string> {
  const trimmed = rawText.trim()
  if (!trimmed) return rawText

  // Step 1: Personalized Custom Dictionary & Vocabulary Bias
  let text = options.applyDictionary !== false ? applyCustomDictionary(trimmed) : trimmed

  // Step 2: Voice Snippets Expansion
  if (options.expandSnippets !== false) {
    const expanded = expandVoiceSnippets(text)
    text = expanded.expandedText
  }

  // Step 3: Live Voice Translation
  const translationConfig = getTranslationSettings()
  const isTransEnabled = options.applyTranslation ?? translationConfig.isEnabled
  const targetLang = options.targetLanguage ?? translationConfig.targetLanguage

  if (isTransEnabled && targetLang) {
    try {
      const translated = await translateText(text, targetLang)
      if (translated && translated.trim()) {
        text = translated.trim()
      }
    } catch {
      // Keep dictionary-corrected text on translation error
    }
  }

  return text
}

