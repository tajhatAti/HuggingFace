from __future__ import annotations

import unittest

from lyr_service.domain import AudioData, TimedSegment
from lyr_service.provider import LrcLibCandidate
from lyr_service.service import LyricsService, LyricsServiceError


def candidate(
    title="Song", plain="these are enough recognized lyric words for matching"
):
    return LrcLibCandidate(
        record_id=8,
        title=title,
        artist="Artist",
        album="Album",
        duration_seconds=60.0,
        plain_lyrics=plain,
        synced_lyrics="[00:01.00] these are enough recognized lyric words\n[00:05.00] for matching",
    )


class FakeProvider:
    def __init__(self, metadata=(), text=()):
        self.metadata = tuple(metadata)
        self.text = tuple(text)
        self.metadata_calls = 0
        self.text_calls = 0

    def search_metadata(self, title, artist, duration):
        del title, artist, duration
        self.metadata_calls += 1
        return self.metadata

    def search_text(self, phrase):
        del phrase
        self.text_calls += 1
        return self.text


class FakeRecognizer:
    def __init__(self):
        self.calls = 0

    def transcribe(self, samples, sample_rate, duration_seconds, language_label):
        del samples, sample_rate, duration_seconds, language_label
        self.calls += 1
        return (
            "these are enough recognized lyric words for matching in this song",
            (
                TimedSegment(1.0, 4.0, "these are enough recognized lyric words"),
                TimedSegment(5.0, 8.0, "for matching in this song"),
            ),
            "en",
        )


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.audio = AudioData(None, 16_000, 60.0, "song.mp3")

    def test_metadata_match_skips_whisper(self):
        provider = FakeProvider(metadata=(candidate(),))
        recognizer = FakeRecognizer()
        result = LyricsService(provider=provider, recognizer=recognizer).transcribe(
            self.audio,
            title="Song",
            artist="Artist",
        )
        self.assertEqual(result.source, "lrclib_metadata")
        self.assertEqual(recognizer.calls, 0)
        self.assertTrue(result.lines)

    def test_audio_evidence_can_select_synced_provider_result(self):
        provider = FakeProvider(text=(candidate(),))
        result = LyricsService(
            provider=provider, recognizer=FakeRecognizer()
        ).transcribe(self.audio)
        self.assertEqual(result.source, "lrclib_audio_match")
        self.assertGreater(provider.text_calls, 0)

    def test_whisper_fallback_returns_lyr_compatible_lrc(self):
        result = LyricsService(
            provider=FakeProvider(), recognizer=FakeRecognizer()
        ).transcribe(
            self.audio,
            title="Unlisted",
            artist="Private",
        )
        self.assertEqual(result.source, "whisper_ai")
        self.assertIn("[ti:Unlisted]", result.synced_lyrics)
        self.assertGreaterEqual(result.synced_lyrics.count("["), 4)
        self.assertTrue(result.warnings)

    def test_missing_recognizer_has_clear_online_error(self):
        with self.assertRaisesRegex(LyricsServiceError, "temporarily unavailable"):
            LyricsService(provider=FakeProvider(), recognizer=None).transcribe(
                self.audio
            )


if __name__ == "__main__":
    unittest.main()
