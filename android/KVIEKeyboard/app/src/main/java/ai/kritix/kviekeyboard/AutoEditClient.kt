package ai.kritix.kviekeyboard

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

/**
 * Talks to the /autoedit endpoint on the KVIE backend (see the mobile
 * architecture doc — this is the same service the iOS extension needs
 * for its Qwen2.5-1.5B pass). Point BASE_URL at your deployed backend.
 *
 * Swap this out for an on-device llama.cpp/MLC-LLM call once that's
 * wired up — handleFinalTranscript() in the service doesn't need to
 * change, since it just awaits AutoEditClient.refine().
 */
object AutoEditClient {

    private const val BASE_URL = "https://your-backend.example.com/autoedit"
    private val client = OkHttpClient()

    suspend fun refine(text: String): String? = withContext(Dispatchers.IO) {
        try {
            val body = JSONObject().put("text", text).toString()
                .toRequestBody("application/json".toMediaType())
            val request = Request.Builder().url(BASE_URL).post(body).build()

            client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) return@withContext null
                val json = JSONObject(response.body?.string().orEmpty())
                json.optString("refined_text", text)
            }
        } catch (e: Exception) {
            null // fall back to the Stage 1 text already committed
        }
    }
}
