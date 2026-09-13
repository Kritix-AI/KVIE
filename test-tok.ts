function tokenize(text: string): string[] {
  const raw = text.split(/\s+/).filter(w => w.length > 0)
  const result: string[] = []

  for (const token of raw) {
    const capBoundary = token.match(/^([a-z][a-z']*)([A-Z][A-Za-z']*)/)
    if (capBoundary) {
      result.push(capBoundary[1])
      result.push(capBoundary[2].replace(/[.,!?;:]+$/gu, ''))
      continue
    }
    const cleaned = token.replace(/^[^\p{L}\p{N}']+|[^\p{L}\p{N}']+$/gu, '')
    if (cleaned.length > 0) result.push(cleaned)
  }
  return result
}

const tests = ["let's", "don't", "it's", "That's", "Germany,", "20%", "openThat's", "back.", "i'm", "we're"]

for (const t of tests) {
  const tokens = tokenize(t)
  console.log(`"${t}" → [${tokens.map(t => `"${t}"`).join(', ')}]`)
}
