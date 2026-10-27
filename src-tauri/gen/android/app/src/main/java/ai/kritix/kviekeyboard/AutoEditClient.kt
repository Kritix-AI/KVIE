package ai.kritix.kviekeyboard

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

object AutoEditClient {

    private var smolLMEngine: SmolLMEngine? = null

    fun init(context: Context) {
        if (smolLMEngine == null) {
            smolLMEngine = SmolLMEngine(context.applicationContext)
        }
    }

    suspend fun refine(text: String, context: Context? = null): String = withContext(Dispatchers.Default) {
        if (text.isBlank()) return@withContext text

        if (context != null && smolLMEngine == null) {
            init(context)
        }

        // Android polishing stays on the Android engine; never send text to the
        // Windows Python/Ollama service or its model.
        return@withContext smolLMEngine?.refineText(text, context = null) ?: text
    }
}
