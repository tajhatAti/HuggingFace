from __future__ import annotations

import unittest

from lyr_service.provider import (
    LrcLibCandidate,
    LrcLibClient,
    LyricsProviderError,
    choose_metadata_candidate,
    choose_transcript_candidate,
    transcript_phrases,
)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.closed = False

    def json(self):
        return self._payload

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.headers = {}
        self.last_call = None

    def mount(self, *args, **kwargs):
        del args, kwargs

    def get(self, url, **kwargs):
        self.last_call = (url, kwargs)
        return self.response


def candidate(**changes):
    values = {
        "record_id": 1,
        "title": "আমার সোনার বাংলা",
        "artist": "Singer",
        "album": "Album",
        "duration_seconds": 180.0,
        "plain_lyrics": "আমার সোনার বাংলা আমি তোমায় ভালোবাসি",
        "synced_lyrics": "[00:01.00] আমার সোনার বাংলা\n[00:04.00] আমি তোমায় ভালোবাসি",
    }
    values.update(changes)
    return LrcLibCandidate(**values)


class ProviderTests(unittest.TestCase):
    def test_maps_bounded_lrclib_results_on_fixed_host(self):
        response = FakeResponse(
            payload=[
                {
                    "id": 7,
                    "trackName": "Song",
                    "artistName": "Artist",
                    "albumName": "Album",
                    "duration": 120,
                    "plainLyrics": "one two",
                    "syncedLyrics": "[00:01.00] one two",
                }
            ]
        )
        session = FakeSession(response)
        results = LrcLibClient(session=session).search_metadata("Song", "Artist", 120)
        self.assertEqual(results[0].record_id, 7)
        self.assertEqual(session.last_call[0], "https://lrclib.net/api/search")
        self.assertFalse(session.last_call[1]["allow_redirects"])
        self.assertTrue(response.closed)

    def test_rejects_provider_redirect(self):
        client = LrcLibClient(
            session=FakeSession(FakeResponse(status_code=302, payload=[]))
        )
        with self.assertRaisesRegex(LyricsProviderError, "redirect"):
            client.search_text("a useful lyric phrase")

    def test_metadata_selection_checks_title_artist_duration_and_script(self):
        good = candidate()
        wrong_duration = candidate(record_id=2, duration_seconds=260.0)
        romanized = candidate(
            record_id=3,
            plain_lyrics="amar shonar bangla",
            synced_lyrics="[00:01.00] amar shonar bangla",
        )
        match, score = choose_metadata_candidate(
            (wrong_duration, romanized, good),
            title="আমার সোনার বাংলা",
            artist="Singer",
            duration_seconds=181.0,
        )
        self.assertEqual(match, good)
        self.assertGreater(score, 0.8)

    def test_transcript_selection_requires_word_overlap(self):
        good = candidate()
        bad = candidate(
            record_id=2,
            plain_lyrics="completely unrelated words from another recording",
            synced_lyrics="[00:01.00] completely unrelated words",
        )
        match, score = choose_transcript_candidate(
            (bad, good),
            transcript="আমার সোনার বাংলা আমি তোমায় ভালোবাসি প্রতিদিন",
            duration_seconds=180.0,
            bengali_expected=True,
        )
        self.assertEqual(match, good)
        self.assertGreater(score, 0.5)

    def test_recognized_queries_are_bounded_to_two(self):
        phrases = transcript_phrases(
            "this is one sufficiently long lyric phrase। "
            "এটি আরেকটি অনেক লম্বা গানের লাইন। third useful lyric phrase appears here"
        )
        self.assertLessEqual(len(phrases), 2)
        self.assertTrue(all(len(phrase.split()) >= 4 for phrase in phrases))


if __name__ == "__main__":
    unittest.main()
