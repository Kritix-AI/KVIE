import unittest

from Backend.voice.WakeWord import WakeWordDetector, WakeWordConfig


class WakeWordMatchingTests(unittest.TestCase):
    def test_requires_multiple_tokens_for_a_match(self):
        config = WakeWordConfig(wake_words=["hey kritix"], sensitivity=0.65)
        detector = WakeWordDetector(config=config)

        self.assertIsNone(detector._check_wake_word("thank you very much"))
        self.assertEqual(detector._check_wake_word("hey kritix"), "hey kritix")
        self.assertEqual(detector._check_wake_word("hello hey kritix"), "hey kritix")


if __name__ == '__main__':
    unittest.main()
