package ai.kritix.kviekeyboard

/**
 * KVIE Multi-Tier Grammar Router Pipeline for Android.
 *
 * Architecture:
 *           │ Grammar Router │
 *           └───────┬────────┘
 *                   │
 *        ┌──────────┼──────────┐
 *        ▼          ▼          ▼
 *     TOKEN       SENTENCE   PARAGRAPH
 *     ENGINE       ENGINE      ENGINE
 *        │          │          │
 *        ▼          ▼          ▼
 *    Spelling    Grammar     Context
 *    Typo        Structure   Coherence
 *    Casing      Tense       Flow
 *        │          │          │
 *        └──────────┼──────────┘
 *                   ▼
 *              FINAL EDITOR
 *                   │
 *                   ▼
 *            Corrected Text
 */
object GrammarRouter {

    // ──────────────── Tier 1: Token Engine (Ultra-Fast 0ms Pre-LLM) ────────────────
    object TokenEngine {
        private val typoMap = mapOf(
            "teh" to "the",
            "recieve" to "receive",
            "seperate" to "separate",
            "definately" to "definitely",
            "occured" to "occurred",
            "untill" to "until",
            "truely" to "truly",
            "whcih" to "which",
            "wierd" to "weird",
            "accomodate" to "accommodate",
            "tommorow" to "tomorrow",
            "neccessary" to "necessary",
            "goverment" to "government",
            "arguement" to "argument",
            "enviroment" to "environment",
            "beleive" to "believe",
            "calender" to "calendar",
            "kritcs" to "Kritix",
            "kritix" to "Kritix",
            "kvie" to "KVIE"
        )

        private val homophoneRules = listOf(
            Regex("(?i)\\b(their)\\s+(going|coming|leaving|working|doing|running|trying|making|feeling|happy|ready|sure|online)\\b") to "they're $2",
            Regex("(?i)\\b(they're|there)\\s+(house|car|office|team|code|project|family|time|idea|work|opinion)\\b") to "their $2",
            Regex("(?i)\\b(their)\\s+(is|are|was|were|will|can|could|should|must|has|have)\\b") to "there $2",
            Regex("(?i)\\b(your)\\s+(welcome|right|wrong|going|coming|doing|making|smart|invited|ready|sure)\\b") to "you're $2",
            Regex("(?i)\\b(you're)\\s+(house|car|phone|name|email|code|message|work|turn|time)\\b") to "your $2",
            Regex("(?i)\\b(its)\\s+(a|an|the|my|your|his|her|our|their|going|been|working|ready|done|cool|good|bad|fine)\\b") to "it's $2",
            Regex("(?i)\\b(to)\\s+(much|many|late|fast|slow|bad|good|expensive|hard|easy)\\b") to "too $2",
            Regex("(?i)\\b(more|less|better|worse|greater|smaller|faster|slower|earlier|later|higher|lower)\\s+(then)\\b") to "$1 than",
            Regex("(?i)\\b(will|can|could|should|would|might|to)\\s+(effect)\\b") to "$1 affect",
            Regex("(?i)\\b(the|a|an|direct|negative|positive)\\s+(affect)\\b") to "$1 effect",
            Regex("(?i)\\b(to|will|might|don't)\\s+(loose)\\b") to "$1 lose"
        )

        fun process(text: String): String {
            if (text.isBlank()) return ""

            var result = text

            // 1. Squash exaggerated character repetitions
            result = result.replace(Regex("([a-zA-Z])\\1{2,}"), "$1")

            // 2. Token dictionary lookup
            result = result.replace(Regex("\\b[a-zA-Z]+\\b")) { match ->
                val word = match.value
                val lower = word.lowercase()
                val replacement = typoMap[lower]
                if (replacement != null) {
                    if (word.first().isUpperCase() && word.length > 1 && word[1].isLowerCase()) {
                        replacement.replaceFirstChar { it.uppercase() }
                    } else if (word == word.uppercase()) {
                        replacement.uppercase()
                    } else {
                        replacement
                    }
                } else {
                    word
                }
            }

            // 3. Homophones & Confusion rules
            for ((regex, repl) in homophoneRules) {
                result = regex.replace(result, repl)
            }

            // 4. Standalone pronoun capitalization
            result = result.replace(Regex("\\bi\\b"), "I")
            result = result.replace(Regex("(?i)\\bi'm\\b"), "I'm")
            result = result.replace(Regex("(?i)\\bi've\\b"), "I've")
            result = result.replace(Regex("(?i)\\bi'll\\b"), "I'll")
            result = result.replace(Regex("(?i)\\bi'd\\b"), "I'd")

            return result
        }
    }

    // ──────────────── Tier 2: Sentence Engine (Grammar, Structure & Tense) ────────────────
    object SentenceEngine {
        private val grammarRules = listOf(
            Regex("(?i)\\b(a)\\s+([aeiou][a-z]+)\\b") to "an $2",
            Regex("(?i)\\b(an)\\s+([bcdfghjklmnpqrstvwxyz][a-z]+)\\b") to "a $2",
            Regex("(?i)\\binterested\\s+on\\b") to "interested in",
            Regex("(?i)\\bcongratulations\\s+for\\b") to "congratulations on",
            Regex("(?i)\\bdiscuss\\s+about\\b") to "discuss",
            Regex("(?i)\\bexplain\\s+about\\b") to "explain",
            Regex("(?i)\\bmarried\\s+with\\b") to "married to",
            Regex("(?i)\\bdepend\\s+of\\b") to "depend on"
        )

        fun process(text: String): String {
            if (text.isBlank()) return ""

            var result = text

            for ((regex, repl) in grammarRules) {
                result = regex.replace(result, repl)
            }

            // Capitalize sentence boundaries
            val sentences = result.split(Regex("(?<=[.!?\\n])\\s+")).map { sentence ->
                val trimmed = sentence.trim()
                if (trimmed.isEmpty()) "" else trimmed.replaceFirstChar { it.uppercase() }
            }

            return sentences.filter { it.isNotEmpty() }.joinToString(" ")
        }
    }

    // ──────────────── Tier 3: Paragraph Engine (Coherence & Flow) ────────────────
    object ParagraphEngine {
        fun process(text: String): String {
            if (text.isBlank()) return ""

            var result = text
            // Remove consecutive duplicate words
            result = result.replace(Regex("(?i)\\b(\\w+)\\s+\\1\\b"), "$1")
            // Remove hesitation fragments
            result = result.replace(Regex("(?i)(\\b\\w+\\b)\\s+(\\.\\.\\.|—|-)\\s+(actually|wait|i mean|no)\\s+"), "")
            return result
        }
    }

    // ──────────────── Tier 4: Final Editor ────────────────
    object FinalEditor {
        fun process(text: String): String {
            if (text.isBlank()) return ""

            var result = text

            // Normalize whitespace around punctuation
            result = result.replace(Regex("\\s+([,.:;?!])"), "$1")
            result = result.replace(Regex("([,.:;?!])([a-zA-Z])"), "$1 $2")
            result = result.replace(Regex("\\s+"), " ").trim()

            val words = result.split(" ")
            if (words.size >= 3 && !result.endsWith(".") && !result.endsWith("?") && !result.endsWith("!")) {
                result = "$result."
            }

            return result
        }
    }

    /**
     * Master route execution across all 4 tiers.
     */
    fun route(text: String, enabled: Boolean = true): String {
        if (!enabled || text.isBlank()) {
            return text.trim()
        }

        val step1 = TokenEngine.process(text)
        val step2 = SentenceEngine.process(step1)
        val step3 = ParagraphEngine.process(step2)
        return FinalEditor.process(step3)
    }
}
