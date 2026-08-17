from __future__ import annotations

import unittest

from lyr_service.domain import LyricLine, LyricsDocument, TimedSegment


class DomainTests(unittest.TestCase):
    def test_invalid_intervals_are_rejected(self):
        with self.assertRaises(ValueError):
            TimedSegment(2.0, 1.0, "bad")
        with self.assertRaises(ValueError):
            LyricLine(1000, 1000, "bad")
        with self.assertRaises(ValueError):
            LyricLine(0, 1000, "")

    def test_document_serializes_for_android(self):
        line = LyricLine(1000, 2500, "hello")
        document = LyricsDocument(
            source="whisper_ai",
            title="Song",
            artist="Artist",
            language="en",
            duration_seconds=3.0,
            plain_lyrics="hello",
            synced_lyrics="[00:01.00] hello",
            lines=(line,),
            warnings=("review",),
        )
        payload = document.to_dict()
        self.assertEqual(payload["lines"][0]["start_ms"], 1000)
        self.assertEqual(payload["warnings"], ["review"])


if __name__ == "__main__":
    unittest.main()
