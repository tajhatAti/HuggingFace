package com.ahad.lyricsoverlay

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class RecognizedLyricsMatcherTest {

    @Test
    fun rejectsCandidateWithFewerThanFiveUsefulSharedWords() {
        val recognized = RecognizedLyricsMatcher.normalizedTokens(
            "নদীর জলে আকাশ ভাসে হারানো দিনের কথা মনে পড়ে"
        )
        val score = RecognizedLyricsMatcher.score(
            songDurationMs = 180_000L,
            candidateDurationSeconds = 180.0,
            candidateLyrics = "নদীর জলে আকাশ ভাসে সম্পূর্ণ আলাদা একটি গান",
            recognizedTokens = recognized
        )

        assertEquals(0.0, score, 0.0)
        assertFalse(RecognizedLyricsMatcher.isConfident(score))
    }

    @Test
    fun rejectsSparseOverlapEvenWhenFiveWordsAndDurationMatch() {
        val recognizedText = (1..50).joinToString(" ") { "heardword$it" }
        val candidateText = (1..5).joinToString(" ") { "heardword$it" }
        val score = RecognizedLyricsMatcher.score(
            songDurationMs = 200_000L,
            candidateDurationSeconds = 200.0,
            candidateLyrics = candidateText,
            recognizedTokens = RecognizedLyricsMatcher.normalizedTokens(recognizedText)
        )

        assertTrue(score > 0.0)
        assertFalse(RecognizedLyricsMatcher.isConfident(score))
    }

    @Test
    fun rejectsOtherwiseStrongLyricsWhenRecordingDurationIsImplausible() {
        val recognized = RecognizedLyricsMatcher.normalizedTokens(
            "তুমি আমার সকাল তুমি আমার রাত ফিরে এসো আবার কাছে"
        )
        val score = RecognizedLyricsMatcher.score(
            songDurationMs = 180_000L,
            candidateDurationSeconds = 260.0,
            candidateLyrics = "তুমি আমার সকাল তুমি আমার রাত ফিরে এসো আবার কাছে",
            recognizedTokens = recognized
        )

        assertEquals(0.0, score, 0.0)
        assertFalse(RecognizedLyricsMatcher.isConfident(score))
    }

    @Test
    fun acceptsStrongLyricOverlapWithPlausibleDuration() {
        val recognized = RecognizedLyricsMatcher.normalizedTokens(
            "তুমি আমার সকাল তুমি আমার রাত ফিরে এসো আবার কাছে"
        )
        val score = RecognizedLyricsMatcher.score(
            songDurationMs = 180_000L,
            candidateDurationSeconds = 184.0,
            candidateLyrics = "তুমি আমার সকাল তুমি আমার রাত ফিরে এসো আবার কাছে দূরের পাখি",
            recognizedTokens = recognized
        )

        assertTrue(score >= 0.30)
        assertTrue(RecognizedLyricsMatcher.isConfident(score))
    }
}
