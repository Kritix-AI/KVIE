import unittest

from Backend.voice.DSP import DSPPipeline


class AudioProcessingFallbackTests(unittest.TestCase):
    """DSP pipeline can process audio without PyAudio dependencies."""

    def test_process_pcm_to_float(self):
        pipeline = DSPPipeline(input_rate=44100, target_rate=16000)
        # Generate a simple int16 sine wave (440 Hz)
        import struct
        import math
        samples = [int(32767 * math.sin(2 * math.pi * 440 * i / 44100))
                   for i in range]
        pcm = struct.pack('<' + 'h' * len(samples), *samples)
        result = pipeline.process(pcm)
        self.assertEqual(result.dtype.name, 'float32')
        self.assertGreater(len(result), 0)

    def test_noise_gate_suppresses_silence(self):
        pipeline = DSPPipeline(input_rate=16000, target_rate=16000, noise_gate_db=-60.0)
        silence = b'\x00' * 3200  # 100ms of silence
        result = pipeline.process(silence)
        self.assertTrue(all(abs(v) < 1e-4 for v in result))


if __name__ == '__main__':
    unittest.main()
