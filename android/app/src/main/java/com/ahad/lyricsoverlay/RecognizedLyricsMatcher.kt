package com.ahad.lyricsoverlay

import kotlin.math.abs

/** Pure, conservative scoring for the lyrics search performed after local audio recognition. */
internal object RecognizedLyricsMatcher {

    fun normalizedTokens(value: String): Set<String> = value
        .lowercase()
        .replace(Regex("""[^\p{L}\p{M}\p{N}]+"""), " ")
        .trim()
        .split(' ')
        .asSequence()
        .map(String::trim)
        .filter { it.length >= MIN_RECOGNIZED_TOKEN_LENGTH }
        .toSet()

    fun score(
        songDurationMs: Long,
        candidateDurationSeconds: Double,
        candidateLyrics: String,
        recognizedTokens: Set<String>
    ): Double {
        if (recognizedTokens.isEmpty()) return 0.0
        val candidateTokens = normalizedTokens(candidateLyrics)
        if (candidateTokens.isEmpty()) return 0.0

        val sharedTokens = recognizedTokens.intersect(candidateTokens)
        val usefulMatches = sharedTokens.count { token -> token.length >= MIN_USEFUL_TOKEN_LENGTH }
        if (usefulMatches < MIN_USEFUL_RECOGNIZED_MATCHES) return 0.0

        val targetDurationSeconds = songDurationMs.coerceAtLeast(1L) / 1_000.0
        val durationDifference = if (candidateDurationSeconds > 0.0) {
            abs(candidateDurationSeconds - targetDurationSeconds)
        } else {
            Double.MAX_VALUE
        }
        val allowedDifference = maxOf(
            MAX_DURATION_DIFFERENCE_SECONDS,
            targetDurationSeconds * MAX_DURATION_DIFFERENCE_RATIO
        )
        if (durationDifference > allowedDifference) return 0.0

        val overlap = sharedTokens.size.toDouble() / recognizedTokens.size.coerceAtMost(80)
        val durationScore = 1.0 - (durationDifference / allowedDifference).coerceIn(0.0, 1.0)
        return overlap * OVERLAP_WEIGHT + durationScore * DURATION_WEIGHT
    }

    fun isConfident(score: Double): Boolean = score >= MINIMUM_CONFIDENT_SCORE

    private const val MIN_RECOGNIZED_TOKEN_LENGTH = 2
    private const val MIN_USEFUL_TOKEN_LENGTH = 3
    private const val MIN_USEFUL_RECOGNIZED_MATCHES = 5
    private const val MAX_DURATION_DIFFERENCE_SECONDS = 12.0
    private const val MAX_DURATION_DIFFERENCE_RATIO = 0.08
    private const val OVERLAP_WEIGHT = 0.8
    private const val DURATION_WEIGHT = 0.2
    private const val MINIMUM_CONFIDENT_SCORE = 0.30
}
