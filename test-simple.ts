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

function isWordMatch(a: string, b: string): boolean {
  const wa = a.toLowerCase(), wb = b.toLowerCase()
  if (wa === wb) return true
  const maxDist = Math.max(1, Math.floor(Math.min(wa.length, wb.length) * 0.35))
  return levenshtein(wa, wb) <= maxDist
}

function wordSim(a: string, b: string): number {
  if (isWordMatch(a, b)) {
    const dist = levenshtein(normalize(a), normalize(b))
    return 1 - dist / Math.max(a.length, b.length)
  }
  return 0
}

function tokenize(text: string): string[] {
  return text.split(/\s+/).filter(w => w.length > 0).map(w =>
    w.replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, '')
  ).filter(w => w.length > 0)
}

const t1 = "But let's openThat's how Windows are in Germany, okayNahin why there is fun on this weekend that means we get 20% in the supermarket from this so premium back. I get money from an empty crackers. Let's make some base song. not feeling too well which team do you want we have all the kind of thing which will help you meet my new german friend alex you are not friends."
const t2 = "it's hard let's open the windows like this and how to close it just put it down nahin chahiye don't you like why there is fun on this well that means we get 20% in the supermarket from this so bring it back i get money from an empty case if let's make some faisala which do you want we have all the kind of thing which will help you let's see some sweets builder quarter swarts what we we are famous for that meet my new german friend alex you are not friends."

const tok1 = tokenize(t1)
const tok2 = tokenize(t2)

// Align using the simple matching approach
const m = tok1.length, n = tok2.length
console.log('Ref length:', m, 'Source length:', n)

// Build alignment: for each ref word, find best match in src
const alignedB: string[] = []
let srcIdx = 0
let matched = 0

for (let i = 0; i < m; i++) {
  // Look ahead up to 3 words in source
  let bestJ = -1
  let bestSim = 0
  for (let j = srcIdx; j < Math.min(srcIdx + 4, n); j++) {
    const s = wordSim(tok1[i], tok2[j])
    if (s > bestSim) { bestSim = s; bestJ = j }
  }

  if (bestJ >= 0 && bestSim >= 0.35) {
    alignedB.push(tok2[bestJ])
    srcIdx = bestJ + 1
    matched++
  } else {
    alignedB.push('')
  }
}

console.log('Matched positions:', matched, '/', m)
console.log()

// Now vote
const minVotes = 2  // ceil(2/2) = 1, but we want at least 1 from source
const result: string[] = []
for (let i = 0; i < m; i++) {
  const rw = tok1[i]
  const sw = alignedB[i]

  const matchesRef = rw
  const hasSource = sw && sw.length > 0 && isWordMatch(rw, sw)

  if (hasSource || rw.length > 4) {
    if (result.length > 0 && isWordMatch(rw, result[result.length - 1])) continue
    result.push(rw)
  }
}

console.log('Result:', result.join(' '))
console.log('Result words:', result.length)
