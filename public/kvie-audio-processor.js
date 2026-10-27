const CHUNK_SIZE = 512

class KVIEAudioProcessor extends AudioWorkletProcessor {
  constructor() {
    super()
    this._buffer = new Float32Array(CHUNK_SIZE)
    this._bufferIndex = 0
  }

  process(inputs, outputs) {
    const input = inputs[0]
    const output = outputs[0] && outputs[0][0]

    if (!input || !input[0] || input[0].length === 0) {
      if (output) output.fill(0)
      return true
    }

    const channelData = input[0]
    if (output) output.set(channelData)

    let srcIndex = 0
    while (srcIndex < channelData.length) {
      const remaining = CHUNK_SIZE - this._bufferIndex
      const toCopy = Math.min(remaining, channelData.length - srcIndex)

      this._buffer.set(channelData.subarray(srcIndex, srcIndex + toCopy), this._bufferIndex)
      this._bufferIndex += toCopy
      srcIndex += toCopy

      if (this._bufferIndex === CHUNK_SIZE) {
        const pcm16 = new Int16Array(CHUNK_SIZE)
        for (let i = 0; i < CHUNK_SIZE; i += 1) {
          const sample = Math.max(-1, Math.min(1, this._buffer[i]))
          pcm16[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff
        }
        this.port.postMessage({ type: 'pcm', samples: pcm16 }, [pcm16.buffer])
        this._bufferIndex = 0
      }
    }

    return true
  }
}

registerProcessor('kvie-audio-processor', KVIEAudioProcessor)
