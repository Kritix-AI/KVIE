/**
 * AudioWorklet processor for KVIE voice capture.
 *
 * Runs off-main-thread, delivering 512-sample mono PCM chunks to the main
 * thread via MessagePort. This replaces
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
const PROCESSOR_NAME = 'kvie-audio-processor'

export interface WorkletHandle {
  onAudioData: ((data: ArrayBuffer) => void) | null
  disconnect: () => void
  stream: MediaStream
  context: AudioContext
}

export async function startAudioWorklet(
  stream: MediaStream,
  onAudioData?: (data: ArrayBuffer) => void,
): Promise<WorkletHandle> {
  const context = new AudioContext({ sampleRate: TARGET_SAMPLE_RATE })

  // If the browser can't provide a 16 kHz context, resample the captured
  // chunks on the main thread before sending them to the STT service.
  const actualRate = context.sampleRate

  // Load a packaged same-origin module. Blob modules are blocked by the
  // desktop CSP and can leave addModule without a registered processor.
  const moduleUrl = new URL(
    `${import.meta.env.BASE_URL}kvie-audio-processor.js`,
    window.location.origin,
  )
  try {
    await context.audioWorklet.addModule(moduleUrl.href)
  } catch (error) {
    await context.close().catch(() => {})
    throw new Error(
      `Could not load the KVIE audio processor (${moduleUrl.pathname}): ${error instanceof Error ? error.message : String(error)}`,
    )
  }

  const source = context.createMediaStreamSource(stream)
  const processor = new AudioWorkletNode(context, PROCESSOR_NAME, {
    numberOfInputs: 1,
    numberOfOutputs: 1,
    channelCount: 1,
    outputChannelCount: [1],
  })
  const mute = context.createGain()
  mute.gain.value = 0

  source.connect(processor)
  processor.connect(mute)
  mute.connect(context.destination)

  // Resample if needed — the worklet outputs at actualRate,
  // but the STT service expects 16000 Hz
  let resampleRatio = 1
  if (actualRate !== TARGET_SAMPLE_RATE) {
    resampleRatio = TARGET_SAMPLE_RATE / actualRate
  }

  const handle: WorkletHandle = {
    // Attach the sender before connecting the source. A suspended context can
    // otherwise start producing frames before the caller has installed it.
    onAudioData: onAudioData ?? null,
    disconnect() {
      processor.disconnect()
      mute.disconnect()
      source.disconnect()
      context.close().catch(() => {})
    },
    stream,
    context,
  }

  processor.port.onmessage = (event: MessageEvent<ProcessorMessage>) => {
    if (event.data.type === 'pcm') {
      const { samples } = event.data
      if (resampleRatio === 1) {
        // Already at target rate — send directly
        handle.onAudioData?.(samples.buffer.slice(samples.byteOffset, samples.byteOffset + samples.byteLength) as ArrayBuffer)
      } else {
        // Downsample by simple averaging with the correct input/output ratio.
        const outputLength = Math.round(samples.length * resampleRatio)
        const output = new Int16Array(outputLength)
        for (let i = 0; i < outputLength; i++) {
          const start = Math.floor(i / resampleRatio)
          const end = Math.max(start + 1, Math.min(Math.floor((i + 1) / resampleRatio), samples.length))
          let sum = 0
          for (let j = start; j < end; j++) sum += samples[j]
          output[i] = Math.round(sum / Math.max(end - start, 1))
        }
        handle.onAudioData?.(output.buffer.slice(output.byteOffset, output.byteOffset + output.byteLength) as ArrayBuffer)
      }
    }
  }

  // Global hotkeys are not browser user gestures. Chromium may therefore
  // create an AudioContext in the suspended state even after getUserMedia has
  // granted microphone access. Explicitly resume it before reporting success.
  try {
    if (context.state !== 'running') await context.resume()
  } catch (error) {
    processor.disconnect()
    mute.disconnect()
    source.disconnect()
    await context.close().catch(() => {})
    throw new Error(`Could not start microphone audio capture: ${error instanceof Error ? error.message : String(error)}`)
  }
  if (context.state !== 'running') {
    processor.disconnect()
    mute.disconnect()
    source.disconnect()
    await context.close().catch(() => {})
    throw new Error('Microphone audio capture is suspended. Click the mic once, then retry the ` key.')
  }

  return handle
}
