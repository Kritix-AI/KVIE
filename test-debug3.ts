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

function tokenize(text: string): string[] {
  return text.split(/\s+/).filter(w => w.length > 0).map(w =>
    w.replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}']+$/gu, '')
  ).filter(w => w.length > 0)
}

function wordSim(a: string, b: string): number {
  if (a.toLowerCase() === b.toLowerCase()) return 1.0
  const dist = levenshtein(normalize(a), normalize(b))
  const maxLen = Math.max(a.length, b.length)
  return maxLen > 0 ? 1 - dist / maxLen : 0
}

const t1 = "But let's openThat's how Windows are in Germany, okayNahin why there is fun on this weekend that means we get 20% in the supermarket from this so premium back."
const t2 = "it's hard let's open the windows like this and how to close it just put it down nahin chahiye don't you like why there is fun on this well that means we get 20% in the supermarket from this so bring it back"

const tok1 = tokenize(t1)
const tok2 = tokenize(t2)

console.log('t1:', tok1.join(' | '))
console.log('t2:', tok2.join(' | '))
console.log()

// Simulate clustering: source 1 creates clusters, source 2 joins them
const clusters: { word: string; src2joined: boolean; sim: number }[] = []

// Source 1 creates clusters
for (const w of tok1) {
  // Check if similar word already exists
  const existing = clusters.find(c => isWordMatch(c.word, w))
  if (existing) {
    if (w.length > existing.word.length) existing.word = w
  } else {
    clusters.push({ word: w, src2joined: false, sim: 0 })
  }
}

console.log('Clusters from source 1:', clusters.length)

// Source 2 tries to join
for (const w of tok2) {
  let bestIdx = -1
  let bestSim = 0
  for (let ci = 0; ci < clusters.length; ci++) {
    if (clusters[ci].src2joined) continue
    const sim = wordSim(w, clusters[ci].word)
    console.log(`  "${w}" vs "${clusters[ci].word}": sim=${sim.toFixed(3)}`)
    if (sim >= 0.5 && sim > bestSim) {
      bestSim = sim
      bestIdx = ci
    }
  }
  if (bestIdx >= 0) {
    clusters[bestIdx].src2joined = true
    if (w.length > clusters[bestIdx].word.length) clusters[bestIdx].word = w
    console.log(`  → JOINED cluster "${clusters[bestIdx].word}"`)
  }
}

const twoSource = clusters.filter(c => c.src2joined)
console.log()
console.log('Clusters with 2 sources:', twoSource.length)
console.log(twoSource.slice(0, 20).map(c => `  "${c.word}"`).join('\n'))
