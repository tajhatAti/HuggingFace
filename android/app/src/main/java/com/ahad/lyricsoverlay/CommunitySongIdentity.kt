package com.ahad.lyricsoverlay

import org.json.JSONObject
import java.util.Locale

/** A title/artist hint discovered from recognized lyric text; song audio is never sent. */
internal data class CommunitySongIdentity(
    val title: String,
    val artist: String,
    val matchedWords: Int,
    val exactWords: Int
)

/**
 * Parses Genius' public text-search response only as an identity hint. Lyr never downloads Genius
 * lyric pages: a discovered title and artist are sent to LRCLIB for a synchronized candidate, then
 * verified against local recognized words and recording duration before automatic adoption.
 */
internal object CommunitySongIdentityParser {

    fun parseGeniusResponse(body: String, limit: Int = 5): List<CommunitySongIdentity> {
        if (limit <= 0) return emptyList()
        return try {
            val sections = JSONObject(body)
                .optJSONObject("response")
                ?.optJSONArray("sections")
                ?: return emptyList()
            val unique = LinkedHashMap<String, CommunitySongIdentity>()
            for (sectionIndex in 0 until sections.length()) {
                val hits = sections.optJSONObject(sectionIndex)?.optJSONArray("hits") ?: continue
                for (hitIndex in 0 until hits.length()) {
                    val hit = hits.optJSONObject(hitIndex) ?: continue
                    val matchedWords = hit.optInt("matched_words", 0)
                    val exactWords = hit.optInt("nb_exact_words", 0)
                    if (matchedWords < MIN_MATCHED_WORDS ||
                        exactWords < MIN_EXACT_WORDS ||
                        exactWords.toDouble() / matchedWords.coerceAtLeast(1) < MIN_EXACT_RATIO
                    ) {
                        continue
                    }
                    val result = hit.optJSONObject("result") ?: continue
                    val title = result.optString("title").trim()
                    val artist = result.optString("primary_artist_names")
                        .ifBlank { result.optJSONObject("primary_artist")?.optString("name").orEmpty() }
                        .trim()
                    if (title.isBlank() || artist.isBlank()) continue
                    val key = "${title.lowercase(Locale.ROOT)}\u0000${artist.lowercase(Locale.ROOT)}"
                    val identity = CommunitySongIdentity(title, artist, matchedWords, exactWords)
                    val previous = unique[key]
                    if (previous == null || identity.exactWords > previous.exactWords) {
                        unique[key] = identity
                    }
                }
            }
            unique.values
                .sortedWith(
                    compareByDescending<CommunitySongIdentity> { it.exactWords }
                        .thenByDescending { it.matchedWords }
                )
                .take(limit)
        } catch (_: Exception) {
            emptyList()
        }
    }

    private const val MIN_MATCHED_WORDS = 4
    private const val MIN_EXACT_WORDS = 3
    private const val MIN_EXACT_RATIO = 0.70
}
