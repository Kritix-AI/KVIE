/**
 * AudioWorklet processor for KVIE voice capture.
 *
 * Runs off-main-thread at 16 kHz mono PCM, delivering 512-sample chunks
 * (32 ms @ 16 kHz) to the main thread via MessagePort. This replaces
 * the deprecated ScriptProcessorNode, eliminating main-thread jitter
 * and cutting audio capture latency from ~64 ms to ~32 ms.
 */

export interface ProcessorMessage {
  type: 'pcm'
  samples: Int16Array
}

export interface ProcessorOptions {
  desiredSampleRate: number
}

const TARGET_SAMPLE_RATE = 16000
const CHUNK_SIZE = 512

export function createProcessorCode(): string {
  return `
class KVIEAudioProcessor extends AudioWorkletProcessor {
  constructor() {
    super()
    this._buffer = new Float32Array(CHUNK_SIZE)
    this._bufferIndex = 0
  }

  process(inputs) {
    const input = inputs[0]
    if (!input || !input[0] || input[0].length === 0) {
      return true
    }

    const channelData = input[0]
    let srcIndex = 0

    while (srcIndex < channelData.length) {
      const remaining = CHUNK_SIZE - this._bufferIndex
      const toCopy = Math.min(remaining, channelData.length - srcIndex)

      this._buffer.set(channelData.subarray(srcIndex, srcIndex + toCopy), this._bufferIndex)
      this._bufferIndex += toCopy
      srcIndex += toCopy

      if (this._bufferIndex >= CHUNK_SIZE) {
        const pcm16 = new Int16Array(CHUNK_SIZE)
        for (let i = 0; i < CHUNK_SIZE; i++) {
          const s = Math.max(-1, Math.min(1, this._buffer[i]))
          pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF
        }
        this.port.postMessage({ type: 'pcm', samples: pcm16 })
        this._bufferIndex = 0
      }
    }

    return true
  }
}

self.registerProcessor('kvie-audio-processor', KVIEAudioProcessor)
`
}

export interface WorkletHandle {
  disconnect: () => void
  stream: MediaStream
  context: AudioContext
}

export async function startAudioWorklet(
  stream: MediaStream,
): Promise<WorkletHandle> {
  const context = new AudioContext({ sampleRate: TARGET_SAMPLE_RATE })

  // If the hardware can't do 16 kHz, we'll resample in the worklet
  // but the worklet still operates at CHUNK_SIZE of the actual rate
  const actualRate = context.sampleRate

  const blob = new Blob([createProcessorCode()], { type: 'application/javascript' })
  const url = URL.createObjectURL(blob)
  await context.audioWorklet.addModule(url)
  URL.revokeObjectURL(url)

  const source = context.createMediaStreamSource(stream)
  const processor = new AudioWorkletNode(context, 'kvie-audio-processor', {
    numberOfInputs: 1,
    numberOfOutputs: 0,
    channelCount: 1,
  })

  source.connect(processor)
  processor.connect(context.destination)

  // Resample if needed — the worklet outputs at actualRate,
  // but the STT service expects 16000 Hz
  let resampleRatio = 1
  if (actualRate !== TARGET_SAMPLE_RATE) {
    resampleRatio = TARGET_SAMPLE_RATE / actualRate
  }

  processor.port.onmessage = (event: MessageEvent<ProcessorMessage>) => {
    if (event.data.type === 'pcm') {
      const { samples } = event.data
      if (resampleRatio === 1) {
        // Already at target rate — send directly
        source.onAudioData?.(samples)
      } else {
        // Resample by simple averaging
        const outputLength = Math.round(samples.length / resampleRatio)
        const output = new Int16Array(outputLength)
        const input = new Float32Array(samples.buffer, samples.byteOffset, samples.length)
        for (let i = 0; i < outputLength; i++) {
          const start = Math.floor(i * resampleRatio)
          const end = Math.min(Math.floor((i + 1) * resampleRatio), input.length)
          let sum = 0
          for (let j = start; j < end; j++) sum += input[j]
          output[i] = Math.round(sum / (end - start))
        }
        source.onAudioData?.(output)
      }
    }
  }

  return {
    disconnect() {
      processor.disconnect()
      source.disconnect()
      context.close().catch(() => {})
    },
    stream,
    context,
  }
}
