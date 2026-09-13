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

function normalize(w: string): string {
  return w.toLowerCase().replace(/[^\p{L}\p{N}]/gu, '')
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

console.log('tok1:', tok1.length, 'tokens')
console.log('tok2:', tok2.length, 'tokens')
console.log('tok3:', tok3.length, 'tokens')
console.log()

// Greedy align tok1 against tok2
function greedyAlign(ref: string[], src: string[], windowSize = 4) {
  const aligned: { ref: string; src: string; srcIdx: number }[] = []
  let srcIdx = 0

  for (const rw of ref) {
    let bestJ = -1
    let bestSim = 0.3

    const start = Math.max(0, srcIdx - 1)
    const end = Math.min(src.length, srcIdx + windowSize)

    for (let j = start; j < end; j++) {
      const s = wordSim(rw, src[j])
      if (s > bestSim) {
        bestSim = s
        bestJ = j
      }
    }

    if (bestJ >= 0) {
      aligned.push({ ref: rw, src: src[bestJ], srcIdx: bestJ })
      srcIdx = bestJ + 1
    } else {
      aligned.push({ ref: rw, src: '', srcIdx: srcIdx })
    }
  }

  return aligned
}

const aligned2 = greedyAlign(tok1, tok2)
const aligned3 = greedyAlign(tok1, tok3)

// Show first 40 aligned positions
console.log('Pos | Reference           | Source 2 match    | Source 3 match')
console.log('----|---------------------|-------------------|----------------')
for (let i = 0; i < Math.min(tok1.length, 40); i++) {
  const a2 = aligned2[i]
  const a3 = aligned3[i]
  const match2 = a2.src && a2.src.length > 0 ? a2.src : '(no match)'
  const match3 = a3.src && a3.src.length > 0 ? a3.src : '(no match)'
  console.log(`${String(i).padStart(3)} | ${a2.ref.padEnd(19)} | ${match2.padEnd(17)} | ${match3}`)
}

console.log()
console.log('Matched positions in src2:', aligned2.filter(a => a.src.length > 0).length, '/', tok1.length)
console.log('Matched positions in src3:', aligned3.filter(a => a.src.length > 0).length, '/', tok1.length)
