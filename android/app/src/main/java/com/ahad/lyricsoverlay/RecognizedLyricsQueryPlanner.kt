package com.ahad.lyricsoverlay

import kotlin.math.abs

/** Builds a small, deterministic set of text-only searches from phrases recognized on the phone. */
internal object RecognizedLyricsQueryPlanner {

    fun plan(phrases: List<String>): List<String> {
        val phraseCandidates = if (phrases.size > 1) {
            phrases + phrases.joinToString(" ")
        } else {
            phrases
        }
        val normalized = phraseCandidates.flatMap { phrase ->
            val words = phrase.trim().replace(Regex("\\s+"), " ")
                .split(' ')
                .filter(String::isNotBlank)
            when {
                words.size in MIN_QUERY_WORDS..MAX_QUERY_WORDS -> listOf(words.joinToString(" "))
                words.size > MAX_QUERY_WORDS -> {
                    val lastStart = (words.size - PREFERRED_QUERY_WORDS).coerceAtLeast(0)
                    linkedSetOf(0, lastStart / 2, lastStart).map { start ->
                        words.drop(start).take(PREFERRED_QUERY_WORDS).joinToString(" ")
                    }
                }
                else -> emptyList()
            }
        }.filter { phrase -> phrase.length >= MIN_QUERY_CHARACTERS }
        if (normalized.isEmpty()) return emptyList()

        val frequencies = normalized.groupingBy(::normalize).eachCount()
        return normalized.distinctBy(::normalize)
            .sortedWith(
                compareByDescending<String> { frequencies[normalize(it)] ?: 0 }
                    .thenBy { abs(it.split(' ').size - PREFERRED_QUERY_WORDS) }
                    .thenBy { it.length }
            )
    }

    private fun normalize(value: String): String = value
        .lowercase()
        .replace(Regex("""[^\p{L}\p{N}]+"""), " ")
        .trim()

    private const val MIN_QUERY_WORDS = 2
    private const val MAX_QUERY_WORDS = 8
    private const val PREFERRED_QUERY_WORDS = 4
    private const val MIN_QUERY_CHARACTERS = 4
}
