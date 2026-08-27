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

    fun resolveAppName(context: Context, packageName: String?): String {
        if (packageName.isNullOrBlank()) return "Active Application"
        return try {
            val pm = context.packageManager
            val appInfo = pm.getApplicationInfo(packageName, 0)
            pm.getApplicationLabel(appInfo).toString()
        } catch (_: Exception) {
            when {
                packageName.contains("whatsapp", ignoreCase = true) -> "WhatsApp"
                packageName.contains("chrome", ignoreCase = true) -> "Google Chrome"
                packageName.contains("telegram", ignoreCase = true) -> "Telegram"
                packageName.contains("instagram", ignoreCase = true) -> "Instagram"
                packageName.contains("linkedin", ignoreCase = true) -> "LinkedIn"
                packageName.contains("outlook", ignoreCase = true) -> "Microsoft Outlook"
                packageName.contains("teams", ignoreCase = true) -> "Microsoft Teams"
                packageName.contains("notes", ignoreCase = true) || packageName.contains("memo", ignoreCase = true) -> "Notes"
                packageName.contains("keep", ignoreCase = true) -> "Google Keep"
                packageName.contains("mms", ignoreCase = true) || packageName.contains("messaging", ignoreCase = true) -> "Messages"
                packageName.contains("gmail", ignoreCase = true) -> "Gmail"
                packageName.contains("twitter", ignoreCase = true) || packageName.contains("x.android", ignoreCase = true) -> "X (Twitter)"
                packageName.contains("youtube", ignoreCase = true) -> "YouTube"
                packageName.contains("docs", ignoreCase = true) -> "Google Docs"
                packageName.contains("slack", ignoreCase = true) -> "Slack"
                packageName.contains("discord", ignoreCase = true) -> "Discord"
                packageName.contains("signal", ignoreCase = true) -> "Signal"
                packageName.contains("reddit", ignoreCase = true) -> "Reddit"
                else -> packageName.substringAfterLast(".").replaceFirstChar { it.uppercase() }
            }
        }
    }

    fun getSessionsJson(context: Context): String {
        val prefs = context.getSharedPreferences("kvie_prefs", Context.MODE_PRIVATE)
        return prefs.getString("kvie_voice_sessions", "[]") ?: "[]"
    }

    fun clearSessions(context: Context) {
        val prefs = context.getSharedPreferences("kvie_prefs", Context.MODE_PRIVATE)
        prefs.edit().remove("kvie_voice_sessions").apply()
    }
}
