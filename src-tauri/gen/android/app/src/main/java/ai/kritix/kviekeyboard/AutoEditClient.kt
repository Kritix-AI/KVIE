package ai.kritix.kviekeyboard

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit

object AutoEditClient {

    private val endpoints = listOf(
        "http://127.0.0.1:8765/api/autoedit",  // USB reverse proxy & on-device
        "http://10.0.2.2:8765/api/autoedit",   // Emulator host routing
        "http://192.168.1.3:8765/api/autoedit" // Local Wi-Fi network host
    )

    private val client = OkHttpClient.Builder()
        .connectTimeout(2, TimeUnit.SECONDS)
        .readTimeout(4, TimeUnit.SECONDS)
        .build()

    suspend fun refine(text: String): String? = withContext(Dispatchers.IO) {
        if (text.isBlank()) return@withContext null

        val body = JSONObject().put("text", text).toString()
            .toRequestBody("application/json".toMediaType())

        for (url in endpoints) {
            try {
                val request = Request.Builder().url(url).post(body).build()
                client.newCall(request).execute().use { response ->
                    if (response.isSuccessful) {
                        val json = JSONObject(response.body?.string().orEmpty())
                        val refined = json.optString("refined_text", "")
                        if (refined.isNotBlank()) {
                            return@withContext refined
                        }
                    }
                }
            } catch (_: Exception) {
                // Try next endpoint
            }
        }
        return@withContext null // Fallback gracefully to Stage 1 transcription
    }
}
