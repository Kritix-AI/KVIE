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

    // 3. Word-level homophone and contextual confusion resolution
    for (const rule of TokenEngine.HOMOPHONE_RULES) {
      result = result.replace(rule.pattern, rule.replacement)
    }

    // 4. Standalone pronoun capitalization (i, i'm, i've, i'll, i'd)
    result = result
      .replace(/\bi\b/g, 'I')
      .replace(/\bi'm\b/gi, "I'm")
      .replace(/\bi've\b/gi, "I've")
      .replace(/\bi'll\b/gi, "I'll")
      .replace(/\bi'd\b/gi, "I'd")

    return result
  }
}

// ──────────────── Tier 2: Sentence Engine (Grammar, Structure & Tense) ────────────────
export class SentenceEngine {
  private static GRAMMAR_RULES: Array<{ pattern: RegExp; replacement: string | ((match: string, ...args: any[]) => string) }> = [
    // Articles: an before vowels, a before consonants
    { pattern: /\b(a)\s+([aeiou][a-z]+)\b/gi, replacement: 'an $2' },
    { pattern: /\b(an)\s+([bcdfghjklmnpqrstvwxyz][a-z]+)\b/gi, replacement: 'a $2' },
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
      if (typeof rule.replacement === 'string') {
        result = result.replace(rule.pattern, rule.replacement)
      } else {
        result = result.replace(rule.pattern, rule.replacement as any)
      }
    }

    // Subject-verb agreement (singular third-person: he go -> he goes)
    result = result.replace(/\b(he|she|it)\s+(go|do|have|make|take|see|come|know|get|give|find|think|tell|say)\b/gi, (_, subject, verb) => {
      const v = verb.toLowerCase()
      let conjugated = v + 's'
      if (v === 'go') conjugated = 'goes'
      else if (v === 'do') conjugated = 'does'
      else if (v === 'have') conjugated = 'has'
      return `${subject} ${conjugated}`
    })

    // Sentence-boundary capitalization & spacing
    const sentences = result.split(/(?<=[.!?\n])\s+/).map(sentence => {
      const trimmed = sentence.trim()
      if (!trimmed) return ''
      return trimmed.charAt(0).toUpperCase() + trimmed.slice(1)
    })

    return sentences.filter(Boolean).join(' ')
  }
}

// ──────────────── Tier 3: Paragraph Engine (Coherence & Flow) ────────────────
export class ParagraphEngine {
  static process(text: string): string {
    if (!text.trim()) return ''

    let result = text

    // Remove duplicate consecutive duplicate words (e.g. "the the" -> "the")
    result = result.replace(/\b(\w+)\s+\1\b/gi, '$1')

    // Clean up conversational restart fragments (e.g. "at 5... wait 6" -> "at 6")
    result = result.replace(/(\b\w+\b)\s+(\.\.\.|—|-)\s+(actually|wait|i mean|no)\s+/gi, '')

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
    result = result.replace(/([,.:;?!])([a-zA-Z])/g, '$1 $2')
    result = result.replace(/\s+/g, ' ').trim()

    // Ensure sentence ending punctuation if >= 3 words
    const words = result.split(' ')
    if (words.length >= 3 && !/[.!?]$/.test(result)) {
      result = `${result}.`
    }

    return result
  }
}

// ──────────────── Grammar Router Master Orchestrator ────────────────
export async function runGrammarRouter(
  text: string,
  options: GrammarRouterOptions = {}
): Promise<string> {
  const { enabled = true } = options

  // If disabled in settings, return raw text trimmed
  if (!enabled || !text.trim()) {
    return text.trim()
  }

  // 1. Stage 1: Token Engine (0ms Typo & Casing & Homophones)
  const tokenStage = TokenEngine.process(text)

  // 2. Stage 2: Sentence Engine (Grammar, Agreement, Articles)
  const sentenceStage = SentenceEngine.process(tokenStage)

  // 3. Stage 3: Paragraph Engine (Coherence & Flow)
  const paragraphStage = ParagraphEngine.process(sentenceStage)

  // 4. Stage 4: Final Editor (Formatting, Punctuation, Integrity)
  const finalResult = FinalEditor.process(paragraphStage)

  return finalResult
}
