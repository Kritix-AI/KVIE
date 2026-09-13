package ai.kritix.kviekeyboard

/**
 * Contextual Bandit Engine for KVIE 2.0.0 (Unified Self-Learning).
 * Bridges Voice (FloatingMicService) and Typing (KVIEInputMethodService) into a single,
 * high-performance (<0.01ms) on-device reinforcement learning feedback loop.
 *
 * Reward Schedule:
 * - Tap Suggestion: +1.0 (Strong explicit positive)
 * - Autocorrect Kept: +0.6 (Implicit positive)
 * - Autocorrect Undone / Backspace: -1.0 (Strong explicit negative)
 * - Spoken Sentence Accepted (no edits for 4.5s): +0.45 (Cross-modal positive)
 * - Spoken Word Deleted / Overwritten: -0.85 (Cross-modal negative)
 */
object ContextualBanditEngine {

    fun buildTrigramKey(w1: String, w2: String): String {
        val clean1 = w1.trim().lowercase()
        val clean2 = w2.trim().lowercase()
        return if (clean1.isNotEmpty() && clean2.isNotEmpty()) "${clean1}_${clean2}" else ""
    }

    fun buildBigramKey(w2: String): String {
        return w2.trim().lowercase()
    }

    /**
     * Blends base n-gram/dictionary commonality score with learned Contextual Bandit score.
     * Formula: FinalScore = BaseScore * (1.0 + 0.65 * BanditScore)
     * Clamped to prevent complete suppression of base grammatical words.
     */
    fun calculateBlendedScore(
        w1: String,
        w2: String,
        candidate: String,
        baseScore: Int,
        userLexiconDb: UserLexiconDatabase?
    ): Int {
        if (userLexiconDb == null) return baseScore

        val triKey = buildTrigramKey(w1, w2)
        val biKey = buildBigramKey(w2)

        val triScore = if (triKey.isNotEmpty()) userLexiconDb.getBanditScore(triKey, candidate) else 0.0f
        val biScore = if (biKey.isNotEmpty()) userLexiconDb.getBanditScore(biKey, candidate) else 0.0f

        // Prefer trigram score if present; otherwise fall back to bigram score
        val effectiveBanditScore = if (triScore != 0.0f) triScore else biScore
        if (effectiveBanditScore == 0.0f) return baseScore

        // Boost or penalize base score by up to 65%
        val multiplier = 1.0f + (0.65f * effectiveBanditScore)
        return (baseScore.toFloat() * multiplier).toInt().coerceIn(10, 160)
    }

    /**
     * Dispatches positive reward when the user explicitly taps a suggestion pill.
     */
    fun rewardSuggestionAccepted(
        w1: String,
        w2: String,
        candidate: String,
        userLexiconDb: UserLexiconDatabase?
    ) {
        if (userLexiconDb == null) return
        val triKey = buildTrigramKey(w1, w2)
        val biKey = buildBigramKey(w2)

        if (triKey.isNotEmpty()) {
            userLexiconDb.recordBanditReward(triKey, candidate, 1.0f)
        }
        if (biKey.isNotEmpty()) {
            userLexiconDb.recordBanditReward(biKey, candidate, 0.75f)
        }
    }

    /**
     * Dispatches negative reward when the user hits Backspace immediately to undo an autocorrect.
     */
    fun rewardAutocorrectUndone(
        w1: String,
        w2: String,
        originalTyped: String,
        rejectedCorrection: String,
        userLexiconDb: UserLexiconDatabase?
    ) {
        if (userLexiconDb == null) return
        val triKey = buildTrigramKey(w1, w2)
        val biKey = buildBigramKey(w2)

        if (triKey.isNotEmpty()) {
            // Heavily penalize the wrong correction
            userLexiconDb.recordBanditReward(triKey, rejectedCorrection, -1.0f)
            // Positively reinforce the word the user actually intended to type
            if (originalTyped.length >= 2) {
                userLexiconDb.recordBanditReward(triKey, originalTyped, 0.8f)
            }
        }
        if (biKey.isNotEmpty()) {
            userLexiconDb.recordBanditReward(biKey, rejectedCorrection, -0.8f)
            if (originalTyped.length >= 2) {
                userLexiconDb.recordBanditReward(biKey, originalTyped, 0.6f)
            }
        }
    }

    /**
     * Dispatches cross-modal positive reward when a voice-dictated sentence was accepted without edits.
     */
    fun rewardVoiceSentenceAccepted(
        words: List<String>,
        userLexiconDb: UserLexiconDatabase?
    ) {
        if (userLexiconDb == null || words.size < 2) return

        for (i in 0 until words.size - 1) {
            val prevWord = words[i]
            val nextWord = words[i + 1]
            val biKey = buildBigramKey(prevWord)
            userLexiconDb.recordBanditReward(biKey, nextWord, 0.45f)
            userLexiconDb.recordTransition(prevWord, nextWord)

            if (i >= 1) {
                val triKey = buildTrigramKey(words[i - 1], prevWord)
                if (triKey.isNotEmpty()) {
                    userLexiconDb.recordBanditReward(triKey, nextWord, 0.55f)
                }
            }
        }
    }

    /**
     * Dispatches cross-modal negative penalty when user erases or corrects a voice-dictated word.
     */
    fun rewardVoiceWordDeleted(
        w1: String,
        w2: String,
        deletedWord: String,
        userLexiconDb: UserLexiconDatabase?
    ) {
        if (userLexiconDb == null) return
        val triKey = buildTrigramKey(w1, w2)
        val biKey = buildBigramKey(w2)

        if (triKey.isNotEmpty()) {
            userLexiconDb.recordBanditReward(triKey, deletedWord, -0.85f)
        }
        if (biKey.isNotEmpty()) {
            userLexiconDb.recordBanditReward(biKey, deletedWord, -0.7f)
        }
    }
}
