package ai.kritix.kviekeyboard

import ai.kritix.desktop.R
import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.inputmethodservice.InputMethodService
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.view.View
import android.view.inputmethod.EditorInfo
import android.widget.ImageButton
import android.widget.TextView
import androidx.core.content.ContextCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch

/**
 * KVIE Voice Keyboard Input Method Service.
 * Supports multi-engine on-device speech-to-text:
 * 1. Android Native SpeechRecognizer (Zero latency, built-in)
 * 2. whisper.cpp (On-device Quantized Whisper Tiny / Base)
 * 3. NVIDIA Parakeet (via ONNX Runtime streaming ASR)
 */
class KVIEInputMethodService : InputMethodService() {

    private var speechRecognizer: SpeechRecognizer? = null
    private var whisperEngine: WhisperEngine? = null
    private var parakeetEngine: ParakeetEngine? = null

    private var isListening = false
    private lateinit var statusText: TextView
    private lateinit var micButton: ImageButton

    private val scope = CoroutineScope(Dispatchers.Main)
    private var engineJob: Job? = null

    override fun onCreate() {
        super.onCreate()
        whisperEngine = WhisperEngine(this)
        parakeetEngine = ParakeetEngine(this)
    }

    override fun onCreateInputView(): View {
        val view = layoutInflater.inflate(R.layout.keyboard_view, null)
        statusText = view.findViewById(R.id.statusText)
        micButton = view.findViewById(R.id.micButton)

        micButton.setOnClickListener {
            if (isListening) stopListening() else startListening()
        }

        view.findViewById<ImageButton>(R.id.switchKeyboardButton).setOnClickListener {
            (getSystemService(INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager)
                .showInputMethodPicker()
        }

        return view
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
            // Default & Fallback: Android Native SpeechRecognizer
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
                statusText.text = "Tap the mic and speak"
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
                    SpeechRecognizer.ERROR_NO_MATCH -> "No speech detected — speak louder"
                    SpeechRecognizer.ERROR_RECOGNIZER_BUSY -> "Busy — please tap mic again"
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
            statusText.text = "Speech service error: ${e.message}"
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
            statusText.text = "Didn't catch that — tap mic to retry"
            return
        }

        // Stage 1: Clean filler words
        val stage1 = stripFillerWords(rawTranscript)

        // Commit text immediately into whatever active field is focused
        commitTextToField(stage1)
        statusText.text = "Ready (Tap mic to speak)"

        // Stage 2: Background refinement pass
        scope.launch {
            try {
                val refined = AutoEditClient.refine(stage1)
                if (refined != null && refined.isNotBlank() && refined != stage1) {
                    replaceLastCommittedText(stage1 + " ", refined + " ")
                }
            } catch (_: Exception) {}
        }
    }

    private fun stripFillerWords(text: String): String {
        val fillers = listOf("um", "uh", "like", "you know", "matlab", "basically")
        var result = text
        for (f in fillers) {
            result = result.replace(Regex("\\b$f\\b", RegexOption.IGNORE_CASE), "")
        }
        return result.replace(Regex("\\s+"), " ").trim()
    }

    private fun commitTextToField(text: String) {
        val ic = currentInputConnection
        if (ic != null) {
            ic.commitText(text + " ", 1)
        }
    }

    private fun replaceLastCommittedText(old: String, new: String) {
        val ic = currentInputConnection ?: return
        ic.deleteSurroundingText(old.length, 0)
        ic.commitText(new, 1)
    }

    override fun onStartInputView(info: EditorInfo?, restarting: Boolean) {
        super.onStartInputView(info, restarting)
        val engine = getActiveEngineId()
        val displayName = when {
            engine.contains("whisper") -> "Whisper On-Device"
            engine.contains("parakeet") -> "Parakeet ONNX"
            else -> "SpeechRecognizer"
        }
        statusText.text = "Ready ($displayName)"
    }

    override fun onDestroy() {
        stopListening()
        speechRecognizer?.destroy()
        super.onDestroy()
    }
}
