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
  if (levenshtein(wa, wb) <= maxDist) return true
  return false
}

function wordSim(a: string, b: string): number {
  const dist = levenshtein(normalize(a), normalize(b))
  const maxLen = Math.max(a.length, b.length)
  return maxLen > 0 ? 1 - dist / maxLen : 0
}

function tokenize(text: string): string[] {
  return text.split(/\s+/).filter(w => w.length > 0).map(w =>
    w.replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}']+$/gu, '')
  ).filter(w => w.length > 0)
}

const t1 = "But let's openThat's how Windows are in Germany, okayNahin why there is fun on this weekend that means we get 20% in the supermarket from this so premium back. I get money from an empty crackers. Let's make some base song. not feeling too well which team do you want we have all the kind of thing which will help you meet my new german friend alex you are not friends."
const t2 = "it's hard let's open the windows like this and how to close it just put it down nahin chahiye don't you like why there is fun on this well that means we get 20% in the supermarket from this so bring it back i get money from an empty case if let's make some faisala which do you want we have all the kind of thing which will help you let's see some sweets builder quarter swarts what we we are famous for that meet my new german friend alex you are not friends."
const t3 = "that's how windows are in germany OK call you by putting it like this and how do you close it just put it down nahin why there is fun on this will that means we get 20% in the supermarket from this so bring it back i get money from an empty canvas god let's make some basarab i'm not feeling too well let's eat some swap with authority swarts what shweta daughter we are famous for that meet my new german alex you are not friends."

const tok1 = tokenize(t1)
const tok2 = tokenize(t2)
const tok3 = tokenize(t3)

const tokenized = [tok1, tok2, tok3]

// Build clusters manually
const clusters: { word: string; entries: { sourceIdx: number; position: number }[] }[] = []

for (let si = 0; si < tokenized.length; si++) {
  const tokens = tokenized[si]
  const sourceClusters = new Set<number>()

  for (let wi = 0; wi < tokens.length; wi++) {
    const word = tokens[wi]

    let bestIdx = -1
    let bestSim = 0
    for (let ci = 0; ci < clusters.length; ci++) {
      if (sourceClusters.has(ci)) continue
      const sim = wordSim(word, clusters[ci].word)
      if (sim >= 0.5 && sim > bestSim) {
        bestSim = sim
        bestIdx = ci
      }
    }

    if (bestIdx >= 0) {
      clusters[bestIdx].entries.push({ sourceIdx: si, position: wi })
      sourceClusters.add(bestIdx)
      if (word.length > clusters[bestIdx].word.length) {
        clusters[bestIdx].word = word
      }
    }
  }
}

console.log('Total clusters:', clusters.length)
console.log('Clusters with 2+ sources:', clusters.filter(c => new Set(c.entries.map(e => e.sourceIdx)).size >= 2).length)
console.log()

const multiSource = clusters
  .filter(c => new Set(c.entries.map(e => e.sourceIdx)).size >= 2)
  .map(c => {
    const sources = new Set(c.entries.map(e => e.sourceIdx))
    const avgPos = c.entries.reduce((a, e) => a + e.position, 0) / c.entries.length
    return { word: c.word, count: sources.size, avgPos }
  })
  .sort((a, b) => a.avgPos - b.avgPos)

console.log('Consensus words (2+ sources):', multiSource.length)
console.log(multiSource.slice(0, 60).map(c => `  "${c.word}" (${c.count} src, pos ~${c.avgPos.toFixed(1)})`).join('\n'))
