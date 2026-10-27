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

    private const val BASE_URL = "https://your-backend.example.com/autoedit"
    private const val MAX_INPUT_LENGTH = 4096

    private val client = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .writeTimeout(5, TimeUnit.SECONDS)
        .build()

    suspend fun refine(text: String): String? = withContext(Dispatchers.IO) {
        // Enforce HTTPS
        if (!BASE_URL.startsWith("https://")) return@withContext null

        // Cap input length to prevent large payload exfiltration
        val safeText = text.take(MAX_INPUT_LENGTH)
        if (safeText.isBlank()) return@withContext null

        try {
            val body = JSONObject().put("text", safeText).toString()
                .toRequestBody("application/json".toMediaType())
            val request = Request.Builder().url(BASE_URL).post(body).build()

            client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) return@withContext null
                val responseBody = response.body?.string().orEmpty()
                if (responseBody.length > MAX_INPUT_LENGTH * 2) return@withContext null
                val json = JSONObject(responseBody)
                json.optString("refined_text", text).take(MAX_INPUT_LENGTH)
            }
        } catch (e: Exception) {
            null // fall back to the Stage 1 text already committed
        }
    }
}
