from __future__ import annotations

import unittest

from lyr_service.domain import TimedSegment
from lyr_service.lyrics import (
    contains_bengali,
    parse_lrc,
    plain_from_lrc,
    segments_to_lines,
    serialize_lrc,
)


class LyricsTests(unittest.TestCase):
    def test_segments_split_long_text_and_emit_explicit_ends(self):
        segments = (
            TimedSegment(
                1.0,
                5.0,
                "one two three four five six seven eight nine ten eleven twelve thirteen",
            ),
            TimedSegment(8.0, 10.0, "শেষ গানের লাইন"),
        )
        lines = segments_to_lines(segments, 12.0)
        self.assertEqual(len(lines), 3)
        self.assertLessEqual(len(lines[0].text.split()), 12)
        self.assertEqual(lines[-1].text, "শেষ গানের লাইন")
        raw = serialize_lrc(lines, title="Test", artist="Singer")
        self.assertIn("[ti:Test]", raw)
        self.assertIn("[00:05.00]", raw)
        self.assertIn("শেষ গানের লাইন", raw)

    def test_parser_understands_standard_and_explicit_end_lrc(self):
        raw = "[ar:Artist]\n[00:01.00] First\n[00:03.40]\n[00:06.00] Second"
        lines = parse_lrc(raw)
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0].start_ms, 1_000)
        self.assertEqual(lines[0].end_ms, 3_400)
        self.assertEqual(lines[1].text, "Second")
        self.assertEqual(plain_from_lrc(raw), "First\nSecond")

    def test_duplicate_neighboring_segments_merge(self):
        lines = segments_to_lines(
            (TimedSegment(0.0, 2.0, "same line"), TimedSegment(2.1, 4.0, "Same line")),
            5.0,
        )
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].end_ms, 4_000)

    def test_non_lyric_markers_are_removed(self):
        lines = segments_to_lines(
            (TimedSegment(0.0, 2.0, "[Music]"), TimedSegment(3.0, 5.0, "Actual lyric")),
            6.0,
        )
        self.assertEqual([line.text for line in lines], ["Actual lyric"])

    def test_bengali_detection(self):
        self.assertTrue(contains_bengali("আমার গান"))
        self.assertFalse(contains_bengali("amar gaan"))


if __name__ == "__main__":
    unittest.main()
