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
import android.view.Gravity
import android.view.HapticFeedbackConstants
import android.view.LayoutInflater
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.view.inputmethod.InputMethodManager
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.Toast
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/**
 * Floating Voice Mic Bubble Service.
 * Hovers over any application on Android (WhatsApp, Notes, Chrome, etc.).
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
    private var bubbleGlow: View? = null
    private var bubbleMicIcon: ImageView? = null

    private var speechRecognizer: SpeechRecognizer? = null
    private var isListening = false
    private val scope = CoroutineScope(Dispatchers.Main)

    private val longPressHandler = Handler(Looper.getMainLooper())
    private var isLongPressed = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        windowManager = getSystemService(Context.WINDOW_SERVICE) as WindowManager
        AutoEditClient.init(this)
        createFloatingBubble()
        initSpeechRecognizer()
    }

    @SuppressLint("ClickableViewAccessibility", "InflateParams")
    private fun createFloatingBubble() {
        val layoutType = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        } else {
            @Suppress("DEPRECATION")
            WindowManager.LayoutParams.TYPE_PHONE
        }

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
        floatingView = inflater.inflate(R.layout.floating_mic_layout, null)
        bubbleContainer = floatingView?.findViewById(R.id.bubbleContainer)
        bubbleGlow = floatingView?.findViewById(R.id.bubbleGlow)
        bubbleMicIcon = floatingView?.findViewById(R.id.bubbleMicIcon)

        // Setup Trash overlay at screen bottom
        val trashParams = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            layoutType,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.BOTTOM
        }
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
            // Hold again: Open Keyboard
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

                    longPressHandler.postDelayed(longPressRunnable, 500)
                    true
                }

                MotionEvent.ACTION_MOVE -> {
                    val dx = (event.rawX - initialTouchX).toInt()
                    val dy = (event.rawY - initialTouchY).toInt()

                    if (Math.abs(dx) > 10 || Math.abs(dy) > 10) {
                        isDragging = true
                        longPressHandler.removeCallbacks(longPressRunnable)
                        trashView?.visibility = View.VISIBLE
                    }

                    if (isDragging) {
                        params.x = initialX + dx
                        params.y = initialY + dy
                        windowManager?.updateViewLayout(floatingView, params)
                    }
                    true
                }

                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    v.isPressed = false
                    longPressHandler.removeCallbacks(longPressRunnable)
                    trashView?.visibility = View.GONE

                    val displayMetrics = resources.displayMetrics
                    val screenHeight = displayMetrics.heightPixels

                    // Check if dropped near bottom trash zone (dismiss)
                    if (isDragging && params.y > (screenHeight - 200)) {
                        Toast.makeText(this, "Floating mic closed", Toast.LENGTH_SHORT).show()
                        stopSelf()
                        return@setOnTouchListener true
                    }

                    // Single Tap handling (<200ms without dragging)
                    if (!isDragging && !isLongPressed) {
                        v.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
                        toggleListening()
                    }
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

    private fun initSpeechRecognizer() {
        if (!SpeechRecognizer.isRecognitionAvailable(this)) return
        try {
            speechRecognizer?.destroy()
        } catch (_: Exception) {}

        speechRecognizer = SpeechRecognizer.createSpeechRecognizer(this).apply {
            setRecognitionListener(object : RecognitionListener {
                override fun onReadyForSpeech(params: android.os.Bundle?) {
                    updateBubbleActiveState(true)
                }

                override fun onBeginningOfSpeech() {}
                override fun onRmsChanged(rmsdB: Float) {}
                override fun onBufferReceived(buffer: ByteArray?) {}
                override fun onEndOfSpeech() {}

                override fun onResults(results: android.os.Bundle?) {
                    val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    val transcript = matches?.firstOrNull().orEmpty()
                    handleFinalTranscript(transcript)
                    stopListening()
                }

                override fun onError(error: Int) {
                    stopListening()
                }

                override fun onPartialResults(partialResults: android.os.Bundle?) {}
                override fun onEvent(eventType: Int, params: android.os.Bundle?) {}
            })
        }
    }

    private fun toggleListening() {
        if (isListening) stopListening() else startListening()
    }

    private fun startListening() {
        if (speechRecognizer == null) initSpeechRecognizer()

        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "en-US")
            putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, false)
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra("android.speech.extra.DICTATION_MODE", true)
        }

        try {
            speechRecognizer?.startListening(intent)
            isListening = true
            updateBubbleActiveState(true)
        } catch (_: Exception) {
            stopListening()
        }
    }

    private fun stopListening() {
        try {
            speechRecognizer?.cancel()
        } catch (_: Exception) {}
        isListening = false
        updateBubbleActiveState(false)
    }

    private fun updateBubbleActiveState(active: Boolean) {
        bubbleContainer?.isSelected = active
        bubbleGlow?.visibility = if (active) View.VISIBLE else View.GONE
    }

    private fun handleFinalTranscript(raw: String) {
        if (raw.isBlank()) return

        val stripped = SmolLMEngine.stripFillersAndPunctuate(raw)
        if (stripped.isBlank()) return

        // 1. Try Direct IME commit (if KVIE keyboard is currently open)
        var typed = KVIEInputMethodService.commitFromExternal(stripped)

        // 2. Try Direct Accessibility node injection (works across all apps: WhatsApp, Chrome, Telegram, etc.)
        if (!typed) {
            typed = KVIEAccessibilityService.typeText(stripped)
        }

        val targetApp = KVIEAccessibilityService.getActiveAppName(this)
        SessionManager.recordSession(this, stripped, targetApp)

        // 3. If neither typed because Accessibility is not enabled yet, copy & guide user
        if (!typed) {
            val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as? ClipboardManager
            val clip = ClipData.newPlainText("KVIE Voice", stripped)
            clipboard?.setPrimaryClip(clip)

            if (!KVIEAccessibilityService.isAvailable) {
                Toast.makeText(this, "🎙️ Copied! Turn ON 'KVIE Realtime Typing' in Accessibility to type directly", Toast.LENGTH_LONG).show()
                try {
                    val intent = Intent(android.provider.Settings.ACTION_ACCESSIBILITY_SETTINGS).apply {
                        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    }
                    startActivity(intent)
                } catch (_: Exception) {}
            } else {
                Toast.makeText(this, "🎙️ Copied: \"$stripped\"", Toast.LENGTH_SHORT).show()
            }
        } else {
            Toast.makeText(this, "🎙️ Typed directly into field", Toast.LENGTH_SHORT).show()
        }

        scope.launch {
            val polished = AutoEditClient.refine(stripped, this@FloatingMicService) ?: stripped
            if (polished != stripped) {
                SessionManager.recordSession(this@FloatingMicService, polished, "$targetApp (AI Polish)")
                val updatedIme = KVIEInputMethodService.commitFromExternal(polished)
                if (!updatedIme) {
                    KVIEAccessibilityService.typeText(polished)
                }
            }
        }
    }

    override fun onDestroy() {
        stopListening()
        speechRecognizer?.destroy()
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
