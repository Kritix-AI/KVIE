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
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.util.Log
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
 * - Uses the Android system SpeechRecognizer and streams partial results
 * - Direct injection into active app via IME or Accessibility Service
 *
 * Gestures:
 * 1. Single Tap: Start / Stop Voice Dictation with local rule-based cleanup.
 * 2. Hold (Long Press): Open full keyboard.
 * 3. Drag: Move anywhere on screen, or drag to bottom trash zone to dismiss.
 */
class FloatingMicService : Service() {

    private var windowManager: WindowManager? = null
    private var floatingView: View? = null
    private var trashView: View? = null
    private var bubbleContainer: FrameLayout? = null
    private var bubbleGlow: View? = null
    private var bubbleMicIcon: ImageView? = null
    private var statusLabel: TextView? = null

    private var speechRecognizer: SpeechRecognizer? = null
    private var isListening = false
    private var currentPartial = ""
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private val mainScope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private val longPressHandler = Handler(Looper.getMainLooper())
    private var isLongPressed = false
    private val isProcessing = AtomicBoolean(false)


    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        instance = this
        windowManager = getSystemService(Context.WINDOW_SERVICE) as WindowManager
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

    // ─── Android Speech Recognition ──────────────────────────────────────────

    private fun toggleListening() {
        if (isProcessing.get() && !isListening) {
            Toast.makeText(this, "Still processing previous result...", Toast.LENGTH_SHORT).show()
            return
        }
        if (isListening) stopListening() else startListening()
    }

    private fun startListening() {
        if (KVIEInputMethodService.isCurrentInputSensitive()) {
            Toast.makeText(this, "Voice input is disabled in sensitive fields", Toast.LENGTH_SHORT).show()
            return
        }
        if (checkSelfPermission(android.Manifest.permission.RECORD_AUDIO) != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            Toast.makeText(this, "Allow microphone access in KVIE settings", Toast.LENGTH_LONG).show()
            return
        }
        if (!SpeechRecognizer.isRecognitionAvailable(this)) {
            Toast.makeText(this, "No speech recognition service is installed", Toast.LENGTH_LONG).show()
            return
        }

        destroySpeechRecognizer()
        isListening = true
        currentPartial = ""
        updateBubbleActiveState(true)
        showStatus("Listening...")
        try {
            speechRecognizer = SpeechRecognizer.createSpeechRecognizer(this).apply {
                setRecognitionListener(object : RecognitionListener {
                    override fun onReadyForSpeech(params: android.os.Bundle?) { showStatus("Listening...") }
                    override fun onBeginningOfSpeech() { showStatus("Dictating...") }
                    override fun onRmsChanged(rmsdB: Float) {}
                    override fun onBufferReceived(buffer: ByteArray?) {}
                    override fun onEndOfSpeech() { showStatus("Processing...") }
                    override fun onError(error: Int) {
                        Log.w("FloatingMic", "System speech recognition failed: $error")
                        KVIEInputMethodService.clearVoiceComposition()
                        resetListeningState()
                        if (error != SpeechRecognizer.ERROR_CLIENT && error != SpeechRecognizer.ERROR_SPEECH_TIMEOUT && error != SpeechRecognizer.ERROR_NO_MATCH) {
                            showStatus("Speech recognition failed")
                        }
                    }
                    override fun onResults(results: android.os.Bundle?) {
                        val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                        if (!matches.isNullOrEmpty()) handleFinalTranscript(matches[0]) else {
                            KVIEInputMethodService.clearVoiceComposition()
                            resetListeningState()
                        }
                    }
                    override fun onPartialResults(partialResults: android.os.Bundle?) {
                        val matches = partialResults?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                        if (!matches.isNullOrEmpty()) {
                            currentPartial = matches[0]
                            KVIEInputMethodService.updateVoiceComposition(currentPartial)
                            showStatus("Hearing: ${currentPartial.take(40)}${if (currentPartial.length > 40) "..." else ""}")
                        }
                    }
                    override fun onEvent(eventType: Int, params: android.os.Bundle?) {}
                })
                val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                    putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                    putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
                    putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
                }
                KVIEInputMethodService.beginVoiceComposition()
                startListening(intent)
            }
        } catch (e: Exception) {
            Log.e("FloatingMic", "Could not start system speech recognition", e)
            KVIEInputMethodService.clearVoiceComposition()
            resetListeningState()
            Toast.makeText(this, "Could not start speech recognition", Toast.LENGTH_SHORT).show()
        }
    }

    private fun stopListening() {
        if (isListening) {
            try { speechRecognizer?.stopListening() } catch (_: Exception) { resetListeningState() }
        } else {
            resetListeningState()
        }
    }

    private fun destroySpeechRecognizer() {
        try {
            speechRecognizer?.cancel()
            speechRecognizer?.destroy()
        } catch (_: Exception) {}
        speechRecognizer = null
    }
    private fun resetListeningState() {
        isListening = false
        currentPartial = ""
        destroySpeechRecognizer()
        updateBubbleActiveState(false)
        showStatus("")
    }

    // ─── Transcript Handling ─────────────────────────────────────────────────

    private fun handleFinalTranscript(raw: String) {
        if (KVIEInputMethodService.isCurrentInputSensitive()) {
            isProcessing.set(false)
            KVIEInputMethodService.clearVoiceComposition()
            resetListeningState()
            return
        }
        if (raw.isBlank()) {
            KVIEInputMethodService.clearVoiceComposition()
            resetListeningState()
            return
        }

        isProcessing.set(true)
        resetListeningState()
        showStatus("Writing...")

        scope.launch {
            try {
                val stripped = withContext(Dispatchers.Default) {
                    SmolLMEngine.stripFillersAndPunctuate(raw)
                }

                if (stripped.isBlank()) {
                    isProcessing.set(false)
                    showStatus("")
                    return@launch
                }

                if (KVIEInputMethodService.isCurrentInputSensitive()) {
                    isProcessing.set(false)
                    KVIEInputMethodService.clearVoiceComposition()
                    showStatus("")
                    return@launch
                }

                // Replace the active IME composing region so each partial is shown in place.
                var typed = KVIEInputMethodService.commitVoiceComposition(stripped)

                // Fall back to Accessibility injection
                if (!typed) {
                    typed = KVIEAccessibilityService.typeText(stripped)
                }

                val targetApp = KVIEAccessibilityService.getActiveAppName(this@FloatingMicService)
                scope.launch(Dispatchers.IO) {
                    SessionManager.recordSession(this@FloatingMicService, stripped, targetApp)
                }

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
                    scope.launch(Dispatchers.IO) {
                        val db = UserLexiconDatabase.getInstance(this@FloatingMicService)
                        words.forEach { db.recordWordTyped(it) }
                        delay(100)
                        ContextualBanditEngine.rewardVoiceSentenceAccepted(words, db)
                    }
                }

                showStatus("")
            } catch (e: Exception) {
                Log.e("FloatingMic", "Handle transcript error: ${e.message}")
                KVIEInputMethodService.clearVoiceComposition()
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
        if (instance == this) instance = null
        scope.cancel()
        mainScope.cancel()
        destroySpeechRecognizer()
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

    private fun stopForSensitiveInput() {
        if (!isListening) return
        KVIEInputMethodService.clearVoiceComposition()
        resetListeningState()
    }

    companion object {
        private var instance: FloatingMicService? = null

        fun stopForSensitiveField() {
            instance?.stopForSensitiveInput()
        }
    }
}
