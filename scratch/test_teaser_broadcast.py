import unittest
from app.handlers.teaser_broadcast import make_teaser_preview

class TestTeaserPreview(unittest.TestCase):
    def test_short_text(self):
        text = "Hello world! Short text."
        self.assertEqual(make_teaser_preview(text), text)

    def test_exact_200_chars(self):
        text = "a" * 200
        self.assertEqual(make_teaser_preview(text), text)

    def test_long_text_truncation_with_space(self):
        # 195 chars of 'a', a space, then 10 chars of 'b' (total 206 chars)
        text = "a" * 195 + " " + "b" * 10
        preview = make_teaser_preview(text)
        self.assertTrue(preview.endswith("..."))
        # Should cut at the space (index 195)
        self.assertEqual(preview, "a" * 195 + "...")
        self.assertTrue(len(preview) <= 203)

    def test_long_text_no_space(self):
        text = "a" * 250
        preview = make_teaser_preview(text)
        # Should take the first 200 chars and add "..."
        self.assertEqual(preview, "a" * 200 + "...")

if __name__ == '__main__':
    unittest.main()
