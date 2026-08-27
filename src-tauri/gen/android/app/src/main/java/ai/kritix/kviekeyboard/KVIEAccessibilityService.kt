package ai.kritix.kviekeyboard

import android.accessibilityservice.AccessibilityService
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.os.Build
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

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event == null) return
        val eventType = event.eventType
        if (eventType == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED || 
            eventType == AccessibilityEvent.TYPE_VIEW_FOCUSED ||
            eventType == AccessibilityEvent.TYPE_VIEW_CLICKED) {
            val pkg = event.packageName?.toString()
            if (!pkg.isNullOrBlank() && 
                pkg != packageName && 
                !pkg.contains("inputmethod", ignoreCase = true) &&
                !pkg.contains("systemui", ignoreCase = true)) {
                currentActivePackage = pkg
                lastTargetPackage = pkg
            }
        }
    }

    override fun onInterrupt() {
        instance = null
    }

    override fun onDestroy() {
        instance = null
        super.onDestroy()
    }

    /**
     * Types text directly into the currently focused or editable field in any active app.
     */
    fun typeTextIntoFocusedField(newText: String): Boolean {
        // Step 1: Copy newText to system clipboard
        val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as? ClipboardManager
        val clip = ClipData.newPlainText("KVIE Voice", newText)
        clipboard?.setPrimaryClip(clip)

        // Step 2: Check all interactive windows on screen
        var targetNode: AccessibilityNodeInfo? = null

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            val interactiveWindows = windows
            if (!interactiveWindows.isNullOrEmpty()) {
                for (w in interactiveWindows) {
                    val root = w.root ?: continue
                    targetNode = findEditableNode(root)
                    if (targetNode != null) break
                }
            }
        }

        if (targetNode == null) {
            val root = rootInActiveWindow
            if (root != null) {
                targetNode = findEditableNode(root)
            }
        }

        if (targetNode == null) {
            return false
        }

        lastTargetPackage = targetNode.packageName?.toString()

        try {
            // Step 3: Try ACTION_PASTE first (standard for all apps, preserving cursor position)
            val pasteSuccess = targetNode.performAction(AccessibilityNodeInfo.ACTION_PASTE)
            if (pasteSuccess) {
                return true
            }

            // Step 4: Fallback to ACTION_SET_TEXT
            val existingText = targetNode.text?.toString() ?: ""
            val textToSet = if (existingText.isEmpty() || existingText.endsWith(" ")) {
                existingText + newText
            } else {
                "$existingText $newText"
            }

            val arguments = Bundle().apply {
                putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, textToSet)
            }
            return targetNode.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, arguments)
        } catch (_: Exception) {
            return false
        }
    }

    private var lastTargetPackage: String? = null

    private fun findEditableNode(root: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        // 1. Direct input focus
        val focused = root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)
        if (focused != null && (focused.isEditable || focused.isFocused)) {
            return focused
        }

        // 2. Recursive depth-first search for focused/editable node
        return searchNodeRecursively(root)
    }

    private fun searchNodeRecursively(node: AccessibilityNodeInfo?): AccessibilityNodeInfo? {
        if (node == null) return null
        if (node.isFocused && (node.isEditable || node.className?.contains("EditText", ignoreCase = true) == true)) {
            return node
        }
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            val found = searchNodeRecursively(child)
            if (found != null) return found
        }
        if (node.isEditable) return node
        return null
    }

    companion object {
        var instance: KVIEAccessibilityService? = null
        var currentActivePackage: String? = null

        val isAvailable: Boolean
            get() = instance != null

        fun typeText(text: String): Boolean {
            return instance?.typeTextIntoFocusedField(text) ?: false
        }

        fun getActiveAppName(context: Context): String {
            val pkg = currentActivePackage 
                ?: instance?.lastTargetPackage 
                ?: instance?.rootInActiveWindow?.packageName?.toString()
                ?: KVIEInputMethodService.lastActivePackageName
            return SessionManager.resolveAppName(context, pkg)
        }
    }
}
