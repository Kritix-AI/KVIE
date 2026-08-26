package ai.kritix.kviekeyboard

import ai.kritix.desktop.R
import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.inputmethodservice.InputMethodService
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.view.HapticFeedbackConstants
import android.view.MotionEvent
import android.view.View
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputConnection
import android.widget.Button
import android.widget.ImageButton
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.content.ContextCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch

/**
 * KVIE Full Hybrid Voice & QWERTY Keyboard Input Method Service.
 * Combines:
 * 1. Complete QWERTY & Number/Symbol touch typing keypad.
 * 2. Instant AI Voice Dictation toolbar with on-device speech engines.
 * 3. 1-Tap on-device SmolLM2-360M AutoEdit AI Polish for typed text.
 */
class KVIEInputMethodService : InputMethodService() {

    private var speechRecognizer: SpeechRecognizer? = null
    private var whisperEngine: WhisperEngine? = null
    private var parakeetEngine: ParakeetEngine? = null

    private var isListening = false
    private var isShifted = false
    private var isCapsLock = false
    private var isSymbolsMode = false

    private lateinit var statusText: TextView
    private lateinit var micButton: ImageButton
    private lateinit var polishButton: Button
    private lateinit var keyShift: Button
    private lateinit var keySymbols: Button
    private lateinit var keyBackspace: Button
    private lateinit var keySpace: Button
    private lateinit var keyDot: Button
    private lateinit var keyComma: Button
    private lateinit var keyEnter: Button

    private lateinit var row1: LinearLayout
    private lateinit var row2: LinearLayout
    private lateinit var row3Letters: LinearLayout

    private val alphabetKeysRow1 = listOf("q", "w", "e", "r", "t", "y", "u", "i", "o", "p")
    private val alphabetKeysRow2 = listOf("a", "s", "d", "f", "g", "h", "j", "k", "l")
    private val alphabetKeysRow3 = listOf("z", "x", "c", "v", "b", "n", "m")

    private val symbolKeysRow1 = listOf("1", "2", "3", "4", "5", "6", "7", "8", "9", "0")
    private val symbolKeysRow2 = listOf("@", "#", "$", "_", "&", "-", "+", "(", ")")
    private val symbolKeysRow3 = listOf("*", "\"", "'", ":", ";", "!", "?")

    private val currentKeyButtons = mutableListOf<Button>()
    private val scope = CoroutineScope(Dispatchers.Main)
    private var engineJob: Job? = null

    private val backspaceHandler = Handler(Looper.getMainLooper())
    private var isBackspaceHolding = false
    private var keyboardRootView: View? = null

    override fun onCreate() {
        super.onCreate()
        whisperEngine = WhisperEngine(this)
        parakeetEngine = ParakeetEngine(this)
        AutoEditClient.init(this)
    }

    override fun onCreateInputView(): View {
        val view = layoutInflater.inflate(R.layout.keyboard_view, null)
        keyboardRootView = view

        statusText = view.findViewById(R.id.statusText)
        micButton = view.findViewById(R.id.micButton)
        polishButton = view.findViewById(R.id.polishButton)

        row1 = view.findViewById(R.id.row1)
        row2 = view.findViewById(R.id.row2)
        row3Letters = view.findViewById(R.id.row3Letters)

        keyShift = view.findViewById(R.id.keyShift)
        keySymbols = view.findViewById(R.id.keySymbols)
        keyBackspace = view.findViewById(R.id.keyBackspace)
        keySpace = view.findViewById(R.id.keySpace)
        keyDot = view.findViewById(R.id.keyDot)
        keyComma = view.findViewById(R.id.keyComma)
        keyEnter = view.findViewById(R.id.keyEnter)

        // 1. Setup Voice Dictation Mic Button
        micButton.setOnClickListener {
            performKeyHaptic()
            if (isListening) stopListening() else startListening()
        }

        // 2. Setup SmolLM2 AI Polish Button
        polishButton.setOnClickListener {
            performKeyHaptic()
            triggerAIPolish()
        }

        // 3. Setup Switch Input Method Button
        view.findViewById<ImageButton>(R.id.switchKeyboardButton).setOnClickListener {
            performKeyHaptic()
            (getSystemService(INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager)
                .showInputMethodPicker()
        }

        // 4. Setup Keypad Action Buttons
        keyShift.setOnClickListener {
            performKeyHaptic()
            toggleShift()
        }

        keySymbols.setOnClickListener {
            performKeyHaptic()
            toggleSymbolsMode()
        }

        setupBackspaceKey()

        keySpace.setOnClickListener {
            performKeyHaptic()
            currentInputConnection?.commitText(" ", 1)
        }

        keyDot.setOnClickListener {
            performKeyHaptic()
            currentInputConnection?.commitText(if (isSymbolsMode) "/" else ".", 1)
        }

        keyComma.setOnClickListener {
            performKeyHaptic()
            currentInputConnection?.commitText(if (isSymbolsMode) "=" else ",", 1)
        }

        keyEnter.setOnClickListener {
            performKeyHaptic()
            handleEnterKey()
        }

        // 5. Render QWERTY key rows
        populateKeys()

        return view
    }

    private fun populateKeys() {
        row1.removeAllViews()
        row2.removeAllViews()
        row3Letters.removeAllViews()
        currentKeyButtons.clear()

        val r1 = if (isSymbolsMode) symbolKeysRow1 else alphabetKeysRow1
        val r2 = if (isSymbolsMode) symbolKeysRow2 else alphabetKeysRow2
        val r3 = if (isSymbolsMode) symbolKeysRow3 else alphabetKeysRow3

        for (char in r1) {
            val btn = createKeyButton(char)
            row1.addView(btn)
            currentKeyButtons.add(btn)
        }

        for (char in r2) {
            val btn = createKeyButton(char)
            row2.addView(btn)
            currentKeyButtons.add(btn)
        }

        for (char in r3) {
            val btn = createKeyButton(char)
            row3Letters.addView(btn)
            currentKeyButtons.add(btn)
        }

        updateKeyLabels()
    }

    private fun createKeyButton(label: String): Button {
        val btn = Button(this).apply {
            val params = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, 1f).apply {
                marginStart = 2
                marginEnd = 2
            }
            layoutParams = params
            setBackgroundResource(R.drawable.key_bg)
            setTextColor(0xFFFFFFFF.toInt())
            textSize = 17f
            isAllCaps = false
            tag = label

            setOnClickListener {
                performKeyHaptic()
                val textToCommit = text.toString()
                currentInputConnection?.commitText(textToCommit, 1)

                // Single shift resets after typing 1 character
                if (isShifted && !isCapsLock && !isSymbolsMode) {
                    isShifted = false
                    updateKeyLabels()
                }
            }
        }
        return btn
    }

    private fun updateKeyLabels() {
        for (btn in currentKeyButtons) {
            val raw = btn.tag as? String ?: continue
            if (isSymbolsMode) {
                btn.text = raw
            } else {
                btn.text = if (isShifted || isCapsLock) raw.uppercase() else raw.lowercase()
            }
        }

        keyShift.text = when {
            isSymbolsMode -> "1/2"
            isCapsLock -> "⇪"
            isShifted -> "⇧"
            else -> "⇧"
        }
        keyShift.isSelected = isShifted || isCapsLock
        keySymbols.text = if (isSymbolsMode) "ABC" else "?123"
        keyDot.text = if (isSymbolsMode) "/" else "."
        keyComma.text = if (isSymbolsMode) "=" else ","
    }

    private fun toggleShift() {
        if (isSymbolsMode) {
            // Secondary symbol page toggle
            return
        }
        if (!isShifted && !isCapsLock) {
            isShifted = true
        } else if (isShifted && !isCapsLock) {
            isCapsLock = true
        } else {
            isShifted = false
            isCapsLock = false
        }
        updateKeyLabels()
    }

    private fun toggleSymbolsMode() {
        isSymbolsMode = !isSymbolsMode
        isShifted = false
        isCapsLock = false
        populateKeys()
    }

    private fun setupBackspaceKey() {
        keyBackspace.setOnClickListener {
            performKeyHaptic()
            deleteLastCharacter()
        }

        keyBackspace.setOnLongClickListener {
            isBackspaceHolding = true
            startContinuousBackspace()
            true
        }

        keyBackspace.setOnTouchListener { _, event ->
            if (event.action == MotionEvent.ACTION_UP || event.action == MotionEvent.ACTION_CANCEL) {
                isBackspaceHolding = false
                backspaceHandler.removeCallbacksAndMessages(null)
            }
            false
        }
    }

    private fun startContinuousBackspace() {
        backspaceHandler.postDelayed(object : Runnable {
            override fun run() {
                if (isBackspaceHolding) {
                    performKeyHaptic()
                    deleteLastCharacter()
                    backspaceHandler.postDelayed(this, 60)
                }
            }
        }, 300)
    }

    private fun deleteLastCharacter() {
        val ic = currentInputConnection ?: return
        val selected = ic.getSelectedText(0)
        if (selected != null && selected.isNotEmpty()) {
            ic.commitText("", 1)
        } else {
            ic.deleteSurroundingText(1, 0)
        }
    }

    private fun handleEnterKey() {
        val ic = currentInputConnection ?: return
        val info = currentInputEditorInfo
        if (info != null && (info.imeOptions and EditorInfo.IME_MASK_ACTION) != EditorInfo.IME_ACTION_NONE &&
            (info.imeOptions and EditorInfo.IME_FLAG_NO_ENTER_ACTION) == 0
        ) {
            ic.performEditorAction(info.imeOptions and EditorInfo.IME_MASK_ACTION)
        } else {
            ic.commitText("\n", 1)
        }
    }

    private fun performKeyHaptic() {
        keyboardRootView?.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
    }

    /**
     * 1-Tap On-Device SmolLM2 AutoEdit Polish for current input connection text
     */
    private fun triggerAIPolish() {
        val ic = currentInputConnection ?: return
        val before = ic.getTextBeforeCursor(300, 0)?.toString() ?: ""
        if (before.isBlank()) {
            statusText.text = "Type or speak something first"
            return
        }

        statusText.text = "✨ Polishing with SmolLM2..."
        scope.launch {
            try {
                val polished = AutoEditClient.refine(before, this@KVIEInputMethodService)
                if (polished != null && polished.isNotBlank() && polished != before) {
                    ic.deleteSurroundingText(before.length, 0)
                    ic.commitText(polished, 1)
                    statusText.text = "✨ Cleaned & Polished!"
                } else {
                    statusText.text = "Already polished ✨"
                }
            } catch (e: Exception) {
                statusText.text = "Polish ready"
            }
        }
    }

    private fun getActiveEngineId(): String {
        val prefs = getSharedPreferences("kvie_prefs", Context.MODE_PRIVATE)
        return prefs.getString("active_engine", "android-speech-recognizer") ?: "android-speech-recognizer"
    }

    private fun startListening() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            statusText.text = "Mic permission needed (open KVIE app)"
            return
        }

        val activeEngine = getActiveEngineId()

        if (activeEngine.startsWith("whisper-cpp")) {
            startWhisperListening(activeEngine)
        } else {
            startSystemSpeechRecognizer()
        }
    }

    private fun startWhisperListening(modelId: String) {
        whisperEngine?.loadModel(modelId)
        isListening = true
        micButton.isSelected = true
        statusText.text = "Whisper listening... Speak now"

        engineJob = scope.launch {
            val transcript = whisperEngine?.transcribeAudio { interim ->
                if (interim.isNotBlank()) statusText.text = interim
            } ?: ""

            if (transcript.isNotBlank()) {
                handleFinalTranscript(transcript)
            } else {
                statusText.text = "KVIE AI Voice (Tap mic)"
            }
            isListening = false
            micButton.isSelected = false
        }
    }

    private fun startSystemSpeechRecognizer() {
        try {
            speechRecognizer?.destroy()
        } catch (_: Exception) {}

        speechRecognizer = SpeechRecognizer.createSpeechRecognizer(this)

        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "en-US")
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, "en-US")
            putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, false)
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3)
            putExtra(RecognizerIntent.EXTRA_CALLING_PACKAGE, packageName)
            putExtra("android.speech.extra.DICTATION_MODE", true)
            putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_MINIMUM_LENGTH_MILLIS, 1500L)
            putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, 2000L)
        }

        speechRecognizer?.setRecognitionListener(object : RecognitionListener {
            override fun onReadyForSpeech(params: android.os.Bundle?) {
                statusText.text = "Listening... Speak now"
            }

            override fun onBeginningOfSpeech() {
                statusText.text = "Hearing your voice..."
            }

            override fun onRmsChanged(rmsdB: Float) {
                if (rmsdB > 2.0f && statusText.text.contains("Listening")) {
                    statusText.text = "Listening 🎙️..."
                }
            }

            override fun onBufferReceived(buffer: ByteArray?) {}

            override fun onEndOfSpeech() {
                statusText.text = "Transcribing & cleaning..."
            }

            override fun onResults(results: android.os.Bundle?) {
                val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                val transcript = matches?.firstOrNull().orEmpty()
                handleFinalTranscript(transcript)
                stopListening()
            }

            override fun onError(error: Int) {
                val errorMsg = when (error) {
                    SpeechRecognizer.ERROR_AUDIO -> "Audio recording error"
                    SpeechRecognizer.ERROR_CLIENT -> "Client error (tap again)"
                    SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> "Mic permission required"
                    SpeechRecognizer.ERROR_NETWORK -> "Network required for speech"
                    SpeechRecognizer.ERROR_NETWORK_TIMEOUT -> "Network timeout"
                    SpeechRecognizer.ERROR_NO_MATCH -> "No speech detected"
                    SpeechRecognizer.ERROR_RECOGNIZER_BUSY -> "Busy — tap mic again"
                    SpeechRecognizer.ERROR_SERVER -> "Speech server error"
                    SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> "No speech heard"
                    else -> "Speech recognition error ($error)"
                }
                statusText.text = errorMsg
                stopListening()
            }

            override fun onPartialResults(partialResults: android.os.Bundle?) {
                val matches = partialResults?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                val interim = matches?.firstOrNull().orEmpty()
                if (interim.isNotBlank()) {
                    statusText.text = interim
                }
            }

            override fun onEvent(eventType: Int, params: android.os.Bundle?) {}
        })

        try {
            speechRecognizer?.startListening(intent)
            isListening = true
            micButton.isSelected = true
        } catch (e: Exception) {
            statusText.text = "Speech error: ${e.message}"
            stopListening()
        }
    }

    private fun stopListening() {
        engineJob?.cancel()
        whisperEngine?.stopRecording()
        try {
            speechRecognizer?.stopListening()
        } catch (_: Exception) {}
        isListening = false
        micButton.isSelected = false
    }

    private fun handleFinalTranscript(rawTranscript: String) {
        if (rawTranscript.isBlank()) {
            statusText.text = "Didn't catch that — tap mic"
            return
        }

        // Commit text immediately into whatever active field is focused
        val ic = currentInputConnection ?: return
        val prefix = if (ic.getTextBeforeCursor(1, 0)?.endsWith(" ") == true || ic.getTextBeforeCursor(1, 0).isNullOrEmpty()) "" else " "
        val stage1 = rawTranscript.trim()
        ic.commitText(prefix + stage1 + " ", 1)
        statusText.text = "Ready (Tap mic or type)"

        // Background SmolLM2 AutoEdit refinement pass
        scope.launch {
            try {
                val refined = AutoEditClient.refine(stage1, this@KVIEInputMethodService)
                if (refined != null && refined.isNotBlank() && refined != stage1) {
                    val oldLen = stage1.length + 1
                    ic.deleteSurroundingText(oldLen, 0)
                    ic.commitText(prefix + refined + " ", 1)
                }
            } catch (_: Exception) {}
        }
    }

    override fun onStartInputView(info: EditorInfo?, restarting: Boolean) {
        super.onStartInputView(info, restarting)
        val engine = getActiveEngineId()
        val displayName = when {
            engine.contains("whisper") -> "Whisper GGUF"
            engine.contains("parakeet") -> "Parakeet ONNX"
            else -> "SpeechRecognizer"
        }
        statusText.text = "KVIE Hybrid ($displayName)"
        isShifted = false
        isCapsLock = false
        isSymbolsMode = false
        populateKeys()
    }

    override fun onDestroy() {
        stopListening()
        speechRecognizer?.destroy()
        backspaceHandler.removeCallbacksAndMessages(null)
        super.onDestroy()
    }
}
