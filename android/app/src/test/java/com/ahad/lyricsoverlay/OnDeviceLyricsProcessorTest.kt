package com.ahad.lyricsoverlay

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class OnDeviceLyricsProcessorTest {

    @Test
    fun audioOnlyCreatesExplicitEndsAndKeepsVocalGapBlank() {
        val raw = OnDeviceLyricsProcessor.audioOnlyLrc(
            segments = listOf(
                OnDeviceLyricsProcessor.Segment(1_000L, 3_000L, "আমি এই শহরে"),
                OnDeviceLyricsProcessor.Segment(6_000L, 8_200L, "আর ফিরে আসিনি")
            ),
            songDurationMs = 10_000L
        )

        val lines = LrcParser.parse(raw)
        assertEquals(2, lines.size)
        assertEquals(3_000L, lines[0].endTimestampMs)
        assertEquals(8_200L, lines[1].endTimestampMs)
        assertEquals(-1, LrcParser.lineIndexAt(lines, 4_500L))
        assertEquals(1, LrcParser.lineIndexAt(lines, 7_000L))
    }

    @Test
    fun knownLyricsPreservesPastedBengaliPhrasesAndBuildsEnds() {
        val raw = OnDeviceLyricsProcessor.alignKnownLyricsLrc(
            knownLyrics = "এই শহরে আমি নেই\nফিরে আসবো কোনো দিন",
            segments = listOf(
                OnDeviceLyricsProcessor.Segment(900L, 3_200L, "এই শহরে আমি নেই"),
                OnDeviceLyricsProcessor.Segment(5_600L, 8_400L, "ফিরে আসবো কোন দিন")
            ),
            songDurationMs = 10_000L
        )

        val lines = LrcParser.parse(raw)
        assertEquals(listOf("এই শহরে আমি নেই", "ফিরে আসবো কোনো দিন"), lines.map(LrcLine::text))
        assertTrue(lines.all { (it.endTimestampMs ?: 0L) > it.timestampMs })
        assertTrue(lines[0].timestampMs < 1_100L)
        assertTrue(lines[1].timestampMs >= 5_000L)
        assertTrue((lines[0].endTimestampMs ?: Long.MAX_VALUE) < lines[1].timestampMs)
    }

    @Test
    fun metadataOnlineTimingNeverReplacesExactPastedPhrases() {
        val pasted = "আমার EXACT কথা!\nদ্বিতীয় লাইন, অপরিবর্তিত।"
        val raw = OnDeviceLyricsProcessor.alignKnownLyricsToTimedLrc(
            knownLyrics = pasted,
            timedLrc = """
                [00:01.00]unrelated online words
                [00:03.20]
                [00:06.00]different provider text
                [00:08.40]
            """.trimIndent(),
            songDurationMs = 10_000L
        )

        val lines = LrcParser.parse(raw)
        assertEquals(listOf("আমার EXACT কথা!", "দ্বিতীয় লাইন, অপরিবর্তিত।"), lines.map(LrcLine::text))
        assertTrue(lines.all { (it.endTimestampMs ?: 0L) > it.timestampMs })
        assertEquals(-1, LrcParser.lineIndexAt(lines, 4_500L))
    }

    @Test
    fun recognizedOnlineStartOnlyTimingKeepsPastedTextAndBoundsFinalCue() {
        val raw = OnDeviceLyricsProcessor.alignKnownLyricsToTimedLrc(
            knownLyrics = "প্রথম লাইন\nদ্বিতীয় লাইন\nশেষ লাইন ঠিক",
            timedLrc = """
                [00:02.00]প্রথম লাইন
                [00:05.00]দ্বিতীয় লাইন
                [00:09.00]শেষ লাইন
            """.trimIndent(),
            songDurationMs = 10_000L
        )

        val lines = LrcParser.parse(raw)
        assertEquals(listOf("প্রথম লাইন", "দ্বিতীয় লাইন", "শেষ লাইন ঠিক"), lines.map(LrcLine::text))
        assertEquals(10_000L, lines.last().endTimestampMs)
        assertTrue(lines.last().timestampMs < lines.last().endTimestampMs!!)
        assertEquals(-1, LrcParser.lineIndexAt(lines, 10_000L))
    }

    @Test
    fun musicMarkersAreDroppedAndImmediateOverlapDuplicatesAreMerged() {
        val cleaned = OnDeviceLyricsProcessor.cleanAndMergeSegments(
            segments = listOf(
                OnDeviceLyricsProcessor.Segment(0L, 1_000L, "[Music]"),
                OnDeviceLyricsProcessor.Segment(1_000L, 2_800L, "আমার গান"),
                OnDeviceLyricsProcessor.Segment(2_500L, 3_600L, "আমার গান")
            ),
            songDurationMs = 5_000L
        )

        assertEquals(1, cleaned.size)
        assertEquals("আমার গান", cleaned.single().text)
        assertEquals(1_000L, cleaned.single().startMs)
        assertEquals(3_600L, cleaned.single().endMs)
        assertFalse(cleaned.single().text.contains("Music", ignoreCase = true))
    }
}
