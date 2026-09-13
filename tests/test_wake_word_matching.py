import unittest

from Backend.voice.STT import _strip_wake_phrase


class WakeWordStrippingTests(unittest.TestCase):
    """Wake-word stripping is now a no-op (returns text as-is)."""

    def test_returns_text_as_is(self):
        self.assertEqual(_strip_wake_phrase("hello world"), "hello world")

    def test_returns_empty_for_empty_input(self):
        self.assertEqual(_strip_wake_phrase(""), "")

    def test_strips_whitespace(self):
        self.assertEqual(_strip_wake_phrase("  hello  "), "hello")


if __name__ == '__main__':
    unittest.main()
