function normalize(w: string): string {
  return w.toLowerCase().replace(/[^\p{L}\p{N}]/gu, '')
}

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

export function isWordMatch(a: string, b: string): boolean {
  const wa = a.toLowerCase(), wb = b.toLowerCase()
  if (wa === wb) return true
  const maxDist = Math.max(1, Math.floor(Math.min(wa.length, wb.length) * 0.35))
  return levenshtein(wa, wb) <= maxDist
}

function tokenize(text: string): string[] {
  return text.split(/\s+/).filter(w => w.length > 0).map(w =>
    w.replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}']+$/gu, '')
  ).filter(w => w.length > 0)
}

const CONTRACTIONS: Record<string, string[]> = {
  "let's": ["let", "'s"], "that's": ["that", "'s"], "it's": ["it", "'s"],
  "i'm": ["i", "'m"], "don't": ["don", "'t"], "doesn't": ["doesn", "'t"],
}

function splitWord(token: string): string[] {
  const lower = token.toLowerCase()
  if (CONTRACTIONS[lower]) {
    console.log(`CONTRACTION MATCH: "${token}" → [${CONTRACTIONS[lower].map(x => `"${x}"`).join(', ')}]`)
    return CONTRACTIONS[lower]
  }
  return [token]
}

const raw = "But let's openThat's how Windows are"
const tokens = raw.split(/\s+/).filter(w => w.length > 0)

for (const token of tokens) {
  const parts = splitWord(token)
  for (const p of parts) {
    const cleaned = p.replace(/^[^\p{L}\p{N}']+|[^\p{L}\p{N}']+$/gu, '')
    console.log(`  "${token}" → part "${p}" → cleaned "${cleaned}"`)
  }
}
