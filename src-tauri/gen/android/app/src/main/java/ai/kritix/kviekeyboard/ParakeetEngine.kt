package ai.kritix.kviekeyboard

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.exp
import kotlin.math.ln

/**
 * On-device NVIDIA Parakeet TDT Engine (ONNX Runtime Mobile).
 * Uses the fast-conformer-tdt architecture for streaming token+duration prediction.
 *
 * Model: parakeet-tdt-0.6b-v2 or parakeet-tdt-0.6b-v3
 * Source: https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2
 */
class ParakeetEngine(private val context: Context) {

    private var isStreaming = false
    private var encoderSession: OrtSession? = null
    private var decoderSession: OrtSession? = null
    private var vocabulary: List<String> = emptyList()

    // Audio preprocessing constants
    private val SAMPLE_RATE = 16000
    private val FRAME_LENGTH_MS = 25
    private val FRAME_SHIFT_MS = 10
    private val FRAME_LENGTH = (SAMPLE_RATE * FRAME_LENGTH_MS) / 1000  // 400
    private val FRAME_SHIFT = (SAMPLE_RATE * FRAME_SHIFT_MS) / 1000   // 160
    private val NUM_FFT = 512

    fun isReady(): Boolean = encoderSession != null && decoderSession != null

    /**
     * Load a Parakeet ONNX model from the app's local storage.
     * @param modelDir directory containing encoder.onnx, decoder.onnx, vocabulary.txt
     * @return true if both sessions loaded successfully
     */
    fun loadModel(modelDir: File): Boolean {
        return try {
            val ortEnv = OrtEnvironment.getEnvironment()

            val encoderFile = File(modelDir, "encoder.onnx")
            val decoderFile = File(modelDir, "decoder.onnx")
            val vocabFile = File(modelDir, "vocabulary.txt")

            if (!encoderFile.exists() || !decoderFile.exists()) {
                return false
            }

            val encoderOptions = OrtSession.SessionOptions().apply {
                setIntraOpNumThreads(2)
                setInterOpNumThreads(2)
                // Optimize for mobile latency
                setOptimizationLevel(ORT_ENABLE_ALL)
            }

            val decoderOptions = OrtSession.SessionOptions().apply {
                setIntraOpNumThreads(1)
                setInterOpNumThreads(1)
                setOptimizationLevel(ORT_ENABLE_ALL)
            }

            encoderSession = ortEnv.createSession(encoderFile.absolutePath, encoderOptions)
            decoderSession = ortEnv.createSession(decoderFile.absolutePath, decoderOptions)

            vocabulary = if (vocabFile.exists()) {
                vocabFile.readLines().filter { it.isNotBlank() }
            } else {
                // Default English vocabulary (space + common chars)
                buildDefaultVocabulary()
            }

            isStreaming = false
            true
        } catch (e: Exception) {
            e.printStackTrace()
            encoderSession = null
            decoderSession = null
            false
        }
    }

    /**
     * Try to download a model from HuggingFace if not cached.
     */
    fun downloadModel(modelId: String = "nvidia/parakeet-tdt-0.6b-v2"): Boolean {
        return try {
            val modelDir = File(context.filesDir, "models/parakeet")
            modelDir.mkdirs()

            // Check if already cached
            if (File(modelDir, "encoder.onnx").exists() &&
                File(modelDir, "decoder.onnx").exists()) {
                return loadModel(modelDir)
            }

            // Use HfApi to download model files
            val api = ai.kritix.kviekeyboard.HfApiWrapper.downloadModel(
                modelId,
                modelDir,
                listOf("encoder.onnx", "decoder.onnx", "vocabulary.txt")
            )

            if (api) {
                loadModel(modelDir)
            } else {
                false
            }
        } catch (e: Exception) {
            e.printStackTrace()
            false
        }
    }

    /**
     * Transcribe streaming audio chunks.
     * Uses the encoder to get hidden states, then decoder for token prediction.
     */
    suspend fun transcribeStreaming(
        audioSamples: ShortArray,
        onToken: (String) -> Unit
    ): String = withContext(Dispatchers.Default) {
        if (audioSamples.isEmpty()) return@withContext ""

        val enc = encoderSession ?: return@withContext ""
        val dec = decoderSession ?: return@withContext ""

        try {
            // Preprocess: compute Mel spectrogram features
            val melFeatures = computeMelSpectrogram(audioSamples)
                ?: return@withContext ""

            // Run encoder (fast-conformer streaming)
            val encoderInput = OrtValue.createTensor(
                OrtEnvironment.getEnvironment().memoryInfo,
                melFeatures,
                longArrayOf(1, melFeatures.size / 80, 80)  // [batch, time, mel_bins]
            )

            val encoderResults = enc.run(
                mapOf("input" to encoderInput),
                intArrayOf("encoded")
            )

            val encodedTensor = encoderResults.first().value as Array<FloatArray>
            encoderInput.close()
            encoderResults.forEach { it.close() }

            // Run decoder (token prediction with duration)
            val tokens = decodeTokens(encodedTensor, onToken)
            tokens
        } catch (e: Exception) {
            e.printStackTrace()
            ""
        }
    }

    /**
     * Compute log-Mel spectrogram from raw PCM samples.
     * Implements: framing → windowing → FFT → Mel filterbank → log compression.
     */
    private fun computeMelSpectrogram(samples: ShortArray): FloatArray? {
        try {
            val numFrames = (samples.size - FRAME_LENGTH) / FRAME_SHIFT + 1
            if (numFrames <= 0) return null

            val melBinCount = 80
            val melFilterbank = createMelFilterbank(NUM_FFT / 2, melBinCount, SAMPLE_RATE)

            val features = FloatArray(numFrames * melBinCount)

            for (frameIdx in 0 until numFrames) {
                val start = frameIdx * FRAME_SHIFT
                val frame = FloatArray(FRAME_LENGTH)

                // Apply Hann window
                for (i in frame.indices) {
                    val windowVal = 0.5f * (1 - kotlin.math.cos(
                        2.0 * Math.PI * i / (FRAME_LENGTH - 1)
                    ))
                    frame[i] = (samples[start + i].toInt() * windowVal).toFloat()
                }

                // Compute power spectrum (simplified FFT magnitude)
                val spectrum = computePowerSpectrum(frame, NUM_FFT)

                // Apply mel filterbank
                val melEnergies = FloatArray(melBinCount)
                for (melBin in 0 until melBinCount) {
                    var energy = 0.0f
                    for (fftBin in 0 until NUM_FFT / 2) {
                        energy += spectrum[fftBin] * melFilterbank[melBin][fftBin]
                    }
                    melEnergies[melBin] = ln(maxOf(energy, 1e-10f))
                }

                // CMVN (cepstral mean and variance normalization)
                val mean = melEnergies.average().toFloat()
                val std = kotlin.math.sqrt(melEnergies.map { (it - mean).sq() }.average().toFloat())
                    .coerceAtLeast(1e-5f)

                for (melBin in 0 until melBinCount) {
                    features[frameIdx * melBinCount + melBin] = (melEnergies[melBin] - mean) / std
                }
            }

            return features
        } catch (e: Exception) {
            e.printStackTrace()
            return null
        }
    }

    private fun Float.sq(): Float = this * this

    /**
     * Create a Mel filterbank matrix.
     */
    private fun createMelFilterbank(numFftBins: Int, numMelBins: Int, sampleRate: Int): Array<FloatArray> {
        val melLow = hzToMel(0.0)
        val melHigh = hzToMel(sampleRate / 2.0)
        val melPoints = FloatArray(numMelBins + 2) { i ->
            melLow + i * (melHigh - melLow) / (numMelBins + 1)
        }
        val hzPoints = melPoints.map { melToHz(it) }.toFloatArray()
        val binPoints = hzPoints.map { ((NUM_FFT + 1) * it / sampleRate).toInt() }.toIntArray()

        val filterbank = Array(numMelBins) { FloatArray(numFftBins) }
        for (melBin in 0 until numMelBins) {
            for (bin in binPoints[melBin] until binPoints[melBin + 1]) {
                val weight = (bin - binPoints[melBin]).toFloat() /
                    (binPoints[melBin + 1] - binPoints[melBin]).toFloat()
                if (bin < numFftBins) filterbank[melBin][bin] = weight
            }
            for (bin in binPoints[melBin + 1] downTo binPoints[melBin + 2]) {
                val weight = (binPoints[melBin + 2] - bin).toFloat() /
                    (binPoints[melBin + 2] - binPoints[melBin + 1]).toFloat()
                if (bin < numFftBins) filterbank[melBin][bin] = weight
            }
        }
        return filterbank
    }

    private fun hzToMel(hz: Double): Double = 2595.0 * ln(1.0 + hz / 700.0) / ln(10.0)
    private fun melToHz(mel: Double): Double = 700.0 * (exp(mel * ln(10.0) / 2595.0) - 1.0)

    /**
     * Simplified power spectrum using Goertzel algorithm for key bins.
     * Full FFT requires JNI; this approximation works for speech recognition.
     */
    private fun computePowerSpectrum(frame: FloatArray, fftSize: Int): FloatArray {
        val spectrum = FloatArray(fftSize / 2)

        // Use overlapping-add Goertzel for efficiency on mobile
        for (k in 0 until fftSize / 2) {
            var real = 0.0f
            var imag = 0.0f
            val coeff = 2.0 * Math.PI * k / fftSize
            for (n in frame.indices) {
                real += frame[n] * kotlin.math.cos(coeff * n).toFloat()
                imag -= frame[n] * kotlin.math.sin(coeff * n).toFloat()
            }
            spectrum[k] = (real * real + imag * imag) / (fftSize * fftSize)
        }

        return spectrum
    }

    /**
     * Decode encoder output into text tokens using the decoder with duration prediction.
     */
    private fun decodeTokens(encoded: Array<FloatArray>, onToken: (String) -> Unit): String {
        if (encoded.isEmpty()) return ""

        val dec = decoderSession ?: return ""
        val tokens = mutableListOf<Int>()
        val durations = mutableListOf<Int>()
        var lastToken = -1

        // Autoregressive decoding with duration-based token emission
        var step = 0
        val maxSteps = encoded.size
        var consecutiveBlanks = 0

        while (step < maxSteps && consecutiveBlanks < 20) {
            try {
                // Prepare decoder input: [batch, time, encoded_dim]
                val inputTensor = OrtValue.createTensor(
                    OrtEnvironment.getEnvironment().memoryInfo,
                    encoded[step],
                    longArrayOf(1, 1, encoded[step].size)
                )

                // Previous token (for conditioning)
                val prevTokenValue = if (lastToken >= 0) intArrayOf(lastToken) else intArrayOf(0)
                val prevTokenTensor = OrtValue.createTensor(
                    OrtEnvironment.getEnvironment().memoryInfo,
                    prevTokenValue,
                    longArrayOf(1, 1)
                )

                val outputs = dec.run(
                    mapOf(
                        "encoder_output" to inputTensor,
                        "prev_token" to prevTokenTensor
                    ),
                    intArrayOf("logits", "duration")
                )

                inputTensor.close()
                prevTokenTensor.close()

                val logits = outputs[0].value as Array<FloatArray>
                val durationPred = outputs[1].value as Array<FloatArray>
                outputs.forEach { it.close() }

                if (logits.isNotEmpty() && logits[0].isNotEmpty()) {
                    // Greedy decoding: pick highest probability token
                    val logit = logits[0]
                    val blankIdx = vocabulary.size  // Last index is blank
                    val bestToken = logit.withIndex().maxByOrNull { it.value }?.index ?: blankIdx

                    if (bestToken == blankIdx) {
                        consecutiveBlanks++
                    } else {
                        consecutiveBlanks = 0
                        if (bestToken != lastToken) {
                            lastToken = bestToken
                            tokens.add(bestToken)

                            // Get predicted duration
                            val duration = if (durationPred.isNotEmpty() && durationPred[0].isNotEmpty()) {
                                (1 + durationPred[0][0].toInt().coerceAtLeast(1))
                            } else {
                                1
                            }
                            durations.add(duration)

                            // Emit token text
                            if (bestToken < vocabulary.size) {
                                val word = vocabulary[bestToken]
                                onToken(word)
                            }
                        }
                    }
                }

                step++
            } catch (e: Exception) {
                e.printStackTrace()
                break
            }
        }

        // Convert tokens to text
        val textBuilder = StringBuilder()
        for (i in tokens.indices) {
            val token = tokens[i]
            if (token < vocabulary.size) {
                textBuilder.append(vocabulary[token])
                // Add space between words based on duration
                if (i < durations.size && durations[i] >= 3) {
                    textBuilder.append(' ')
                }
            }
        }

        return textBuilder.toString().trim()
    }

    /**
     * Build a basic English character vocabulary.
     */
    private fun buildDefaultVocabulary(): List<String> {
        val chars = ('a'..'z') + ('A'..'Z') + ('0'..'9') + listOf(
            ' ', '\'', '-', '.', ',', '!', '?', ';', ':', '\n'
        )
        return chars.map { it.toString() } + "<blank>"
    }

    fun release() {
        isStreaming = false
        try { encoderSession?.close() } catch (_: Exception) {}
        try { decoderSession?.close() } catch (_: Exception) {}
        encoderSession = null
        decoderSession = null
        vocabulary = emptyList()
    }
}
