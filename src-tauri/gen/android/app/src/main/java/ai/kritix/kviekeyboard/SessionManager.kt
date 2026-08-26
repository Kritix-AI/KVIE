package ai.kritix.kviekeyboard

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Android Voice Session Recorder.
 * Automatically persists voice typing sessions from KVIE Keyboard and Floating Mic
 * into SharedPreferences so they appear in the KVIE Sessions tab.
 */
object SessionManager {

    fun recordSession(context: Context, text: String, targetApp: String = "KVIE Keyboard") {
        val clean = text.trim()
        if (clean.length < 2) return

        val prefs = context.getSharedPreferences("kvie_prefs", Context.MODE_PRIVATE)
        val existingJson = prefs.getString("kvie_voice_sessions", "[]") ?: "[]"
        val sessionsArray = try {
            JSONArray(existingJson)
        } catch (_: Exception) {
            JSONArray()
        }

        // Avoid duplicate identical entry if last text matches
        if (sessionsArray.length() > 0) {
            val latest = sessionsArray.optJSONObject(0)
            if (latest != null && latest.optString("text") == clean) {
                return
            }
        }

        val sdf = SimpleDateFormat("hh:mm a", Locale.getDefault())
        val newObj = JSONObject().apply {
            put("id", System.currentTimeMillis().toString())
            put("text", clean)
            put("targetApp", targetApp)
            put("timestamp", sdf.format(Date()))
            put("wordCount", clean.split(Regex("\\s+")).size)
        }

        val newArray = JSONArray()
        newArray.put(newObj)
        for (i in 0 until Math.min(sessionsArray.length(), 49)) {
            newArray.put(sessionsArray.get(i))
        }

        prefs.edit().putString("kvie_voice_sessions", newArray.toString()).apply()
    }

    fun getSessionsJson(context: Context): String {
        val prefs = context.getSharedPreferences("kvie_prefs", Context.MODE_PRIVATE)
        return prefs.getString("kvie_voice_sessions", "[]") ?: "[]"
    }
}
