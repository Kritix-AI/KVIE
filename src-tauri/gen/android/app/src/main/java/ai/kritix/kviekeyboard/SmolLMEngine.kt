package ai.kritix.kviekeyboard

import android.content.Context
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

/**
 * SmolLM2-360M GGUF Inference Engine for Android.
 *
 * Two-tier architecture:
 * 1. Primary: native ggml inference via JNI (llama.cpp bindings) when bundled.
 * 2. Fallback: rule-based grammar / filler / punctuation polish (<1 ms, no model).
 *
 * The engine never crashes if the native layer is missing; it logs a warning
 * and continues on the rule-based path.
 */
class SmolLMEngine(private val context: Context) {

    companion object {
        private const val TAG = "SmolLMEngine"
        const val MODEL_FILE = "smollm2-360m-q4_k_m.gguf"
        const val MODEL_REPO = "HuggingFaceTB/SmolLM2-360M-Instruct"
        const val MODEL_MIN_BYTES = 50L * 1024 * 1024

        enum class VoiceCommandType {
            DELETE_LAST_WORD, DELETE_LAST_SENTENCE, CLEAR_ALL,
            NEW_LINE, MAKE_FORMAL, MAKE_CASUAL, NONE
        }

        private val SENTENCE_PATTERN = Regex("(?<=[.!?\n]\s*)([a-z])")
        private val PROPER_NOUNS = setOf(
            "monday","tuesday","wednesday","thursday","friday","saturday","sunday",
            "january","february","march","april","may","june","july","august",
            "september","october","november","december",
            "india","usa","uk","google","apple","microsoft","amazon",
            "kvie","kritix","english","hindi"
        )
        private val FILLER_PATTERNS = listOf(
            Regex("(?i)\b(um+|umm+|ummm+)\b"),
            Regex("(?i)\b(uh+|uhh+|ah+|ahh+|er+|err+|eh+)\b"),
            Regex("(?i)\b(matlab\s*ki|matlab|yaani|matlab\s*ki)\b"),
            Regex("(?i)\b(basically|literally|actually)\b"),
            Regex("(?i)\b(you know|i mean|so yeah)\b"),
            Regex("(?i)(^\s*like\s+)|(,\s*like\s*,?)|(\s+like\s+(?=[,.:;?!]))")
        )
        private val SPOKEN_PUNCTUATION = listOf(
            Regex("(?i)\b(period|full stop)\b") to ".",
            Regex("(?i)\bcomma\b") to ",",
            Regex("(?i)\bquestion mark\b") to "?",
            Regex("(?i)\b(exclamation mark|exclamation point)\b") to "!",
            Regex("(?i)\bcolon\b") to ":",
            Regex("(?i)\bsemicolon\b") to ";",
            Regex("(?i)\b(new line|next line)\b") to "\n",
            Regex("(?i)\b(open paren|open parenthesis)\b") to "(",
            Regex("(?i)\b(close paren|close parenthesis)\b") to ")",
            Regex("(?i)\b(dash|hyphen)\b") to "-"
        )

        fun parseVoiceCommand(transcript: String): VoiceCommandType {
            val lower = transcript.lowercase().trim()
            return when {
                lower.matches(Regex(".*\b(delete that|scratch that|remove that|delete last word|remove last)\b.*"))
                    -> VoiceCommandType.DELETE_LAST_WORD
                lower.matches(Regex(".*\b(delete sentence|remove sentence|scratch sentence|delete last sentence)\b.*"))
                    -> VoiceCommandType.DELETE_LAST_SENTENCE
                lower.matches(Regex(".*\b(clear all|delete all|clear everything|start over|scratch all)\b.*"))
                    -> VoiceCommandType.CLEAR_ALL
                lower.matches(Regex(".*\b(new line|next line|next paragraph|new paragraph|line break|enter)\b.*"))
                    -> VoiceCommandType.NEW_LINE
                lower.matches(Regex(".*\b(make formal|formal mode|formal tone|formal please)\b.*"))
                    -> VoiceCommandType.MAKE_FORMAL
                lower.matches(Regex(".*\b(make casual|casual mode|casual tone|informal please|keep it casual)\b.*"))
                    -> VoiceCommandType.MAKE_CASUAL
                else -> VoiceCommandType.NONE
            }
        }

        fun stripFillersAndPunctuate(text: String): String {
            if (text.isBlank()) return ""
            var result = text.trim()
            for ((regex, sym) in SPOKEN_PUNCTUATION) result = regex.replace(result, sym)
            for (pattern in FILLER_PATTERNS) result = pattern.replace(result, " ")
            result = result.replace(Regex(",\s*,"), ",")
                .replace(Regex("^[,.:;?!\s]+"), "")
                .replace(Regex("\s+([,.:;?!])"), "$1")
                .replace(Regex("([,.:;?!])([a-zA-Z])"), "$1 $2")
                .replace(Regex("\s+"), " ").trim()
            if (result.isBlank()) return ""
            result = result.replace(Regex("(?i)\bi\b"), "I")
                .replace(Regex("(?i)\bi'm\b"), "I'm")
                .replace(Regex("(?i)\bi've\b"), "I've")
                .replace(Regex("(?i)\bi'll\b"), "I'll")
                .replace(Regex("(?i)\bi'd\b"), "I'd")
            result = SENTENCE_PATTERN.replace(result) { it.value.uppercase() }
            val words = result.split(Regex("\s+")).toMutableList()
            for (i in words.indices) {
                val clean = words[i].lowercase().replace(Regex("[^a-zA-Z]"), "")
                if (clean in PROPER_NOUNS) {
                    words[i] = words[i].replaceFirstChar { c -> c.uppercase() }
                }
            }
            return words.joinToString(" ")
        }
    }

    private var nativeReady = false
    private val modelFile: File = File(context.filesDir, "models/$MODEL_FILE")

    val isModelDownloaded: Boolean
        get() = modelFile.exists() && modelFile.length() >= MODEL_MIN_BYTES

    init {
        try {
            System.loadLibrary("ggml")
            System.loadLibrary("llama")
            Log.d(TAG, "Native ggml/llama libraries loaded")
            nativeReady = true
        } catch (e: UnsatisfiedLinkError) {
            Log.w(TAG, "Native libs unavailable - rule-based fallback: ${e.message}")
            nativeReady = false
        } catch (e: Exception) {
            Log.w(TAG, "Native lib load failed: ${e.message}")
            nativeReady = false
        }
    }

    suspend fun ensureModelDownloaded(): Boolean = withContext(Dispatchers.IO) {
        if (isModelDownloaded) return@withContext true
        Log.i(TAG, "Downloading SmolLM2 GGUF from HuggingFace...")
        modelFile.parentFile?.mkdirs()
        return@withContext try {
            HfApiWrapper.downloadModel(
                repoId = MODEL_REPO,
                targetDir = modelFile.parentFile!!,
                filenames = listOf(MODEL_FILE)
            ) && modelFile.exists() && modelFile.length() >= MODEL_MIN_BYTES
        } catch (e: Exception) {
            Log.e(TAG, "Download failed: ${e.message}")
            false
        }
    }

    suspend fun refineText(
        rawTranscript: String,
        style: String = "clean",
        context: String? = null
    ): String = withContext(Dispatchers.Default) {
        if (rawTranscript.isBlank()) return@withContext rawTranscript
        val base = stripFillersAndPunctuate(rawTranscript)
        if (nativeReady && isModelDownloaded) {
            try {
                val refined = runGGUFInference(base, style, context)
                if (refined.isNotBlank() && refined != base) return@withContext refined
            } catch (e: Exception) {
                Log.w(TAG, "GGUF inference failed, using rule-based: ${e.message}")
            }
        }
        applyRuleBasedRefinement(base, style, context)
    }

    private external fun nativeGenerate(prompt: String, maxTokens: Int, temperature: Float): String

    private fun runGGUFInference(input: String, style: String, context: String?): String {
        val systemPrompt = when (style) {
            "formal" -> "You are a professional editor. Rewrite into formal, polished English. Output ONLY the refined text."
            "concise" -> "You are a concise editor. Remove fluff. Output ONLY the refined text."
            else -> "You are a real-time voice typing assistant. Fix grammar and punctuation. Output ONLY polished text."
        }
        val ctxBlock = context?.let { "\n[Previous]: $it" } ?: ""
        val prompt = "system\n$systemPrompt\n\nuser\n$ctxBlock\n\n$input\n\nassistant\n"
        return try {
            nativeGenerate(prompt, 256, 0.3f)
        } catch (e: Exception) {
            Log.w(TAG, "nativeGenerate failed: ${e.message}")
            input
        }
    }

    private fun applyRuleBasedRefinement(text: String, style: String, context: String?): String {
        if (style == "formal" || style == "concise") {
            return try { GrammarRouter.route(text, true) } catch (_: Exception) { text }
        }
        return text
    }
}
