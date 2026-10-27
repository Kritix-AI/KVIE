/**
 * KVIE Multi-Tier Grammar Router Pipeline
 *
 * Architecture:
 *           │ Grammar Router │
 *           └───────┬────────┘
 *                   │
 *        ┌──────────┼──────────┐
 *        ▼          ▼          ▼
 *     TOKEN       SENTENCE   PARAGRAPH
 *     ENGINE       ENGINE      ENGINE
 *        │          │          │
 *        ▼          ▼          ▼
 *    Spelling    Grammar     Context
 *    Typo        Structure   Coherence
 *    Casing      Tense       Flow
 *        │          │          │
 *        └──────────┼──────────┘
 *                   ▼
 *              FINAL EDITOR
 *                   │
 *                   ▼
 *            Corrected Text
 */

export interface GrammarRouterOptions {
  enabled?: boolean
  style?: 'standard' | 'formal' | 'concise'
  preserveHinglish?: boolean
  surroundingContext?: string
}

// ──────────────── Tier 1: Token Engine (Ultra-Fast 0ms Pre-LLM) ────────────────
export class TokenEngine {
  private static TYPO_MAP: Record<string, string> = {
    // Common letter-level typos
    teh: 'the',
    recieve: 'receive',
    seperate: 'separate',
    definately: 'definitely',
    occured: 'occurred',
    untill: 'until',
    truely: 'truly',
    whcih: 'which',
    wierd: 'weird',
    accomodate: 'accommodate',
    tommorow: 'tomorrow',
    neccessary: 'necessary',
    goverment: 'government',
    arguement: 'argument',
    enviroment: 'environment',
    beleive: 'believe',
    calender: 'calendar',
    critics: 'Kritix',
    critic: 'Kritix',
    critcs: 'Kritix',
    kritics: 'Kritix',
    kritik: 'Kritix',
    kritiks: 'Kritix',
    kritic: 'Kritix',
    critis: 'Kritix',
    Kritcs: 'Kritix',
    kritcs: 'Kritix',
    kritix: 'Kritix',
    kvie: 'KVIE',
  }

  // Common word-level homophone & confusion contextual replacements
  private static HOMOPHONE_RULES: Array<{ pattern: RegExp; replacement: string }> = [
    // Their / They're / There
    { pattern: /\b(their)\s+(going|coming|leaving|working|doing|running|trying|making|feeling|happy|ready|sure|online)\b/gi, replacement: "they're $2" },
    { pattern: /\b(they're|there)\s+(house|car|office|team|code|project|family|time|idea|work|opinion)\b/gi, replacement: "their $2" },
    { pattern: /\b(their)\s+(is|are|was|were|will|can|could|should|must|has|have)\b/gi, replacement: "there $2" },
    // Your / You're
    { pattern: /\b(your)\s+(welcome|right|wrong|going|coming|doing|making|smart|invited|ready|sure)\b/gi, replacement: "you're $2" },
    { pattern: /\b(you're)\s+(house|car|phone|name|email|code|message|work|turn|time)\b/gi, replacement: "your $2" },
    // Its / It's
    { pattern: /\b(its)\s+(a|an|the|my|your|his|her|our|their|going|been|working|ready|done|cool|good|bad|fine)\b/gi, replacement: "it's $2" },
    // To / Too / Two
    { pattern: /\b(to)\s+(much|many|late|fast|slow|bad|good|expensive|hard|easy)\b/gi, replacement: "too $2" },
    // Then / Than
    { pattern: /\b(more|less|better|worse|greater|smaller|faster|slower|earlier|later|higher|lower)\s+(then)\b/gi, replacement: "$1 than" },
    // Affect / Effect
    { pattern: /\b(will|can|could|should|would|might|to)\s+(effect)\b/gi, replacement: "$1 affect" },
    { pattern: /\b(the|a|an|direct|negative|positive)\s+(affect)\b/gi, replacement: "$1 effect" },
    // Lose / Loose
    { pattern: /\b(to|will|might|don't)\s+(loose)\b/gi, replacement: "$1 lose" },
  ]

  static process(text: string): string {
    if (!text.trim()) return ''

    let result = text

    // 1. Squash exaggerated character repetitions (e.g. "sooooo" -> "so", "helllooo" -> "hello")
    result = result.replace(/([a-zA-Z])\1{2,}/g, '$1')

    // 2. Token-by-token spelling & typo dictionary lookup
    result = result.replace(/\b[a-zA-Z]+\b/g, match => {
      const lower = match.toLowerCase()
      const replacement = TokenEngine.TYPO_MAP[lower] || TokenEngine.TYPO_MAP[match]
      if (replacement) {
        // Preserve title case if original was capitalized
        if (match[0] === match[0].toUpperCase() && match.length > 1 && match[1] === match[1].toLowerCase()) {
          return replacement.charAt(0).toUpperCase() + replacement.slice(1)
        }
        if (match === match.toUpperCase()) {
          return replacement.toUpperCase()
        }
        return replacement
      }
      return match
    })

    // 3. Standalone pronoun capitalization (i, i'm, i've, i'll, i'd)
    result = result
      .replace(/\bi\b/g, 'I')
      .replace(/\bi'm\b/gi, "I'm")
      .replace(/\bi've\b/gi, "I've")
      .replace(/\bi'll\b/gi, "I'll")
      .replace(/\bi'd\b/gi, "I'd")

    return result
  }

  /**
   * Light-touch processing: only squash repeats + typo fixes.
   * Skips homophone rules that can corrupt correct speech (e.g. "to" -> "too").
   */
  static safeProcess(text: string): string {
    if (!text.trim()) return ''

    let result = text

    // 1. Squash exaggerated character repetitions (e.g. "sooooo" -> "so")
    result = result.replace(/([a-zA-Z])\1{2,}/g, '$1')

    // 2. Only fix known unambiguous typos from the dictionary
    result = result.replace(/\b[a-zA-Z]+\b/g, match => {
      const lower = match.toLowerCase()
      const replacement = TokenEngine.TYPO_MAP[lower]
      if (replacement) {
        if (match[0] === match[0].toUpperCase() && match.length > 1 && match[1] === match[1].toLowerCase()) {
          return replacement.charAt(0).toUpperCase() + replacement.slice(1)
        }
        if (match === match.toUpperCase()) {
          return replacement.toUpperCase()
        }
        return replacement
      }
      return match
    })

    return result
  }
}

// ──────────────── Tier 2: Sentence Engine (Grammar, Structure & Tense) ────────────────
// Words that look like they take the other article but don't ("an hour",
// "a university") — without these the rules corrupt correct English on every
// dictation.
const A_EXCEPTIONS = /^(uni|use|us|user|used|useful|useless|usual|usually|one|once|euro|european|eulogy|utensil|unit|united|university|universal|universe|ubiquitous|ukrainian|unicorn|union|unique)/i
const AN_EXCEPTIONS = /^(hour|hourly|honest|honestly|honor|honour|honorable|honourable|heir|herb|mba|fbi|honorarium)/i

export class SentenceEngine {
  private static GRAMMAR_RULES: Array<{ pattern: RegExp; replacement: string | ((substring: string, ...args: any[]) => string) }> = [
    // Articles: an before vowel sounds, a before consonant sounds — with
    // exception lists so correct text is never rewritten.
    {
      pattern: /\ba\s+([aeiou][a-zA-Z]*)\b/gi,
      replacement: (substring: string, word: string) => (A_EXCEPTIONS.test(word) ? substring : `an ${word}`),
    },
    {
      pattern: /\ban\s+([bcdfghjklmnpqrstvwxyz][a-zA-Z]*)\b/gi,
      replacement: (substring: string, word: string) => (AN_EXCEPTIONS.test(word) ? substring : `a ${word}`),
    },
    // Prepositions
    { pattern: /\binterested\s+on\b/gi, replacement: 'interested in' },
    { pattern: /\bcongratulations\s+for\b/gi, replacement: 'congratulations on' },
    { pattern: /\bdiscuss\s+about\b/gi, replacement: 'discuss' },
    { pattern: /\bexplain\s+about\b/gi, replacement: 'explain' },
    { pattern: /\bmarried\s+with\b/gi, replacement: 'married to' },
    { pattern: /\bdepend\s+of\b/gi, replacement: 'depend on' },
    // Common spoken contractions
    { pattern: /\bgonna\b/gi, replacement: 'going to' },
    { pattern: /\bwanna\b/gi, replacement: 'want to' },
    { pattern: /\bkinda\b/gi, replacement: 'kind of' },
  ]

  static process(text: string): string {
    if (!text.trim()) return ''

    let result = text

    for (const rule of SentenceEngine.GRAMMAR_RULES) {
      result = result.replace(rule.pattern, rule.replacement as string)
    }

    // Sentence-boundary capitalization, preserving the original whitespace and
    // newlines (the previous split+join collapsed multi-line text into one line).
    return result.replace(/(^|[.!?]\s+|\n\s*)([a-z])/g, (_match, prefix: string, letter: string) => prefix + letter.toUpperCase())
  }

  /**
   * Light cleanup: only capitalization, no grammar rule rewrites.
   */
  static cleanupOnly(text: string): string {
    if (!text.trim()) return ''
    const trimmed = text.trim()
    return trimmed.charAt(0).toUpperCase() + trimmed.slice(1)
  }
}

// ──────────────── Tier 3: Paragraph Engine (Coherence & Flow) ────────────────
export class ParagraphEngine {
  static process(text: string): string {
    if (!text.trim()) return ''

    let result = text

    // Only collapse duplicate function words (not content words like names, verbs, etc.)
    // "the the" -> "the" but NOT "hello hello" -> "hello"
    result = result.replace(/\b(the|a|an|and|or|but|is|are|was|were|be|been|to|of|in|on|at|for|with|from|by|it|that|this)\s+\1\b/gi, '$1')

    // Clean up conversational restart fragments (e.g. "at 5... wait 6" -> "at 6")
    result = result.replace(/(\b\w+\b)\s+(\.{2,}|—|-+)\s+(actually|wait|i mean|no)\s+/gi, '')

    // Connect paragraph sentences smoothly
    result = result.replace(/\s*;\s*/g, '; ')
    result = result.replace(/\s*:\s*/g, ': ')

    return result
  }
}

// ──────────────── Tier 4: Final Editor ────────────────
export class FinalEditor {
  static process(text: string): string {
    if (!text.trim()) return ''

    let result = text

    // Normalize whitespace around punctuation
    result = result.replace(/\s+([,.:;?!])/g, '$1')
    result = result.replace(/([,.:;?!])([a-zA-Z])/g, (match, punct: string, letter: string) => {
      // A period followed by a lowercase letter is part of an abbreviation or
      // domain ("e.g.", "node.js") — never split those.
      if (punct === '.' && letter === letter.toLowerCase()) return match
      return `${punct} ${letter}`
    })
    // Collapse runs of spaces/tabs but PRESERVE newlines.
    result = result.replace(/[^\S\n]+/g, ' ').trim()

    // Ensure sentence ending punctuation if >= 3 words
    const words = result.split(' ')
    if (words.length >= 3 && !/[.!?]$/.test(result)) {
      result = `${result}.`
    }

    return result
  }

  /**
   * Conservative whitespace normalization only.
   */
  static normalizeWhitespace(text: string): string {
    if (!text.trim()) return ''
    return text.replace(/\s+/g, ' ').trim()
  }
}

// ──────────────── Grammar Router Master Orchestrator ────────────────
export async function runGrammarRouter(
  text: string,
  options: GrammarRouterOptions = {}
): Promise<string> {
  if (!text.trim()) return text.trim()
  const { enabled = true } = options
  if (!enabled) return text.trim()

  // Stage 1: Light-touch typo fixes only (no homophones, no rewrites)
  const tokenStage = TokenEngine.safeProcess(text)

  // Stage 2: Sentence cleanup (capitalization only — no grammar rewrites)
  const sentenceStage = SentenceEngine.cleanupOnly(tokenStage)

  // Stage 3: Whitespace normalization
  return FinalEditor.normalizeWhitespace(sentenceStage)
}
