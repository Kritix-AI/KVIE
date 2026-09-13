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

const CONTRACTIONS: Record<string, string[]> = {}
for (const c of ["let's", "that's", "it's", "i'm", "don't", "doesn't", "won't",
  "can't", "couldn't", "wouldn't", "shouldn't", "didn't", "isn't", "aren't",
  "wasn't", "weren't", "haven't", "hasn't", "hadn't", "you're", "we're",
  "they're", "we'll", "they'll", "what's", "who's", "there's", "here's"]) {
  CONTRACTIONS[c] = c.split("'")
}

function tokenize(text: string): string[] {
  const raw = text.split(/\s+/).filter(w => w.length > 0)
  const result: string[] = []

  for (const token of raw) {
    const lower = token.toLowerCase().replace(/[.,!?;:]/g, '')

    if (CONTRACTIONS[lower]) {
      const parts = CONTRACTIONS[lower]
      const punct = token.match(/[.,!?;:]+$/)?.[0] || ''
      if (parts.length === 2) {
        if (token[0] === token[0]?.toUpperCase() && token[0] !== token[0]?.toLowerCase()) {
          result.push(parts[0][0].toUpperCase() + parts[0].slice(1))
        } else {
          result.push(parts[0])
        }
        result.push(parts[1] + punct)
      }
      continue
    }

    const capMatch = token.match(/^([a-z][a-z']*)([A-Z][A-Za-z']*)/)
    if (capMatch) {
      result.push(capMatch[1])
      result.push(capMatch[2].replace(/[.,!?;:]+$/gu, ''))
      continue
    }

    const cleaned = token.replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, '')
    if (cleaned.length > 0) result.push(cleaned)
  }

  return result
}

const t1 = "But let's openThat's how Windows are in Germany, okayNahin why there is fun on this weekend that means we get 20% in the supermarket from this so premium back. I get money from an empty crackers. Let's make some base song. not feeling too well which team do you want we have all the kind of thing which will help you meet my new german friend alex you are not friends."
const t2 = "it's hard let's open the windows like this and how to close it just put it down nahin chahiye don't you like why there is fun on this well that means we get 20% in the supermarket from this so bring it back i get money from an empty case if let's make some faisala which do you want we have all the kind of thing which will help you let's see some sweets builder quarter swarts what we we are famous for that meet my new german friend alex you are not friends."
const t3 = "that's how windows are in germany OK call you by putting it like this and how do you close it just put it down nahin why there is fun on this will that means we get 20% in the supermarket from this so bring it back i get money from an empty canvas god let's make some basarab i'm not feeling too well let's eat some swap with authority swarts what shweta daughter we are famous for that meet my new german alex you are not friends."

const tok1 = tokenize(t1)
const tok2 = tokenize(t2)
const tok3 = tokenize(t3)

console.log('t1:', tok1.length, 'tokens')
console.log(tok1.join(' | '))
console.log()
console.log('t2:', tok2.length, 'tokens')
console.log(tok2.join(' | '))
console.log()
console.log('t3:', tok3.length, 'tokens')
console.log(tok3.join(' | '))
