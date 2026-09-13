/**
 * KVIE Consensus Transcription Engine
 *
 * Strategy: Use the longest transcription as the reference order,
 * then validate each word against all other sources using fuzzy matching.
 * Words only survive if supported by majority or if they're the best fuzzy match.
 */

function levenshtein(a: string, b: string): number {
  if (a.length === 0) return b.length
  if (b.length === 0) return a.length
  const prev = new Array(b.length + 1).fill(0)
  const curr = new Array(b.length + 1).fill(0)
  for (let j = 0; j <= b.length; j++) prev[j] = j
  for (let i = 1; i <= a.length; i++) {
    curr[0] = i
    for (let j = 1; j <= b.length; j++) {
      if (a[i - 1] === b[j - 1]) curr[j] = prev[j - 1]
      else curr[j] = 1 + Math.min(prev[j - 1], prev[j], curr[j - 1])
    }
    for (let k = 0; k <= b.length; k++) prev[k] = curr[k]
  }
  return curr[b.length]
}

function isWordMatch(a: string, b: string): boolean {
  const wa = a.toLowerCase(), wb = b.toLowerCase()
  if (wa === wb) return true
  const maxLen = Math.max(wa.length, wb.length)
  if (maxLen <= 3) return wa === wb
  const maxDist = Math.floor(Math.min(wa.length, wb.length) * 0.35)
  return levenshtein(wa, wb) <= maxDist
}

function tokenize(text: string): string[] {
  const raw = text.split(/\s+/).filter(w => w.length > 0)
  const result: string[] = []
  for (const token of raw) {
    const capMatch = token.match(/^([a-z][a-z']*)([A-Z][A-Za-z']*)/)
    if (capMatch) {
      result.push(capMatch[1])
      result.push(capMatch[2].replace(/[.,!?;:]+$/gu, ''))
      continue
    }
    const cleaned = token.replace(/^[^\p{L}\p{N}']+|[^\p{L}\p{N}']+$/gu, '')
    if (cleaned.length > 0) result.push(cleaned)
  }
  return result
}

function findBestMatch(word: string, candidates: string[], preferred?: string): { word: string; dist: number } {
  let best = word
  let bestDist = 0
  for (const c of candidates) {
    if (c.length < 2) continue
    const d = levenshtein(word.toLowerCase(), c.toLowerCase())
    if (d < bestDist || bestDist === 0) {
      bestDist = d
      best = c
    }
  }
  // If we have a preferred alternative that matches better, use it
  if (preferred && isWordMatch(word, preferred)) {
    return { word: preferred, dist: 0 }
  }
  return { word: best, dist: bestDist }
}

export function consensusTranscription(transcriptions: string[]): string {
  if (transcriptions.length === 0) return ''
  if (transcriptions.length === 1) return transcriptions[0]

  const tokenized = transcriptions
    .map(t => tokenize(t))
    .filter(t => t.length > 0)

  if (tokenized.length === 0) return ''
  if (tokenized.length === 1) return tokenized[0].join(' ')

  // Pick the longest transcription as reference order
  tokenized.sort((a, b) => b.length - a.length)
  const reference = tokenized[0]
  const otherSources = tokenized.slice(1)

  const totalSources = transcriptions.length
  const minSupport = Math.ceil(totalSources / 2) // majority

  // For each word in reference, find best consensus version
  const result: string[] = []
  for (const refWord of reference) {
    // Count how many sources support this exact word
    let supportCount = 1 // reference itself
    let alternatives: string[] = []

    for (const source of otherSources) {
      const matchIdx = source.findIndex(w => isWordMatch(w, refWord))
      if (matchIdx >= 0) {
        supportCount++
        alternatives.push(source[matchIdx])
      }
    }

    if (supportCount >= minSupport) {
      // Word has majority support — use reference spelling
      result.push(refWord)
    } else {
      // Word not in majority — try to find best fuzzy match from other sources
      const allCandidates: string[] = []
      for (const source of otherSources) {
        allCandidates.push(...source)
      }
      const { word: bestWord, dist } = findBestMatch(refWord, allCandidates)

      // Count if bestWord is supported by majority
      let bestSupport = 0
      for (const source of tokenized) {
        if (source.find(w => isWordMatch(w, bestWord))) bestSupport++
      }

      if (bestSupport >= minSupport) {
        result.push(bestWord)
      } else if (dist <= Math.floor(refWord.length * 0.35)) {
        // Fuzzy match but no majority — still use best fuzzy
        result.push(bestWord)
      } else {
        // No support at all — keep reference word (it might be correct)
        result.push(refWord)
      }
    }
  }

  return result.join(' ')
}

export interface ConsensusReport {
  consensus: string
  words: Array<{
    word: string
    confidence: number
    alternatives: string[]
  }>
}

export function consensusReport(transcriptions: string[]): ConsensusReport {
  const consensus = consensusTranscription(transcriptions)
  const tokenized = transcriptions.map(t => tokenize(t))

  const words = consensus.split(/\s+/).map(word => {
    const matched: string[] = []
    for (const tokens of tokenized) {
      const m = tokens.find(t => isWordMatch(t, word))
      if (m) matched.push(m)
    }
    const unique = [...new Set(matched.map(w => w.toLowerCase()))]
    return {
      word,
      confidence: matched.length > 0 ? matched.length / transcriptions.length : 1,
      alternatives: unique.filter(w => !isWordMatch(w, word)),
    }
  })

  return { consensus, words }
}
