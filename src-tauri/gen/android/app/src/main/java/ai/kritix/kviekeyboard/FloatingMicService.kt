package ai.kritix.kviekeyboard

import ai.kritix.desktop.R
import android.annotation.SuppressLint
import android.app.Service
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.graphics.PixelFormat
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.view.Gravity
import android.view.HapticFeedbackConstants
import android.view.LayoutInflater
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.view.inputmethod.InputMethodManager
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.TextView
import android.widget.Toast
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.collectLatest
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Floating Voice Mic Bubble Service.
 *
 * Architecture:
 * - Uses WhisperEngine (Silero VAD + HTTP Whisper backend) instead of Google SpeechRecognizer
 * - Streams partial transcription results in real-time
 * - Direct injection into active app via IME or Accessibility Service
 *
 * Gestures:
 * 1. Single Tap: Start / Stop Voice Dictation with on-device SmolLM2 refinement.
 * 2. Hold (Long Press): Open full keyboard.
 * 3. Drag: Move anywhere on screen, or drag to bottom trash zone to dismiss.
 */
class FloatingMicService : Service() {

    private var windowManager: WindowManager? = null
    private var floatingView: View? = null
    private var trashView: View? = null
    private var bubbleContainer: FrameLayout? = null
    private var bubbleMicIcon: ImageView? = null
    private var statusLabel: TextView? = null

    private var whisperEngine: WhisperEngine? = null
    private var isListening = false
    private var currentPartial = ""
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private val mainScope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private val longPressHandler = Handler(Looper.getMainLooper())
    private var isLongPressed = false
    private val isProcessing = AtomicBoolean(false)

    // Backend URLs to try (same as AutoEditClient)
    private val backendUrls = listOf(
        "http://127.0.0.1:8765",
        "http://10.0.2.2:8765",
        "http://192.168.1.3:8765"
    )

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        windowManager = getSystemService(Context.WINDOW_SERVICE) as WindowManager
        AutoEditClient.init(this)
        createFloatingBubble()
    }

    @SuppressLint("ClickableViewAccessibility", "InflateParams")
    private fun createFloatingBubble() {
        val layoutType = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        } else {
            @Suppress("DEPRECATION")
            WindowManager.LayoutParams.TYPE_PHONE
        }

        // Main bubble params
        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            layoutType,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = 20
            y = 350
        }

        val inflater = LayoutInflater.from(this)
        floatingView = inflater.inflate(R.layout.floating_mic_layout, null).apply {
            bubbleContainer = findViewById(R.id.bubbleContainer)
            bubbleGlow = findViewById(R.id.bubbleGlow)
            bubbleMicIcon = findViewById(R.id.bubbleMicIcon)
            statusLabel = findViewById(R.id.statusLabel)
        }

        // Trash zone at bottom
        val trashParams = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            layoutType,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT
        ).apply { gravity = Gravity.BOTTOM }

        trashView = inflater.inflate(R.layout.floating_trash_target, null)
        windowManager?.addView(trashView, trashParams)
        windowManager?.addView(floatingView, params)

        setupDragAndGestures(params)
    }

    @SuppressLint("ClickableViewAccessibility")
    private fun setupDragAndGestures(params: WindowManager.LayoutParams) {
        var initialX = 0
        var initialY = 0
        var initialTouchX = 0f
        var initialTouchY = 0f
        var isDragging = false

        val longPressRunnable = Runnable {
            isLongPressed = true
            floatingView?.performHapticFeedback(HapticFeedbackConstants.LONG_PRESS)
            openKeyboard()
        }

        bubbleContainer?.setOnTouchListener { v, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    initialX = params.x
                    initialY = params.y
                    initialTouchX = event.rawX
                    initialTouchY = event.rawY
                    isDragging = false
                    isLongPressed = false
                    v.isPressed = true
                    longPressHandler.postDelayed(longPressRunnable, 600)
                    true
                }

                MotionEvent.ACTION_MOVE -> {
                    val dx = (event.rawX - initialTouchX).toInt()
                    val dy = (event.rawY - initialTouchY).toInt()

                    if (kotlin.math.abs(dx) > 10 || kotlin.math.abs(dy) > 10) {
                        isDragging = true
                        longPressHandler.removeCallbacks(longPressRunnable)
                        trashView?.visibility = View.VISIBLE
                    }

                    if (isDragging) {
                        val newX = initialX + dx
                        val newY = initialY + dy
                        if (newX != params.x || newY != params.y) {
                            params.x = newX
                            params.y = newY
                            windowManager?.updateViewLayout(floatingView, params)
                        }
                    }
                    true
                }

                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    v.isPressed = false
                    longPressHandler.removeCallbacks(longPressRunnable)
                    trashView?.visibility = View.GONE

                    val displayMetrics = resources.displayMetrics
                    val screenHeight = displayMetrics.heightPixels

                    // Trash zone dismissal
                    if (isDragging && params.y > (screenHeight - 200)) {
                        Toast.makeText(this, "Floating mic closed", Toast.LENGTH_SHORT).show()
                        stopSelf()
                        return@setOnTouchListener true
                    }

                    // Single tap: toggle mic
                    if (!isDragging && !isLongPressed) {
                        v.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
                        toggleListening()
                    }
                    isLongPressed = false
                    isDragging = false
                    true
                }

                else -> false
            }
        }
    }

    private fun openKeyboard() {
        Toast.makeText(this, "Opening Keyboard...", Toast.LENGTH_SHORT).show()
        val imm = getSystemService(Context.INPUT_METHOD_SERVICE) as? InputMethodManager
        imm?.showInputMethodPicker()
    }

    // ─── Whisper Engine Integration ──────────────────────────────────────────

    private fun getWhisperEngine(): WhisperEngine? {
        if (whisperEngine == null) {
            // Try to find the working backend URL
            val workingUrl = backendUrls.firstOrNull { checkBackend(it) } ?: backendUrls[0]
            whisperEngine = WhisperEngine(this).configure(
                backendUrl = workingUrl,
                silenceTimeoutMs = 1200,
                minSpeechMs = 250,
                vadThreshold = 0.5f
            )
        }
        return whisperEngine
    }

    private fun checkBackend(url: String): Boolean {
        return try {
            val conn = java.net.URL("$url/health").openConnection() as java.net.HttpURLConnection
            conn.connectTimeout = 500
            conn.readTimeout = 500
            conn.responseCode == 200
        } catch (_: Exception) {
            false
        }
    }

    private fun toggleListening() {
        if (isProcessing.get() && !isListening) {
            Toast.makeText(this, "Still processing previous result...", Toast.LENGTH_SHORT).show()
            return
        }

        if (isListening) {
            stopListening()
        } else {
            startListening()
        }
    }

    private fun startListening() {
        if (isListening) return

        val engine = getWhisperEngine() ?: run {
            Toast.makeText(this, "Whisper engine not available", Toast.LENGTH_SHORT).show()
            return
        }

        isListening = true
        currentPartial = ""
        updateBubbleActiveState(true)
        showStatus("Listening...")

        scope.launch {
            engine.startTranscription(
                onPartial = { partial ->
                    currentPartial = partial
                    showStatus("Hearing: ${partial.take(40)}${if (partial.length > 40) "..." else ""}")
                },
                onFinal = { text ->
                    handleFinalTranscript(text)
                },
                onError = { error ->
                    Log.e("FloatingMic", "Transcription error: $error")
                    showStatus("Error: $error")
                    resetListeningState()
                }
            )
        }
    }

    private fun stopListening() {
        val engine = whisperEngine
        if (engine != null && isListening) {
            scope.launch {
                try {
                    val finalText = engine.stopTranscription()
                    if (finalText.isNotBlank() && finalText != currentPartial) {
                        handleFinalTranscript(finalText)
                    } else if (currentPartial.isNotBlank()) {
                        handleFinalTranscript(currentPartial)
                    }
                } catch (e: Exception) {
                    Log.e("FloatingMic", "Stop error: ${e.message}")
                }
                resetListeningState()
            }
        } else {
            resetListeningState()
        }
    }

    private fun resetListeningState() {
        isListening = false
        currentPartial = ""
        updateBubbleActiveState(false)
        showStatus("")
    }

    // ─── Transcript Handling ─────────────────────────────────────────────────

    private fun handleFinalTranscript(raw: String) {
        if (raw.isBlank()) {
            resetListeningState()
            return
        }

        isProcessing.set(true)
        resetListeningState()
        showStatus("Polishing...")

        scope.launch {
            try {
                val stripped = SmolLMEngine.stripFillersAndPunctuate(raw)

                if (stripped.isBlank()) {
                    isProcessing.set(false)
                    showStatus("")
                    return@launch
                }

                // Try direct injection via IME first
                var typed = KVIEInputMethodService.commitFromExternal(stripped)

                // Fall back to Accessibility injection
                if (!typed) {
                    typed = KVIEAccessibilityService.typeText(stripped)
                }

                val targetApp = KVIEAccessibilityService.getActiveAppName(this@FloatingMicService)
                SessionManager.recordSession(this@FloatingMicService, stripped, targetApp)

                // If neither injection worked, copy to clipboard and guide user
                if (!typed) {
                    val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as? ClipboardManager
                    clipboard?.setPrimaryClip(ClipData.newPlainText("KVIE Voice", stripped))

                    if (!KVIEAccessibilityService.isAvailable) {
                        Toast.makeText(
                            this@FloatingMicService,
                            "Turn ON 'KVIE Realtime Typing' in Accessibility Settings",
                            Toast.LENGTH_LONG
                        ).show()
                        try {
                            startActivity(Intent(android.provider.Settings.ACTION_ACCESSIBILITY_SETTINGS).apply {
                                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                            })
                        } catch (_: Exception) {}
                    } else {
                        Toast.makeText(this@FloatingMicService, "Copied to clipboard", Toast.LENGTH_SHORT).show()
                    }
                }

                // Feed to Contextual Bandit for learning
                val words = stripped.split(Regex("[^\\p{L}\\p{Nd}]+")).filter { it.isNotBlank() }
                if (words.isNotEmpty()) {
                    scope.launch {
                        val db = UserLexiconDatabase.getInstance(this@FloatingMicService)
                        words.forEach { db.recordWordTyped(it) }
                        delay(100)
                        ContextualBanditEngine.rewardVoiceSentenceAccepted(words, db)
                    }
                }

                // AI polish
                val polished = AutoEditClient.refine(stripped, this@FloatingMicService) ?: stripped
                if (polished != stripped) {
                    SessionManager.recordSession(this@FloatingMicService, polished, "$targetApp (AI Polish)")
                    val updatedIme = KVIEInputMethodService.commitFromExternal(polished)
                    if (!updatedIme) {
                        KVIEAccessibilityService.typeText(polished)
                    }
                }

                showStatus("")
            } catch (e: Exception) {
                Log.e("FloatingMic", "Handle transcript error: ${e.message}")
                showStatus("")
            } finally {
                isProcessing.set(false)
            }
        }
    }

    // ─── UI Updates ──────────────────────────────────────────────────────────

    private fun updateBubbleActiveState(active: Boolean) {
        Handler(Looper.getMainLooper()).post {
            bubbleContainer?.isSelected = active
            val prefs = getSharedPreferences("kvie_prefs", Context.MODE_PRIVATE)
            val accentHex = prefs.getString("accent_color", "#22d3ee") ?: "#22d3ee"
            val accentColor = try { android.graphics.Color.parseColor(accentHex) }
            catch (_: Exception) { 0xFF22D3EE.toInt() }
            bubbleMicIcon?.setColorFilter(if (active) accentColor else 0xFFFFFFFF.toInt())
        }
    }

    private fun showStatus(text: String) {
        Handler(Looper.getMainLooper()).post {
            statusLabel?.text = text
            statusLabel?.visibility = if (text.isBlank()) View.GONE else View.VISIBLE
        }
    }

    override fun onDestroy() {
        scope.cancel()
        mainScope.cancel()
        whisperEngine?.release()
        try {
            speechRecognizer?.stopListening()
            speechRecognizer?.cancel()
            speechRecognizer?.destroy()
        } catch (_: Exception) {}
        speechRecognizer = null
        if (floatingView != null) {
            windowManager?.removeView(floatingView)
            floatingView = null
        }
        if (trashView != null) {
            windowManager?.removeView(trashView)
            trashView = null
        }
        super.onDestroy()
    }
}
