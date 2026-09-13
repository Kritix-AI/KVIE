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

function splitConcatenated(word: string): string[] {
  const lower = word.toLowerCase()
  const COMMON_PREFIXES = new Set([
    'a','an','the','i','we','you','it','he','she','they',
    'is','am','are','was','were','have','has','had','do','did',
    'will','would','could','not','no','and','but','or','so','if',
    'what','when','where','who','why','how','my','your','his',
    'all','some','to','of','in','for','on','with','at','by','from',
    'let','open','close','just','put','down','that','this',
  ])
  const COMMON_SUFFIXES = new Set([
    's','es','ed','ing','ly','er','tion','open','close','down',
    'back','well','too','that','this','they','them','with',
    'windows','germany','weekend','supermarket','crackers',
    'friends','alex','premium','faisala','authority','shweta',
    'that\'s','it\'s','let\'s','don\'t',
  ])

  let bestSplit: string[] = [word]
  let bestScore = 0

  for (let i = 1; i < word.length; i++) {
    const left = word.slice(0, i)
    const right = word.slice(i)
    const leftN = normalize(left)
    const rightN = normalize(right)
    if (leftN.length < 2 || rightN.length < 2) continue
    if (!/[aeiou]/i.test(rightN) && rightN.length > 3) continue

    let score = 0
    if (COMMON_PREFIXES.has(leftN)) score += 2
    if (COMMON_SUFFIXES.has(rightN)) score += 2
    if (/[aeiou]/i.test(leftN) && /[aeiou]/i.test(rightN)) score += 1
    const balance = 1 - Math.abs(left.length - right.length) / (left.length + right.length)
    score += balance

    if (score > bestScore) {
      bestScore = score
      bestSplit = [left, right]
    }
  }
  return bestSplit
}

const t1 = "But let's openThat's how Windows are in Germany, okayNahin why there is fun on this weekend that means we get 20% in the supermarket from this so premium back. I get money from an empty crackers. Let's make some base song. not feeling too well which team do you want we have all the kind of thing which will help you meet my new german friend alex you are not friends."
const t2 = "it's hard let's open the windows like this and how to close it just put it down nahin chahiye don't you like why there is fun on this well that means we get 20% in the supermarket from this so bring it back i get money from an empty case if let's make some faisala which do you want we have all the kind of thing which will help you let's see some sweets builder quarter swarts what we we are famous for that meet my new german friend alex you are not friends."
const t3 = "that's how windows are in germany OK call you by putting it like this and how do you close it just put it down nahin why there is fun on this will that means we get 20% in the supermarket from this so bring it back i get money from an empty canvas god let's make some basarab i'm not feeling too well let's eat some swap with authority swarts what shweta daughter we are famous for that meet my new german alex you are not friends."

function tokenize(text: string): string[] {
  const raw = text.split(/\s+/).filter(w => w.length > 0)
  const tokens: string[] = []
  for (const token of raw) {
    const split = splitConcatenated(token)
    tokens.push(...split)
  }
  return tokens
}

const tok1 = tokenize(t1)
const tok2 = tokenize(t2)
const tok3 = tokenize(t3)

console.log('t1 tokens:', tok1.length, tok1.slice(0, 30).join(' | '))
console.log('t2 tokens:', tok2.length, tok2.slice(0, 30).join(' | '))
console.log('t3 tokens:', tok3.length, tok3.slice(0, 30).join(' | '))
console.log()

// Show word overlap between first 30 words of each
const check = (arr1: string[], arr2: string[], label: string) => {
  let matches = 0
  for (const w1 of arr1.slice(0, 30)) {
    if (arr2.slice(0, 40).some(w2 => isWordMatch(w1, w2))) matches++
  }
  console.log(`${label}: ${matches}/30 first words of t1 match in other`)
}
check(tok1, tok2, 't1 vs t2')
check(tok1, tok3, 't1 vs t3')
check(tok2, tok3, 't2 vs t3')
console.log()

// Build a unified vocabulary with positions
const allWords: { word: string; src: string; pos: number }[] = []
for (const [src, tokens] of [[...tok1], [...tok2], [...tok3]].entries()) {
  for (let i = 0; i < tokens.length; i++) {
    allWords.push({ word: tokens[i], src: String(src), pos: i })
  }
}

// Cluster similar words
const clusters: { word: string; count: number; positions: number[] }[] = []
for (const entry of allWords) {
  let best: typeof clusters[0] | null = null
  let bestSim = 0
  for (const c of clusters) {
    if (isWordMatch(entry.word, c.word)) {
      const sim = 1 - levenshtein(normalize(entry.word), normalize(c.word)) / Math.max(entry.word.length, c.word.length)
      if (sim > bestSim) { bestSim = sim; best = c }
    }
  }
  if (best) {
    best.count++
    best.positions.push(entry.pos)
    if (entry.word.length > best.word.length) best.word = entry.word
  } else {
    clusters.push({ word: entry.word, count: 1, positions: [entry.pos] })
  }
}

// Show top clusters (words that appear in 2+ sources)
const popular = clusters.filter(c => c.count >= 2).sort((a, b) => b.count - a.count)
console.log('Words appearing in 2+ sources:', popular.length)
console.log(popular.slice(0, 40).map(c => `  "${c.word}" (${c.count}x, avg pos ${(c.positions.reduce((a,b)=>a+b,0)/c.positions.length).toFixed(1)})`).join('\n'))
