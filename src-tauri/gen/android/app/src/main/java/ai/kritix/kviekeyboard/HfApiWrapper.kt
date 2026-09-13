package ai.kritix.kviekeyboard

import android.content.Context
import android.util.Log

import java.io.File
import java.io.FileOutputStream
import java.net.URL

import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.ResponseBody

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Minimal HuggingFace model downloader.
 * Fetches specified files from a HF repo and saves them to targetDir.
 */
object HfApiWrapper {

    private const val TAG = "HfApiWrapper"
    private val client = OkHttpClient.Builder()
        .connectTimeout(30)
        .readTimeout(120)
        .build()

    /**
     * Download specified files from a HuggingFace model repo.
     * @param repoId e.g. "nvidia/parakeet-tdt-0.6b-v2"
     * @param targetDir local directory to save files
     * @param filenames list of filenames to download
     * @return true if all files downloaded successfully
     */
    suspend fun downloadModel(
        repoId: String,
        targetDir: File,
        filenames: List<String>
    ): Boolean = withContext(Dispatchers.IO) {
        targetDir.mkdirs()
        var allOk = true

        for (filename in filenames) {
            val dest = File(targetDir, filename)
            if (dest.exists() && dest.length() > 0) {
                Log.d(TAG, "Skip existing: $filename")
                continue
            }

            val url = "https://huggingface.co/$repoId/resolve/main/$filename"
            Log.d(TAG, "Downloading: $url")

            try {
                val request = Request.Builder().url(url).build()
                client.newCall(request).execute().use { response ->
                    if (!response.isSuccessful) {
                        Log.e(TAG, "Failed: $filename → HTTP ${response.code}")
                        allOk = false
                        continue
                    }

                    val body: ResponseBody = response.body ?: run {
                        allOk = false
                        continue
                    }

                    body.byteStream().use { input ->
                        FileOutputStream(dest).use { output ->
                            input.copyTo(output)
                        }
                    }

                    Log.d(TAG, "Saved: ${dest.absolutePath} (${dest.length()} bytes)")
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error downloading $filename: ${e.message}")
                allOk = false
            }
        }

        allOk
    }
}
