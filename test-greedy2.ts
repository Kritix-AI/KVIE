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

function wordSim(a: string, b: string): number {
  if (a.toLowerCase() === b.toLowerCase()) return 1.0
  const dist = levenshtein(normalize(a), normalize(b))
  const maxLen = Math.max(a.length, b.length)
  return maxLen > 0 ? 1 - dist / maxLen : 0
}

const t1 = "But let's openThat's how Windows are in Germany, okayNahin why there is fun on this weekend that means we get 20% in the supermarket from this so premium back. I get money from an empty crackers. Let's make some base song. not feeling too well which team do you want we have all the kind of thing which will help you meet my new german friend alex you are not friends."
const t2 = "it's hard let's open the windows like this and how to close it just put it down nahin chahiye don't you like why there is fun on this well that means we get 20% in the supermarket from this so bring it back i get money from an empty case if let's make some faisala which do you want we have all the kind of thing which will help you let's see some sweets builder quarter swarts what we we are famous for that meet my new german friend alex you are not friends."
const t3 = "that's how windows are in germany OK call you by putting it like this and how do you close it just put it down nahin why there is fun on this will that means we get 20% in the supermarket from this so bring it back i get money from an empty canvas god let's make some basarab i'm not feeling too well let's eat some swap with authority swarts what shweta daughter we are famous for that meet my new german alex you are not friends."

const tok1 = tokenize(t1)
const tok2 = tokenize(t2)
const tok3 = tokenize(t3)

console.log('tok1:', tok1.join(' | '))
console.log('tok2:', tok2.join(' | '))
console.log('tok3:', tok3.join(' | '))
console.log()

// Sort by length (longest = reference)
const sources = [tok1, tok2, tok3].sort((a, b) => b.length - a.length)
const ref = sources[0]
const other1 = sources[1]
const other2 = sources[2]
console.log(`Reference: ${ref.length} words (source ${sources.indexOf(tok1)})`)
console.log(`Other 1:  ${other1.length} words (source ${sources.indexOf(tok2)})`)
console.log(`Other 2:  ${other2.length} words (source ${sources.indexOf(tok3)})`)
console.log()

// Greedy alignment with window
function greedyAlign(ref: string[], src: string[], windowSize: number) {
  const aligned: { ref: string; src: string }[] = []
  let srcIdx = 0

  for (const rw of ref) {
    let bestJ = -1
    let bestSim = 0.3
    const start = Math.max(0, srcIdx - 2)
    const end = Math.min(src.length, srcIdx + windowSize)

    for (let j = start; j < end; j++) {
      const s = wordSim(rw, src[j])
      if (s > bestSim) { bestSim = s; bestJ = j }
    }

    if (bestJ >= 0) {
      aligned.push({ ref: rw, src: src[bestJ] })
      srcIdx = bestJ + 1
    } else {
      aligned.push({ ref: rw, src: '' })
    }
  }

  return aligned
}

// Window 12
console.log('=== Window 12 ===')
const a1 = greedyAlign(ref, other1, 12)
const a2 = greedyAlign(ref, other2, 12)

let match12 = 0, match13 = 0
for (let i = 0; i < ref.length; i++) {
  const m1 = a1[i].src && a1[i].src.length > 0 ? a1[i].src : '(gap)'
  const m2 = a2[i].src && a2[i].src.length > 0 ? a2[i].src : '(gap)'
  if (a1[i].src) match12++
  if (a2[i].src) match13++
}
console.log(`Matched src2: ${match12}/${ref.length}`)
console.log(`Matched src3: ${match13}/${ref.length}`)
console.log()

// Show detailed alignment for first 60 positions
console.log('Detailed alignment (first 60 ref positions):')
for (let i = 0; i < Math.min(ref.length, 60); i++) {
  const votes = [a1[i].src, a2[i].src].filter(s => s && s.length > 0).length
  const m1 = a1[i].src || '(gap)'
  const m2 = a2[i].src || '(gap)'
  console.log(`${String(i).padStart(3)} | ${ref[i].padEnd(15)} | src2: ${m1.padEnd(15)} | src3: ${m2.padEnd(15)} | votes: ${votes}`)
}
