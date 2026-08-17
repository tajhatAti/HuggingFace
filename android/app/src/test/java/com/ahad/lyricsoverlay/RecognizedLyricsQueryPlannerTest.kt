package com.ahad.lyricsoverlay

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class RecognizedLyricsQueryPlannerTest {

    @Test
    fun ignoresFragmentsTooShortForAUsefulCommunitySearch() {
        assertTrue(RecognizedLyricsQueryPlanner.plan(listOf("hello")).isEmpty())
        assertTrue(RecognizedLyricsQueryPlanner.plan(listOf("a b")).isEmpty())
    }

    @Test
    fun deduplicatesNormalizedPhrasesAndPrioritizesRepeatedEvidence() {
        val queries = RecognizedLyricsQueryPlanner.plan(
            listOf("Hello, from the other side", "hello from the other side")
        )

        assertEquals("Hello, from the other side", queries.first())
        assertEquals(1, queries.count { it.lowercase().replace(",", "") == "hello from the other side" })
    }

    @Test
    fun boundsLongRecognitionToBeginningMiddleAndEndingWindows() {
        val queries = RecognizedLyricsQueryPlanner.plan(
            listOf("one two three four five six seven eight nine ten")
        )

        assertEquals(3, queries.size)
        assertTrue("one two three four" in queries)
        assertTrue("four five six seven" in queries)
        assertTrue("seven eight nine ten" in queries)
        assertTrue(queries.all { it.split(' ').size == 4 })
    }

    @Test
    fun preservesBengaliUnicodeInTextOnlyQueries() {
        val queries = RecognizedLyricsQueryPlanner.plan(
            listOf("তুমি আমার সকাল তুমি আমার রাত")
        )

        assertTrue(queries.isNotEmpty())
        assertTrue(queries.all { query -> query.any { it in '\u0980'..'\u09FF' } })
    }
}
