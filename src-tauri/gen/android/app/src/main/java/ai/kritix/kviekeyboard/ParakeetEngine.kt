package ai.kritix.kviekeyboard

import android.content.Context
import android.util.Log

/**
 * Parakeet is not currently supported in the Android client. NVIDIA publishes
 * this model as a 4.29 GB NeMo checkpoint; this app contains neither an Android
 * NeMo/ONNX runtime nor a compatible exported model. Never download fake files.
 */
@Deprecated("No Android Parakeet runtime or compatible exported model is bundled")
class ParakeetEngine(@Suppress("UNUSED_PARAMETER") context: Context) {
    fun isReady(): Boolean = false
    fun hasLocalModel(): Boolean = false

    suspend fun loadModel(@Suppress("UNUSED_PARAMETER") modelId: String = "parakeet-tdt-1.1b"): Boolean {
        Log.w("ParakeetEngine", "Parakeet download disabled: Android inference is not implemented")
        return false
    }

    fun startStreaming(
        @Suppress("UNUSED_PARAMETER") onToken: (String) -> Unit,
        onError: (String) -> Unit
    ) {
        onError("Parakeet is unavailable in this Android build")
    }

    fun stopStreaming() = Unit
}