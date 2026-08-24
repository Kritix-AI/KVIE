import unittest

from Backend.voice.WakeWord import _open_input_stream


class DummyPyAudio:
    def __init__(self):
        self.calls = []
        self.stream = object()

    def open(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs['channels'] == 1:
            raise ValueError('Invalid number of channels')
        return self.stream


class OpenInputStreamTests(unittest.TestCase):
    def test_falls_back_to_second_channel_count(self):
        p = DummyPyAudio()

        stream = _open_input_stream(p, sample_rate=16000, frames_per_buffer=1024, device_index=3)

        self.assertIs(stream, p.stream)
        self.assertEqual(len(p.calls), 2)
        self.assertEqual(p.calls[0]['channels'], 1)
        self.assertEqual(p.calls[1]['channels'], 2)


if __name__ == '__main__':
    unittest.main()
