/**
 * KVIE Smart Incremental Typing & Overlap Analysis Engine
 * 
 * Solves the sentence rewriting problem on pauses:
 * - Analyzes tail words of committed text (last N words) to prevent duplicating words across audio chunks.
 * - Ensures that once text is committed after a pause, it is NEVER erased or rewritten.
 * - Only calculates backspaces/appends for the currently active uncommitted interim clause.
 * - Automatically handles smart spacing and punctuation attachment between sentences.
 */

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

  const leftClean = leftWords.map(normalizeWord).filter(Boolean)
  const rightClean = rightWords.map(normalizeWord).filter(Boolean)
  if (!leftClean.length || !rightClean.length) return 0

  let overlap = 0
  const maxCheck = Math.min(leftClean.length, rightClean.length, maxWords)

  for (let size = maxCheck; size >= 1; size -= 1) {
    const tail = leftClean.slice(-size).join(' ')
    const head = rightClean.slice(0, size).join(' ')
    if (tail === head) {
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
  }

  public commitCurrent(): void {
    if (this.uncommittedInterim) {
      this.committedText = `${this.committedText}${this.uncommittedInterim}`
      this.uncommittedInterim = ''
    }
  }

  /**
   * Process an incoming speech segment (interim or final) and compute the exact
   * keyboard delta (how many backspaces to press, and what text to type).
   */
  public processSegment(rawIncoming: string, isFinal: boolean): TypingDelta {
    const raw = rawIncoming.trim()
    if (!raw) {
      return {
        eraseCount: 0,
        appendText: '',
        committedText: this.committedText,
        uncommittedInterim: this.uncommittedInterim,
      }
    }

    // Step 1: Strip any tail overlap with committed text
    const { cleanText } = stripCommittedOverlap(this.committedText, raw)

    if (!cleanText && !isFinal) {
      return {
        eraseCount: 0,
        appendText: '',
        committedText: this.committedText,
        uncommittedInterim: this.uncommittedInterim,
      }
    }

    const previousInterim = this.uncommittedInterim
    const targetInterim = cleanText

    if (previousInterim === targetInterim && !isFinal) {
      return {
        eraseCount: 0,
        appendText: '',
        committedText: this.committedText,
        uncommittedInterim: this.uncommittedInterim,
      }
    }

    // Step 2: Compute delta against uncommittedInterim ONLY (never touch committedText!)
    let commonPrefixLen = 0
    const minLen = Math.min(previousInterim.length, targetInterim.length)
    for (let i = 0; i < minLen; i++) {
      if (previousInterim[i] === targetInterim[i]) {
        commonPrefixLen++
      } else {
        break
      }
    }

    const eraseCount = previousInterim.length - commonPrefixLen
    const appendText = targetInterim.slice(commonPrefixLen)

    if (isFinal) {
      // Finalize this segment into committedText and reset uncommittedInterim
      this.committedText = `${this.committedText}${targetInterim}`
      this.uncommittedInterim = ''
    } else {
      this.uncommittedInterim = targetInterim
    }

    return {
      eraseCount,
      appendText,
      committedText: this.committedText,
      uncommittedInterim: this.uncommittedInterim,
    }
  }
}
