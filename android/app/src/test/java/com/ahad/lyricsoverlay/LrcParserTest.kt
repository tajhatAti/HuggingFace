package com.ahad.lyricsoverlay

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class LrcParserTest {

    @Test
    fun emptyTimestampAfterLyricBecomesExclusiveEnd() {
        val lines = LrcParser.parse(
            """
            [00:10.00]প্রথম বাক্য
            [00:12.50]
            [00:15.00]দ্বিতীয় বাক্য
            [00:18.25]
            """.trimIndent()
        )

        assertEquals(2, lines.size)
        assertEquals(10_000L, lines[0].timestampMs)
        assertEquals(12_500L, lines[0].endTimestampMs)
        assertEquals(-1, LrcParser.lineIndexAt(lines, 12_500L))
        assertEquals(-1, LrcParser.lineIndexAt(lines, 14_999L))
        assertEquals(1, LrcParser.lineIndexAt(lines, 15_000L))
        assertEquals(-1, LrcParser.lineIndexAt(lines, 18_250L))
    }

    @Test
    fun ordinaryLrcKeepsPreviousCompatibility() {
        val lines = LrcParser.parse("[00:01.00]One\n[00:03.00]Two")

        assertNull(lines[0].endTimestampMs)
        assertEquals(0, LrcParser.lineIndexAt(lines, 2_999L))
        assertEquals(1, LrcParser.lineIndexAt(lines, 9_000L))
    }

    @Test
    fun serializeShiftAndFitPreserveCueEnds() {
        val raw = LrcParser.serialize(listOf(LrcLine(1_000L, "Line", 2_250L)))
        assertEquals("[00:01.00] Line\n[00:02.25]", raw)

        val shifted = LrcParser.parse(LrcParser.shiftTimestamps(raw, 500L)).single()
        assertEquals(1_500L, shifted.timestampMs)
        assertEquals(2_750L, shifted.endTimestampMs)

        val fitted = LrcParser.parse(LrcParser.fitToDuration(raw, 10_000L, 20_000L)).single()
        assertEquals(2_000L, fitted.timestampMs)
        assertEquals(4_500L, fitted.endTimestampMs)
    }
}
