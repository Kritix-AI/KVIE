package ai.kritix.kviekeyboard

/**
 * High-Accuracy Sentence-Aware Next-Word Prediction Engine.
 *
 * Employs a multi-tier prediction hierarchy:
 * 1. User Personal Learned Transitions (UserLexiconDatabase word pairs) [Confidence: 95-100]
 * 2. Conversational Trigram Context ("w1 w2" -> candidates) [Confidence: 85-92]
 * 3. Conversational Bigram Context ("w2" -> candidates) [Confidence: 70-80]
 * 4. High-Probability Sentence Starters [Confidence: 65-75]
 */
object SentencePredictor {

    data class ScoredCandidate(
        val word: String,
        val score: Int
    )

    // ───────────── TRIGRAM CONTEXT MAP ("word1 word2" -> ranked predictions) ─────────────
    private val trigramContext: Map<String, List<String>> = mapOf(
        // Questions & Starters
        "how are" to listOf("you", "things", "we"),
        "how is" to listOf("it", "your", "everything"),
        "how was" to listOf("your", "the", "it"),
        "what are" to listOf("you", "the", "we"),
        "what is" to listOf("the", "your", "this"),
        "what do" to listOf("you", "we", "they"),
        "what did" to listOf("you", "they", "he"),
        "where are" to listOf("you", "we", "they"),
        "where is" to listOf("the", "it", "my"),
        "when are" to listOf("you", "we", "they"),
        "when will" to listOf("you", "we", "it"),
        "why are" to listOf("you", "they", "we"),
        "why did" to listOf("you", "they", "he"),
        "who is" to listOf("that", "this", "there"),

        // Gratitude & Courtesy
        "thank you" to listOf("so much", "very much", "for"),
        "thanks for" to listOf("the", "your", "all"),
        "thanks a" to listOf("lot", "bunch", "million"),
        "you are" to listOf("welcome", "right", "great"),
        "you're" to listOf("welcome", "right", "great"),
        "nice to" to listOf("meet", "see", "hear"),
        "good to" to listOf("see", "hear", "know"),
        "pleasure to" to listOf("meet", "work", "help"),

        // Requests & Professional
        "can you" to listOf("please", "send", "call"),
        "could you" to listOf("please", "send", "help"),
        "would you" to listOf("like", "mind", "be"),
        "please let" to listOf("me", "us", "them"),
        "let me" to listOf("know", "check", "see"),
        "let us" to listOf("know", "go", "start"),
        "i would" to listOf("like", "love", "appreciate"),
        "i want" to listOf("to", "you", "a"),
        "i need" to listOf("to", "your", "help"),
        "i hope" to listOf("you", "this", "all"),
        "looking forward" to listOf("to", "for", "with"),
        "forward to" to listOf("hearing", "seeing", "meeting"),
        "as per" to listOf("our", "the", "your"),

        // Intentions & State
        "i am" to listOf("going", "on", "ready"),
        "i'm" to listOf("going", "on", "sorry"),
        "i will" to listOf("be", "call", "send"),
        "i'll" to listOf("be", "call", "let"),
        "i have" to listOf("been", "to", "seen"),
        "i had" to listOf("a", "to", "been"),
        "i don't" to listOf("know", "think", "have"),
        "i think" to listOf("it", "we", "you"),
        "i know" to listOf("that", "it", "what"),
        "we are" to listOf("going", "ready", "happy"),
        "we will" to listOf("be", "meet", "have"),
        "they are" to listOf("going", "ready", "not"),
        "it will" to listOf("be", "take", "help"),
        "it is" to listOf("a", "the", "very"),

        // Reassurance & Common Idioms
        "don't worry" to listOf("about", "bhai", "it"),
        "no problem" to listOf("at", "bro", "bhai"),
        "see you" to listOf("soon", "tomorrow", "later"),
        "talk to" to listOf("you", "him", "them"),
        "call me" to listOf("when", "back", "later"),
        "send me" to listOf("the", "your", "details"),
        "check this" to listOf("out", "link", "one"),
        "give me" to listOf("a", "the", "some"),
        "tell me" to listOf("more", "about", "what"),
        "take care" to listOf("of", "and", "bye"),
        "have a" to listOf("great", "good", "nice"),
        "have you" to listOf("seen", "done", "checked"),
        "at the" to listOf("moment", "same", "end"),
        "in the" to listOf("morning", "evening", "office"),
        "on my" to listOf("way", "own", "phone"),
        "as soon" to listOf("as", "possible", "you"),
        "right now" to listOf("I", "we", "it"),
        "wait for" to listOf("me", "the", "a"),

        // Hinglish / Indian Chat Context
        "kaha ho" to listOf("bhai", "yaar", "aap"),
        "kya kar" to listOf("rahe", "raha", "rahi"),
        "kya hua" to listOf("bhai", "yaar", "kuch"),
        "kya baat" to listOf("hai", "h", "bhai"),
        "theek hai" to listOf("bhai", "mai", "kal"),
        "kal milte" to listOf("hain", "hai", "bhai"),
        "aap kaise" to listOf("ho", "hain", "hai"),
        "main theek" to listOf("hu", "hoon", "bhai"),
        "bas thodi" to listOf("der", "me", "dair"),
        "kaha ja" to listOf("rahe", "raha", "rahi"),
        "kab tak" to listOf("aaoge", "hoga", "aate"),
        "baat karta" to listOf("hu", "hoon", "baad"),
        "phone karo" to listOf("bhai", "yaar", "mujhe"),
        "kitne baje" to listOf("milna", "aana", "hoga"),
        "koi baat" to listOf("nahi", "nhi", "bhai"),
        "haan bhai" to listOf("bol", "kya", "bolo"),
        "nahi yaar" to listOf("mai", "aaj", "kuch"),
        "suno na" to listOf("ek", "kya", "bhai"),
        "arre bhai" to listOf("kya", "sun", "yaar"),
        "kaise ho" to listOf("bhai", "aap", "sab")
    )

    // ───────────── BIGRAM CONTEXT MAP ("word" -> ranked predictions) ─────────────
    private val bigramContext: Map<String, List<String>> = mapOf(
        "how" to listOf("are", "is", "about"),
        "what" to listOf("is", "are", "do"),
        "where" to listOf("are", "is", "do"),
        "when" to listOf("will", "are", "can"),
        "why" to listOf("did", "are", "is"),
        "who" to listOf("is", "are", "was"),
        "thank" to listOf("you", "so", "god"),
        "thanks" to listOf("for", "a", "lot"),
        "please" to listOf("let", "check", "send"),
        "let" to listOf("me", "us", "it"),
        "can" to listOf("you", "we", "I"),
        "could" to listOf("you", "we", "I"),
        "would" to listOf("you", "like", "be"),
        "i" to listOf("am", "will", "have"),
        "you" to listOf("are", "can", "have"),
        "we" to listOf("are", "will", "can"),
        "they" to listOf("are", "will", "were"),
        "it" to listOf("is", "was", "will"),
        "this" to listOf("is", "was", "will"),
        "that" to listOf("is", "was", "would"),
        "good" to listOf("morning", "night", "luck"),
        "see" to listOf("you", "it", "later"),
        "call" to listOf("me", "you", "back"),
        "send" to listOf("me", "the", "it"),
        "meet" to listOf("you", "at", "tomorrow"),
        "are" to listOf("you", "we", "they"),
        "is" to listOf("this", "it", "that"),
        "do" to listOf("you", "not", "we"),
        "did" to listOf("you", "it", "not"),
        "have" to listOf("a", "you", "been"),
        "has" to listOf("been", "done", "come"),
        "had" to listOf("a", "been", "to"),
        "will" to listOf("be", "do", "call"),
        "want" to listOf("to", "a", "you"),
        "need" to listOf("to", "help", "you"),
        "like" to listOf("to", "this", "it"),
        "know" to listOf("if", "that", "what"),
        "think" to listOf("about", "that", "it"),
        "on" to listOf("the", "my", "it"),
        "at" to listOf("the", "home", "work"),
        "in" to listOf("the", "my", "a"),
        "for" to listOf("the", "you", "me"),
        "with" to listOf("you", "me", "the"),
        "about" to listOf("it", "the", "this"),
        "to" to listOf("the", "be", "do"),
        "my" to listOf("way", "friend", "phone"),
        "your" to listOf("name", "help", "order"),
        "our" to listOf("team", "meeting", "plan"),
        "bhai" to listOf("kya", "kaha", "bol"),
        "kya" to listOf("hua", "hai", "kar"),
        "theek" to listOf("hai", "h", "bhai"),
        "kaise" to listOf("ho", "kare", "hoga"),
        "aap" to listOf("kaise", "kaha", "kya"),
        "kal" to listOf("milte", "aaunga", "karenge"),
        "aaj" to listOf("milte", "aana", "karte")
    )

    // High-Probability Sentence Openers
    private val sentenceOpeners = listOf("I", "How", "Hey", "The", "What", "Please", "Thanks", "Can")

    /**
     * Predicts the next word given the full text before the cursor.
     * Returns a list of scored candidates, with the highest-accuracy candidate marked.
     */
    fun predictNextWords(
        textBefore: String,
        isSentenceStart: Boolean,
        userLexiconDb: UserLexiconDatabase? = null,
        limit: Int = 3
    ): List<ScoredCandidate> {
        val trimmed = textBefore.trimEnd()
        val words = trimmed.split("\\s+".toRegex()).filter { it.isNotBlank() }

        val candidates = mutableListOf<ScoredCandidate>()
        val seen = mutableSetOf<String>()

        fun addCandidate(w: String, score: Int) {
            val normalized = w.trim()
            if (normalized.length >= 2 && seen.add(normalized.lowercase())) {
                candidates.add(ScoredCandidate(normalized, score))
            }
        }

        val w1 = if (words.size >= 2) words[words.size - 2].lowercase() else ""
        val w2 = if (words.isNotEmpty()) words.last().lowercase() else ""

        // 0. Contextual Bandit Self-Learning Tier (Highest Priority: 100-115)
        if (userLexiconDb != null) {
            val triKey = ContextualBanditEngine.buildTrigramKey(w1, w2)
            if (triKey.isNotEmpty()) {
                val triBandit = userLexiconDb.getTopBanditCandidates(triKey, limit)
                for ((word, score) in triBandit) {
                    addCandidate(word, (100 + (score * 15)).toInt())
                }
            }
            val biKey = ContextualBanditEngine.buildBigramKey(w2)
            if (biKey.isNotEmpty()) {
                val biBandit = userLexiconDb.getTopBanditCandidates(biKey, limit)
                for ((word, score) in biBandit) {
                    addCandidate(word, (95 + (score * 12)).toInt())
                }
            }
        }

        // 1. Check User Personal Learned Transitions (Priority: 90-98)
        if (userLexiconDb != null && w2.isNotEmpty()) {
            val personalTransitions = userLexiconDb.getLearnedNextWords(w2, limit)
            for ((idx, word) in personalTransitions.withIndex()) {
                addCandidate(word, 92 - (idx * 2))
            }
        }

        // 2. Trigram Match: "w1 w2" -> candidates (Confidence: 84-90)
        if (w1.isNotEmpty() && w2.isNotEmpty()) {
            val trigramKey = "$w1 $w2"
            val matches = trigramContext[trigramKey]
            if (!matches.isNullOrEmpty()) {
                for ((idx, word) in matches.withIndex()) {
                    addCandidate(word, 88 - (idx * 3))
                }
            }
        }

        // 3. Bigram Match: "w2" -> candidates (Confidence: 72-80)
        if (w2.isNotEmpty()) {
            val matches = bigramContext[w2]
            if (!matches.isNullOrEmpty()) {
                for ((idx, word) in matches.withIndex()) {
                    addCandidate(word, 78 - (idx * 3))
                }
            }
        }

        // 4. Sentence Starters if at beginning of sentence or line
        if (isSentenceStart || words.isEmpty()) {
            for ((idx, opener) in sentenceOpeners.withIndex()) {
                addCandidate(opener, 70 - idx)
            }
        }

        // 5. Fallback defaults if still short of candidates
        val fallbacks = if (isSentenceStart) {
            listOf("I", "The", "How", "What", "Can")
        } else {
            listOf("the", "to", "and", "you", "it")
        }
        for (fb in fallbacks) {
            if (candidates.size >= limit) break
            addCandidate(fb, 50)
        }

        // 6. Rerank using Contextual Bandit blended scoring
        val reranked = candidates.map { sc ->
            val blended = ContextualBanditEngine.calculateBlendedScore(w1, w2, sc.word, sc.score, userLexiconDb)
            ScoredCandidate(sc.word, blended)
        }.sortedByDescending { it.score }

        return reranked.take(limit)
    }
}
