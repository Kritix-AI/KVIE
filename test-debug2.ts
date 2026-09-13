import { isWordMatch } from './src/lib/consensusEngine.ts'

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

function normalize(w: string): string {
  return w.toLowerCase().replace(/[^\p{L}\p{N}]/gu, '')
}

function tokenize(text: string): string[] {
  return text.split(/\s+/).filter(w => w.length > 0).map(w =>
    w.replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, '')
  ).filter(w => w.length > 0)
}

const t1 = "But let's openThat's how Windows are in Germany, okayNahin why there is fun on this weekend that means we get 20% in the supermarket from this so premium back. I get money from an empty crackers. Let's make some base song. not feeling too well which team do you want we have all the kind of thing which will help you meet my new german friend alex you are not friends."
const t2 = "it's hard let's open the windows like this and how to close it just put it down nahin chahiye don't you like why there is fun on this well that means we get 20% in the supermarket from this so bring it back i get money from an empty case if let's make some faisala which do you want we have all the kind of thing which will help you let's see some sweets builder quarter swarts what we we are famous for that meet my new german friend alex you are not friends."
const t3 = "that's how windows are in germany OK call you by putting it like this and how do you close it just put it down nahin why there is fun on this will that means we get 20% in the supermarket from this so bring it back i get money from an empty canvas god let's make some basarab i'm not feeling too well let's eat some swap with authority swarts what shweta daughter we are famous for that meet my new german alex you are not friends."

const tok1 = tokenize(t1)
const tok2 = tokenize(t2)
const tok3 = tokenize(t3)

console.log('Reference (t1) length:', tok1.length)
console.log('Source 2 (t2) length:', tok2.length)
console.log('Source 3 (t3) length:', tok3.length)
console.log()

// Try a simple greedy alignment: for each word in reference, find best match in source
function greedyAlign(ref: string[], src: string[]): { refWord: string; srcWord: string }[] {
  const result: { refWord: string; srcWord: string }[] = []
  let srcIdx = 0

  for (const rw of ref) {
    // Find best match in remaining source words
    let bestMatch: { idx: number; sim: number } | null = null
    for (let i = srcIdx; i < Math.min(srcIdx + 5, src.length); i++) {
      const nx = normalize(rw)
      const ny = normalize(src[i])
      const dist = levenshtein(nx, ny)
      const maxLen = Math.max(nx.length, ny.length)
      const sim = maxLen > 0 ? 1 - dist / maxLen : 0
      if (sim >= 0.4 && (!bestMatch || sim > bestMatch.sim)) {
        bestMatch = { idx: i, sim }
      }
    }

    if (bestMatch) {
      result.push({ refWord: rw, srcWord: src[bestMatch.idx] })
      srcIdx = bestMatch.idx + 1
    } else {
      result.push({ refWord: rw, srcWord: '' })
    }
  }

  return result
}

// Try with a more lenient approach first
const aligned2 = greedyAlign(tok1, tok2)
const aligned3 = greedyAlign(tok1, tok3)

// Now vote
console.log('Position-by-position voting:')
let count = 0
for (let i = 0; i < Math.min(aligned2.length, aligned3.length); i++) {
  const a = aligned2[i]
  const b = aligned3[i]
  const rw = a.refWord

  // Check which source words match this reference word
  const match2 = a.srcWord && isWordMatch(rw, a.srcWord) ? a.srcWord : null
  const match3 = b.srcWord && isWordMatch(rw, b.srcWord) ? b.srcWord : null

  const votes = [rw, match2, match3].filter(Boolean).length

  if (votes >= 2) {
    count++
    const alternatives = [match2, match3].filter(w => w && !isWordMatch(rw, w))
    if (alternatives.length > 0) {
      console.log(`  pos ${i}: "${rw}" (${votes}/3) ← alt: ${alternatives.join(', ')}`)
    }
  }
}
console.log(`Words with majority votes: ${count}`)
