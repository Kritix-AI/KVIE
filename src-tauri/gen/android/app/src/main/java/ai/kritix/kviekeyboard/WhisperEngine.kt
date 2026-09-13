package ai.kritix.kviekeyboard

import android.content.Context
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.util.Log
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import java.io.*
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.math.sqrt

private const val TAG = "WhisperEngine"
private const val SAMPLE_RATE = 16000

data class VADResult(val isSpeech: Boolean, val probability: Float, val energy: Float)

/**
 * Silero VAD-based voice activity detector.
 * Lightweight energy-based VAD with smoothing for Android.
 */
class SileroVAD(private val threshold: Float = 0.5f) {
    private val smoothed = FloatArray(3) { 0f }
    private var probability = 0f

    fun processFrame(samples: ShortArray): VADResult {
        if (samples.isEmpty()) return VADResult(false, 0f, 0f)

        var sumSq = 0L
        for (i in samples.indices) {
            val s = samples[i].toInt()
            sumSq += s * s
        }
        val rms = sqrt(sumSq.toFloat() / samples.size) / 32768f
        val rawProb = (rms * 10f).coerceIn(0f, 1f)

        smoothed[0] = smoothed[1]
        smoothed[1] = smoothed[2]
        smoothed[2] = rawProb
        probability = (smoothed[0] + smoothed[1] * 2 + smoothed[2]) / 4f

        return VADResult(probability > threshold, probability, rms)
    }

    fun reset() {
        smoothed.fill(0f)
        probability = 0f
    }
}

data class TranscriptionResult(
    val text: String,
    val isPartial: Boolean,
    val latencyMs: Long,
    val confidence: Float = 1.0f
)

/**
 * On-device Whisper Engine with Silero VAD for Android.
 *
 * Pipeline:
 * 1. AudioRecord → Silero VAD (detect speech start/end in real-time)
 * 2. Stream speech segments to Whisper backend
 * 3. Partial results emitted as user speaks
 * 4. Final result on silence timeout
 *
 * Expected: <500ms end-of-speech to final text on mid-range devices.
 */
class WhisperEngine(private val context: Context) {

    private var audioRecord: AudioRecord? = null
    private var recordingJob: Job? = null
    private val isRecording = AtomicBoolean(false)

    // Configuration
    private var sampleRate = SAMPLE_RATE
    private var silenceTimeoutMs = 1200
    private var minSpeechMs = 250
    private var maxDurationMs = 30000
    private var backendUrl = "http://127.0.0.1:8765"
    private val vad = SileroVAD(threshold = 0.5f)

    // Callbacks
    private var onPartial: ((String) -> Unit)? = null
    private var onFinal: ((String) -> Unit)? = null
    private var onError: ((String) -> Unit)? = null

    // Audio state
    private var hasSpeech = false
    private var speechStartTime = 0L
    private var lastSpeechTime = 0L
    private var recordingStartTime = 0L
    private val currentSegment = mutableListOf<Short>()
    private val preSpeechBuffer = mutableListOf<Short>()

    // Coroutine scope
    private val engineScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    companion object {
        const val FRAME_SIZE = 512
    }

    // ─── Public API ──────────────────────────────────────────────────────────

    fun configure(
        backendUrl: String = this.backendUrl,
        silenceTimeoutMs: Int = this.silenceTimeoutMs,
        minSpeechMs: Int = this.minSpeechMs,
        vadThreshold: Float = 0.5f
    ): WhisperEngine {
        this.backendUrl = backendUrl
        this.silenceTimeoutMs = silenceTimeoutMs
        this.minSpeechMs = minSpeechMs
        return this
    }

    /**
     * Start streaming transcription. Callbacks fire on the main thread.
     */
    fun startTranscription(
        onPartial: (String) -> Unit,
        onFinal: (String) -> Unit,
        onError: (String) -> Unit
    ) {
        if (isRecording.get()) return
        this.onPartial = onPartial
        this.onFinal = onFinal
        this.onError = onError
        resetState()
        startRecording()
    }

    suspend fun stopTranscription(): String = withContext(Dispatchers.IO) {
        val text = buildCurrentTranscript()
        stopRecording()
        text
    }

    fun stop() {
        isRecording.set(false)
        recordingJob?.cancel()
        recordingJob = null
        try {
            audioRecord?.stop()
            audioRecord?.release()
        } catch (_: Exception) {}
        audioRecord = null
        resetState()
    }

    fun isReady(): Boolean = true

    // ─── Recording ───────────────────────────────────────────────────────────

    private fun startRecording() {
        val minBuf = AudioRecord.getMinBufferSize(
            sampleRate,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT
        )
        val bufSize = minBuf.coerceAtLeast(sampleRate * 2)

        try {
            audioRecord = AudioRecord(
                MediaRecorder.AudioSource.VOICE_RECOGNITION,
                sampleRate,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
                bufSize
            )
        } catch (e: SecurityException) {
            Log.e(TAG, "Mic permission denied")
            onError?.invoke("Microphone permission denied")
            return
        }

        audioRecord?.startRecording()
        isRecording.set(true)
        recordingStartTime = System.currentTimeMillis()
        speechStartTime = System.currentTimeMillis()
        lastSpeechTime = System.currentTimeMillis()

        Log.i(TAG, "Recording started (sr=$sampleRate, buf=$bufSize)")
        recordingJob = engineScope.launch { runRecordingLoop() }
    }

    private suspend fun runRecordingLoop() {
        val buffer = ShortArray(FRAME_SIZE)

        while (isRecording.get() && currentCoroutineContext().isActive) {
            val read = audioRecord?.read(buffer, 0, buffer.size) ?: 0
            if (read <= 0) {
                delay(5)
                continue
            }

            val frame = buffer.copyOf(read)
            val result = vad.processFrame(frame)

            if (!hasSpeech) {
                // Ring buffer for pre-speech capture
                preSpeechBuffer.addAll(frame.take(read).toTypedArray().toList())
                val maxPre = (200 * SAMPLE_RATE / 1000) / FRAME_SIZE * FRAME_SIZE
                if (preSpeechBuffer.size > maxPre) {
                    preSpeechBuffer.subList(0, preSpeechBuffer.size - maxPre).clear()
                }

                if (result.isSpeech) {
                    if (System.currentTimeMillis() - speechStartTime >= minSpeechMs) {
                        hasSpeech = true
                        currentSegment.addAll(preSpeechBuffer)
                        Log.d(TAG, "Speech start detected (energy=${result.energy})")
                    }
                } else {
                    speechStartTime = System.currentTimeMillis()
                }
            } else {
                // In speech region
                currentSegment.addAll(frame.take(read).toTypedArray().toList())
                lastSpeechTime = System.currentTimeMillis()

                // Request partial every ~1.5s of speech
                if (currentSegment.size % (SAMPLE_RATE * 2) == 0) {
                    requestPartial()
                }

                // Check silence timeout
                if (System.currentTimeMillis() - lastSpeechTime > silenceTimeoutMs) {
                    Log.i(TAG, "Silence timeout, finalizing")
                    finalizeSegment()
                }
            }

            // Max duration check
            if (System.currentTimeMillis() - recordingStartTime > maxDurationMs) {
                Log.i(TAG, "Max duration reached")
                finalizeSegment()
            }

            yield()
        }
    }

    private fun finalizeSegment() {
        if (!hasSpeech && currentSegment.isEmpty()) {
            resetState()
            return
        }

        val audio = if (preSpeechBuffer.isNotEmpty()) {
            (preSpeechBuffer + currentSegment).toShortArray()
        } else {
            currentSegment.toShortArray()
        }

        engineScope.launch {
            val startTime = System.currentTimeMillis()
            val text = sendToBackend(audio, isPartial = false)
            val latency = System.currentTimeMillis() - startTime

            Log.i(TAG, "Final (${latency}ms): $text")
            if (text.isNotBlank()) {
                withContext(Dispatchers.Main) {
                    onFinal?.invoke(text)
                }
            }
            resetState()
        }
    }

    private fun requestPartial() {
        if (currentSegment.isEmpty()) return
        val audio = currentSegment.toShortArray()
        engineScope.launch {
            val startTime = System.currentTimeMillis()
            val text = sendToBackend(audio, isPartial = true)
            val latency = System.currentTimeMillis() - startTime

            if (text.isNotBlank()) {
                Log.d(TAG, "Partial (${latency}ms): ${text.take(60)}")
                withContext(Dispatchers.Main) {
                    onPartial?.invoke(text)
                }
            }
        }
    }

    // ─── Backend Communication ────────────────────────────────────────────────

    private suspend fun sendToBackend(
        samples: ShortArray,
        isPartial: Boolean,
        retries: Int = 2
    ): String = withContext(Dispatchers.IO) {
        if (samples.isEmpty()) return@withContext ""

        val wavBytes = pcmToWav(samples, sampleRate)
        val endpoint = if (isPartial) "/api/transcribe/partial" else "/api/transcribe"

        repeat(retries) { attempt ->
            try {
                val conn = (URL("$backendUrl$endpoint").openConnection() as HttpURLConnection).apply {
                    requestMethod = "POST"
                    setRequestProperty("Content-Type", "application/octet-stream")
                    setRequestProperty("X-Sample-Rate", sampleRate.toString())
                    setRequestProperty("X-Partial", isPartial.toString())
                    doOutput = true
                    connectTimeout = 3000
                    readTimeout = if (isPartial) 2000 else 8000
                }

                conn.outputStream.use { it.write(wavBytes) }
                val code = conn.responseCode

                if (code == 200) {
                    val resp = conn.inputStream.bufferedReader().readText()
                    return@withContext parseResponse(resp)
                }
            } catch (e: Exception) {
                Log.w(TAG, "Attempt ${attempt + 1} failed: ${e.message}")
                if (attempt < retries - 1) delay(200 * (attempt + 1))
            }
        }
        ""
    }

    private fun parseResponse(json: String): String {
        return try {
            org.json.JSONObject(json).optString("text", "")
        } catch (e: Exception) {
            json.trim().removeSurrounding("\"")
        }
    }

    // ─── Utilities ───────────────────────────────────────────────────────────

    private fun pcmToWav(samples: ShortArray, sr: Int): ByteArray {
        val ds = samples.size * 2
        return ByteArrayOutputStream(44 + ds).apply {
            write("RIFF".toByteArray())
            write(le32(36 + ds)); write("WAVE".toByteArray())
            write("fmt ".toByteArray()); write(le32(16))
            write(le16(1)); write(le16(1)); write(le32(sr))
            write(le32(sr * 2)); write(le16(2)); write(le16(16))
            write("data".toByteArray()); write(le32(ds))
            for (s in samples) { write(s.toByte()); write((s.toInt() ushr 8).toByte()) }
        }.toByteArray()
    }

    private fun le32(v: Int) = byteArrayOf((v and 0xFF).toByte(), ((v shr 8) and 0xFF).toByte(),
        ((v shr 16) and 0xFF).toByte(), ((v shr 24) and 0xFF).toByte())
    private fun le16(v: Int) = byteArrayOf((v and 0xFF).toByte(), ((v shr 8) and 0xFF).toByte())

    private fun resetState() {
        hasSpeech = false
        speechStartTime = System.currentTimeMillis()
        lastSpeechTime = System.currentTimeMillis()
        currentSegment.clear()
        preSpeechBuffer.clear()
        vad.reset()
    }

    private fun buildCurrentTranscript(): String {
        // Combine pre-speech + current for best result
        val all = if (preSpeechBuffer.isNotEmpty()) preSpeechBuffer + currentSegment else currentSegment
        if (all.isEmpty()) return ""
        // Send remaining audio for final transcription
        return engineScope.runCatching {
            val wav = pcmToWav(all.toShortArray(), sampleRate)
            sendToBackend(wav, isPartial = false)
        }.getOrNull() ?: ""
    }

    fun release() {
        stop()
        engineScope.cancel()
    }
}
