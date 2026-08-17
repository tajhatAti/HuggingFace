package com.ahad.lyricsoverlay

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class CommunitySongIdentityParserTest {

    @Test
    fun malformedOrIncompleteResponsesAreIgnored() {
        assertTrue(CommunitySongIdentityParser.parseGeniusResponse("not json").isEmpty())
        assertTrue(CommunitySongIdentityParser.parseGeniusResponse("{}").isEmpty())
        assertTrue(
            CommunitySongIdentityParser.parseGeniusResponse(
                response(
                    hit(
                        title = "Missing artist",
                        artist = "",
                        matchedWords = 8,
                        exactWords = 8
                    )
                )
            ).isEmpty()
        )
    }

    @Test
    fun weakCommunityMatchesNeverBecomeIdentityHints() {
        val parsed = CommunitySongIdentityParser.parseGeniusResponse(
            response(
                hit("Too few words", "Artist A", matchedWords = 3, exactWords = 3),
                hit("Too few exact", "Artist B", matchedWords = 6, exactWords = 2),
                hit("Weak exact ratio", "Artist C", matchedWords = 10, exactWords = 6)
            )
        )

        assertTrue(parsed.isEmpty())
    }

    @Test
    fun acceptsFallbackArtistAndOrdersStrongestMatchFirst() {
        val parsed = CommunitySongIdentityParser.parseGeniusResponse(
            response(
                hit("Second song", "Artist Two", matchedWords = 7, exactWords = 5),
                hit(
                    title = "First song",
                    artist = "Artist One",
                    matchedWords = 8,
                    exactWords = 7,
                    useNestedArtist = true
                )
            )
        )

        assertEquals(listOf("First song", "Second song"), parsed.map { it.title })
        assertEquals("Artist One", parsed.first().artist)
    }

    @Test
    fun deduplicatesCaseInsensitivelyAndKeepsHigherQualityHit() {
        val parsed = CommunitySongIdentityParser.parseGeniusResponse(
            response(
                hit("Same Song", "Same Artist", matchedWords = 6, exactWords = 5),
                hit("same song", "same artist", matchedWords = 9, exactWords = 8),
                hit("Other Song", "Other Artist", matchedWords = 8, exactWords = 7)
            ),
            limit = 2
        )

        assertEquals(2, parsed.size)
        assertEquals("same song", parsed.first().title)
        assertEquals(8, parsed.first().exactWords)
        assertEquals(1, parsed.count { it.title.equals("same song", ignoreCase = true) })
    }

    @Test
    fun nonPositiveLimitReturnsNothing() {
        val valid = response(hit("A valid song", "A valid artist", 5, 4))
        assertTrue(CommunitySongIdentityParser.parseGeniusResponse(valid, limit = 0).isEmpty())
    }

    private fun response(vararg hits: String): String =
        """{"response":{"sections":[{"hits":[${hits.joinToString(",")}]}]}}"""

    private fun hit(
        title: String,
        artist: String,
        matchedWords: Int,
        exactWords: Int,
        useNestedArtist: Boolean = false
    ): String {
        val artistJson = if (useNestedArtist) {
            "\"primary_artist_names\":\"\",\"primary_artist\":{\"name\":\"${escape(artist)}\"}"
        } else {
            "\"primary_artist_names\":\"${escape(artist)}\""
        }
        return """{"matched_words":$matchedWords,"nb_exact_words":$exactWords,"result":{"title":"${escape(title)}",$artistJson}}"""
    }

    private fun escape(value: String): String = value
        .replace("\\", "\\\\")
        .replace("\"", "\\\"")
}
