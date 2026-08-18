from __future__ import annotations

import unittest

from lyr_service.domain import AudioData, TimedSegment
from lyr_service.provider import LrcLibCandidate, SongIdentity
from lyr_service.service import LyricsService, LyricsServiceError


def candidate(
    title="Song",
    artist="Artist",
    plain="these are enough recognized lyric words for matching",
    synced="[00:01.00] these are enough recognized lyric words\n[00:05.00] for matching",
):
    return LrcLibCandidate(
        record_id=8,
        title=title,
        artist=artist,
        album="Album",
        duration_seconds=60.0,
        plain_lyrics=plain,
        synced_lyrics=synced,
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


class FilenameProvider(FakeProvider):
    def search_title_identities(self, query):
        self.filename_query = query
        return (SongIdentity("Amar Sonar Bangla", "Rabindranath Tagore", 3, 3),)


class FakeRecognizer:
    def __init__(self):
        self.calls = 0
        self.language_labels = []

    def transcribe(self, samples, sample_rate, duration_seconds, language_label):
        del samples, sample_rate, duration_seconds
        self.calls += 1
        self.language_labels.append(language_label)
        return (
            "these are enough recognized lyric words for matching in this song",
            (
                TimedSegment(1.0, 4.0, "these are enough recognized lyric words"),
                TimedSegment(5.0, 8.0, "for matching in this song"),
            ),
            "en",
        )


class PreviewRecognizer(FakeRecognizer):
    def preview(self, samples, sample_rate, duration_seconds, language_label):
        del samples, sample_rate, duration_seconds, language_label
        return "আমার সোনার বাংলা আমি তোমায় ভালোবাসি প্রতিদিন", "bn", 0.94

    def transcribe(self, samples, sample_rate, duration_seconds, language_label):
        del samples, sample_rate, duration_seconds
        self.calls += 1
        self.language_labels.append(language_label)
        return (
            "আমার সোনার বাংলা আমি তোমায় ভালোবাসি চিরদিন তোমার আকাশ বাতাস",
            (
                TimedSegment(1.0, 4.0, "আমার সোনার বাংলা আমি তোমায় ভালোবাসি"),
                TimedSegment(5.0, 8.0, "চিরদিন তোমার আকাশ তোমার বাতাস"),
            ),
            "bn",
        )


class MixedScriptRecognizer(PreviewRecognizer):
    def transcribe(self, samples, sample_rate, duration_seconds, language_label):
        del samples, sample_rate, duration_seconds, language_label
        text = (
            "মাটির রোদে আঁকা নতুন দিনের খোঁজে সময়ের চাকা ঘুরে যায় "
            "বিধাতার স্পর্শে জাগা هذي كلمات 있으니까 laștiga"
        )
        return text, (TimedSegment(1.0, 8.0, text),), "bn"


class FakeIdentifier:
    def identify(self, samples, sample_rate, duration_seconds):
        del samples, sample_rate, duration_seconds
        return SongIdentity("Matir Roud", "Aftermath", 100, 100)


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

    def test_ai_preview_finds_synced_result_before_full_song(self):
        provider = FakeProvider(
            text=(
                candidate(
                    title="আমার সোনার বাংলা",
                    plain="আমার সোনার বাংলা আমি তোমায় ভালোবাসি প্রতিদিন",
                    synced="[00:01.00] আমার সোনার বাংলা\n[00:05.00] আমি তোমায় ভালোবাসি প্রতিদিন",
                ),
            )
        )
        recognizer = PreviewRecognizer()
        result = LyricsService(provider=provider, recognizer=recognizer).transcribe(
            self.audio
        )
        self.assertEqual(result.source, "lrclib_audio_match")
        self.assertEqual(result.language, "bn")
        self.assertEqual(recognizer.calls, 0)

    def test_fingerprint_finds_synced_lyrics_despite_random_filename(self):
        synced = (
            "[00:01.00] বিধাতার স্পর্শে জাগা নতুন দিনেরই খোঁজে\n"
            "[00:05.00] সময়ের চাকা মাটির রোদে আঁকা"
        )
        provider = FakeProvider(
            metadata=(
                candidate(
                    title="Matir Roud",
                    artist="Aftermath",
                    plain="বিধাতার স্পর্শে জাগা সময়ের চাকা মাটির রোদে আঁকা",
                    synced=synced,
                ),
            )
        )
        audio = AudioData(None, 16_000, 60.0, "292nsksksk.mp3")
        recognizer = PreviewRecognizer()
        result = LyricsService(
            provider=provider,
            recognizer=recognizer,
            identifier=FakeIdentifier(),
        ).transcribe(audio)
        self.assertEqual(result.source, "lrclib_audio_match")
        self.assertEqual(result.title, "Matir Roud")
        self.assertEqual(result.artist, "Aftermath")
        self.assertEqual(recognizer.calls, 0)

    def test_bengali_preview_forces_native_script_full_transcription(self):
        recognizer = PreviewRecognizer()
        result = LyricsService(
            provider=FakeProvider(), recognizer=recognizer
        ).transcribe(self.audio)
        self.assertEqual(result.source, "whisper_ai")
        self.assertEqual(result.language, "bn")
        self.assertEqual(recognizer.language_labels, ["বাংলা"])

    def test_online_verified_filename_refills_fallback_identity(self):
        provider = FilenameProvider()
        recognizer = PreviewRecognizer()
        audio = AudioData(None, 16_000, 60.0, "amar-sonar-bangla-public-domain.ogg")
        result = LyricsService(provider=provider, recognizer=recognizer).transcribe(audio)
        self.assertEqual(provider.filename_query, "amar sonar bangla")
        self.assertEqual(result.title, "Amar Sonar Bangla")
        self.assertEqual(result.artist, "Rabindranath Tagore")

    def test_mixed_script_bengali_gibberish_is_rejected(self):
        with self.assertRaisesRegex(LyricsServiceError, "mixed-script or Banglish"):
            LyricsService(
                provider=FakeProvider(), recognizer=MixedScriptRecognizer()
            ).transcribe(self.audio)

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
