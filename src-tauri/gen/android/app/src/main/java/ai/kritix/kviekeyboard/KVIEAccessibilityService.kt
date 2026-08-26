package ai.kritix.kviekeyboard

import android.accessibilityservice.AccessibilityService
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.os.Bundle
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo

/**
 * Accessibility Service that enables KVIE Floating Mic Bubble to directly
 * type spoken and polished text in real-time into any focused input field
 * across all Android apps (WhatsApp, Chrome, Telegram, Notes, Instagram, etc.).
 */
class KVIEAccessibilityService : AccessibilityService() {

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {}

    override fun onInterrupt() {
        instance = null
    }

    override fun onDestroy() {
        instance = null
        super.onDestroy()
    }

    /**
     * Types text directly into the currently focused EditText in any app.
     */
    fun typeTextIntoFocusedField(newText: String): Boolean {
        val root = rootInActiveWindow ?: return false
        val focusedNode = root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT) ?: return false

        try {
            val existingText = focusedNode.text?.toString() ?: ""
            val textToSet = if (existingText.isEmpty() || existingText.endsWith(" ")) {
                existingText + newText
            } else {
                "$existingText $newText"
            }

            // 1. Try ACTION_SET_TEXT
            val arguments = Bundle().apply {
                putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, textToSet)
            }
            val success = focusedNode.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, arguments)

            if (!success) {
                // 2. Fallback: Copy to clipboard and perform ACTION_PASTE
                val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as? ClipboardManager
                val clip = ClipData.newPlainText("KVIE Paste", newText)
                clipboard?.setPrimaryClip(clip)
                return focusedNode.performAction(AccessibilityNodeInfo.ACTION_PASTE)
            }

            return true
        } catch (_: Exception) {
            return false
        }
    }

    companion object {
        var instance: KVIEAccessibilityService? = null

        val isAvailable: Boolean
            get() = instance != null

        fun typeText(text: String): Boolean {
            return instance?.typeTextIntoFocusedField(text) ?: false
        }
    }
}
