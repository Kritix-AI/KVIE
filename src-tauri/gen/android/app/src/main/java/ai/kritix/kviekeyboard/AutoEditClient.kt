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

    private const val BASE_URL = "http://192.168.1.3:8765/api/autoedit"
    private val client = OkHttpClient.Builder()
        .connectTimeout(3, TimeUnit.SECONDS)
        .readTimeout(5, TimeUnit.SECONDS)
        .build()

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
            null // fallback gracefully to Stage 1 transcription
        }
    }
}
