package com.ahad.lyricsoverlay

import java.text.Normalizer
import java.util.Locale
import kotlin.math.max
import kotlin.math.min

/** Pure Kotlin phrase cleanup and known-text alignment, kept independent of Android for tests. */
object OnDeviceLyricsProcessor {

    data class Segment(
        val startMs: Long,
        val endMs: Long,
        val text: String
    )

    private data class TimedWord(
        val normalized: String,
        val startMs: Long,
        val endMs: Long
    )

    fun audioOnlyLrc(segments: List<Segment>, songDurationMs: Long): String {
        val cues = segments
            .flatMap(::splitSegmentIntoCues)
            .let(::mergeImmediateDuplicates)
            .let { sanitizeCues(it, songDurationMs) }
        return LrcParser.serialize(cues)
    }

    /**
     * Uses an online or sidecar LRC only as a timing reference. The returned cue text always comes
     * from [knownLyrics], so an imperfect online transcription can never replace what was pasted.
     */
    fun alignKnownLyricsToTimedLrc(
        knownLyrics: String,
        timedLrc: String,
        songDurationMs: Long
    ): String {
        val lines = LrcParser.parse(timedLrc)
        if (lines.isEmpty()) return timedLrc
        val effectiveDurationMs = songDurationMs.takeIf { it > 0L }
            ?: lines.last().endTimestampMs
            ?: (lines.last().timestampMs + DEFAULT_TIMING_REFERENCE_CUE_DURATION_MS)
        val segments = lines.mapIndexed { index, line ->
            val nextStart = lines.getOrNull(index + 1)?.timestampMs
            val endMs = line.endTimestampMs
                ?: nextStart
                ?: (line.timestampMs + DEFAULT_TIMING_REFERENCE_CUE_DURATION_MS)
                    .coerceAtMost(effectiveDurationMs)
            Segment(
                startMs = line.timestampMs,
                endMs = endMs.coerceAtLeast(line.timestampMs + MIN_TIMING_REFERENCE_CUE_DURATION_MS),
                text = line.text
            )
        }
        return alignKnownLyricsLrc(knownLyrics, segments, effectiveDurationMs)
    }

    fun alignKnownLyricsLrc(
        knownLyrics: String,
        segments: List<Segment>,
        songDurationMs: Long
    ): String {
        val phrases = parseKnownPhrases(knownLyrics)
        require(phrases.isNotEmpty()) { "Paste at least one lyric phrase to align." }
        val observedWords = buildTimedWords(segments)
        require(observedWords.isNotEmpty()) {
            "The local model could not hear usable words to align in this recording."
        }

        val targetWords = mutableListOf<String>()
        val timedPhrases = mutableListOf<Pair<String, IntRange>>()
        phrases.forEach { phrase ->
            val phraseTokens = tokenize(phrase).map(::normalizeToken).filter(String::isNotBlank)
            if (phraseTokens.isNotEmpty()) {
                val first = targetWords.size
                targetWords += phraseTokens
                timedPhrases += phrase to (first..targetWords.lastIndex)
            }
        }
        require(targetWords.isNotEmpty()) { "The pasted lyrics do not contain recognizable words." }

        val mapping = alignWordSequences(targetWords, observedWords.map(TimedWord::normalized))
        fillMissingMappings(mapping, observedWords.size)

        val cues = timedPhrases.map { (phrase, range) ->
            val firstObserved = mapping[range.first].coerceIn(0, observedWords.lastIndex)
            val lastObserved = mapping[range.last].coerceIn(firstObserved, observedWords.lastIndex)
            LrcLine(
                timestampMs = (observedWords[firstObserved].startMs - START_PADDING_MS).coerceAtLeast(0L),
                text = phrase,
                endTimestampMs = observedWords[lastObserved].endMs + END_PADDING_MS
            )
        }
        return LrcParser.serialize(sanitizeCues(cues, songDurationMs))
    }

    fun cleanAndMergeSegments(segments: List<Segment>, songDurationMs: Long): List<Segment> {
        val cleaned = segments
            .mapNotNull { segment ->
                val text = cleanText(segment.text)
                if (text.isBlank() || isNonLyricMarker(text)) null
                else segment.copy(
                    startMs = segment.startMs.coerceAtLeast(0L),
                    endMs = segment.endMs.coerceAtLeast(segment.startMs + MIN_CUE_DURATION_MS),
                    text = text
                )
            }
            .sortedBy(Segment::startMs)

        val result = mutableListOf<Segment>()
        cleaned.forEach { segment ->
            val safeEnd = if (songDurationMs > 0L) {
                segment.endMs.coerceAtMost(songDurationMs)
            } else {
                segment.endMs
            }
            if (safeEnd <= segment.startMs) return@forEach
            val adjusted = segment.copy(endMs = safeEnd)
            val previous = result.lastOrNull()
            if (previous != null &&
                normalizeForComparison(previous.text) == normalizeForComparison(adjusted.text) &&
                adjusted.startMs <= previous.endMs + DUPLICATE_JOIN_GAP_MS
            ) {
                result[result.lastIndex] = previous.copy(endMs = max(previous.endMs, adjusted.endMs))
            } else {
                result += adjusted
            }
        }
        return result
    }

    private fun splitSegmentIntoCues(segment: Segment): List<LrcLine> {
        val text = cleanText(segment.text)
        if (text.isBlank() || isNonLyricMarker(text)) return emptyList()
        val sentencePieces = text
            .split(SENTENCE_BOUNDARY)
            .map(String::trim)
            .filter(String::isNotBlank)
            .flatMap(::splitLongPhrase)
        if (sentencePieces.isEmpty()) return emptyList()

        val weights = sentencePieces.map { max(1, tokenize(it).size) }
        val totalWeight = weights.sum().coerceAtLeast(1)
        val duration = (segment.endMs - segment.startMs).coerceAtLeast(MIN_CUE_DURATION_MS)
        var consumedWeight = 0
        return sentencePieces.mapIndexed { index, phrase ->
            val start = segment.startMs + duration * consumedWeight / totalWeight
            consumedWeight += weights[index]
            val end = if (index == sentencePieces.lastIndex) {
                segment.endMs
            } else {
                segment.startMs + duration * consumedWeight / totalWeight
            }
            LrcLine(
                timestampMs = start.coerceAtLeast(0L),
                text = phrase,
                endTimestampMs = max(start + MIN_CUE_DURATION_MS, end)
            )
        }
    }

    private fun splitLongPhrase(phrase: String): List<String> {
        val words = phrase.split(WHITESPACE).filter(String::isNotBlank)
        if (words.size <= MAX_WORDS_PER_PHRASE) return listOf(phrase)
        return words.chunked(MAX_WORDS_PER_PHRASE).map { it.joinToString(" ") }
    }

    private fun mergeImmediateDuplicates(cues: List<LrcLine>): List<LrcLine> {
        val result = mutableListOf<LrcLine>()
        cues.sortedBy(LrcLine::timestampMs).forEach { cue ->
            val previous = result.lastOrNull()
            if (previous != null &&
                normalizeForComparison(previous.text) == normalizeForComparison(cue.text) &&
                cue.timestampMs <= (previous.endTimestampMs ?: previous.timestampMs) + DUPLICATE_JOIN_GAP_MS
            ) {
                result[result.lastIndex] = previous.copy(
                    endTimestampMs = max(
                        previous.endTimestampMs ?: previous.timestampMs,
                        cue.endTimestampMs ?: cue.timestampMs
                    )
                )
            } else {
                result += cue
            }
        }
        return result
    }

    private fun sanitizeCues(input: List<LrcLine>, songDurationMs: Long): List<LrcLine> {
        val sorted = input
            .filter { it.text.isNotBlank() }
            .sortedBy(LrcLine::timestampMs)
            .toMutableList()
        if (sorted.isEmpty()) return emptyList()

        for (index in sorted.indices) {
            val cue = sorted[index]
            val nextStart = sorted.getOrNull(index + 1)?.timestampMs
            var start = cue.timestampMs.coerceAtLeast(0L)
            if (songDurationMs > 0L) start = start.coerceAtMost((songDurationMs - 1L).coerceAtLeast(0L))
            var end = cue.endTimestampMs ?: nextStart ?: (start + DEFAULT_CUE_DURATION_MS)
            if (nextStart != null && end > nextStart) end = nextStart
            if (songDurationMs > 0L) end = end.coerceAtMost(songDurationMs)
            if (end <= start) end = (start + MIN_CUE_DURATION_MS).let { candidate ->
                if (songDurationMs > 0L) candidate.coerceAtMost(songDurationMs) else candidate
            }
            sorted[index] = cue.copy(timestampMs = start, endTimestampMs = end)
        }
        return sorted.filter { (it.endTimestampMs ?: 0L) > it.timestampMs }
    }

    private fun parseKnownPhrases(raw: String): List<String> = raw
        .lineSequence()
        .map { line -> line.replace(TIMESTAMP_PREFIX, "").trim() }
        .filter(String::isNotBlank)
        .flatMap { line ->
            line.split(SENTENCE_BOUNDARY)
                .map(String::trim)
                .filter(String::isNotBlank)
                .flatMap(::splitLongPhrase)
        }
        .take(MAX_KNOWN_PHRASES)
        .toList()

    private fun buildTimedWords(segments: List<Segment>): List<TimedWord> = segments.flatMap { segment ->
        val tokens = tokenize(segment.text)
            .map(::normalizeToken)
            .filter(String::isNotBlank)
        if (tokens.isEmpty()) return@flatMap emptyList()
        val duration = (segment.endMs - segment.startMs).coerceAtLeast(tokens.size * 80L)
        tokens.mapIndexed { index, token ->
            TimedWord(
                normalized = token,
                startMs = segment.startMs + duration * index / tokens.size,
                endMs = segment.startMs + duration * (index + 1) / tokens.size
            )
        }
    }

    /** Needleman-Wunsch sequence alignment with fuzzy Unicode token substitution costs. */
    private fun alignWordSequences(target: List<String>, observed: List<String>): IntArray {
        val rows = target.size + 1
        val columns = observed.size + 1
        val previous = FloatArray(columns) { it * INSERT_COST }
        val current = FloatArray(columns)
        val decisions = ByteArray(rows * columns)
        for (column in 1 until columns) decisions[column] = MOVE_LEFT

        for (row in 1 until rows) {
            current[0] = row * DELETE_COST
            decisions[row * columns] = MOVE_UP
            for (column in 1 until columns) {
                val diagonal = previous[column - 1] + substitutionCost(
                    target[row - 1],
                    observed[column - 1]
                )
                val up = previous[column] + DELETE_COST
                val left = current[column - 1] + INSERT_COST
                when {
                    diagonal <= up && diagonal <= left -> {
                        current[column] = diagonal
                        decisions[row * columns + column] = MOVE_DIAGONAL
                    }
                    up <= left -> {
                        current[column] = up
                        decisions[row * columns + column] = MOVE_UP
                    }
                    else -> {
                        current[column] = left
                        decisions[row * columns + column] = MOVE_LEFT
                    }
                }
            }
            current.copyInto(previous)
        }

        val mapping = IntArray(target.size) { -1 }
        var row = target.size
        var column = observed.size
        while (row > 0 || column > 0) {
            when (decisions[row * columns + column]) {
                MOVE_DIAGONAL -> {
                    mapping[row - 1] = column - 1
                    row--
                    column--
                }
                MOVE_UP -> row--
                MOVE_LEFT -> column--
                else -> {
                    if (row > 0) row-- else column--
                }
            }
        }
        return mapping
    }

    private fun fillMissingMappings(mapping: IntArray, observedSize: Int) {
        if (mapping.isEmpty()) return
        val known = mapping.indices.filter { mapping[it] >= 0 }
        if (known.isEmpty()) {
            mapping.indices.forEach { index ->
                mapping[index] = if (mapping.size == 1) 0
                else ((index.toLong() * (observedSize - 1)) / (mapping.size - 1)).toInt()
            }
            return
        }
        mapping.indices.forEach { index ->
            if (mapping[index] >= 0) return@forEach
            val left = known.lastOrNull { it < index }
            val right = known.firstOrNull { it > index }
            mapping[index] = when {
                left != null && right != null -> {
                    val span = right - left
                    mapping[left] + ((mapping[right] - mapping[left]) * (index - left)) / span
                }
                left != null -> mapping[left] + (index - left)
                right != null -> mapping[right] - (right - index)
                else -> 0
            }.coerceIn(0, observedSize - 1)
        }
        for (index in 1 until mapping.size) {
            mapping[index] = max(mapping[index], mapping[index - 1])
        }
    }

    private fun substitutionCost(left: String, right: String): Float {
        if (left == right) return 0f
        val maxLength = max(left.length, right.length).coerceAtLeast(1)
        val similarity = 1f - levenshtein(left, right).toFloat() / maxLength
        return when {
            similarity >= 0.8f -> 0.18f
            similarity >= 0.55f -> 0.45f
            else -> 1.0f
        }
    }

    private fun levenshtein(left: String, right: String): Int {
        if (left.isEmpty()) return right.length
        if (right.isEmpty()) return left.length
        var previous = IntArray(right.length + 1) { it }
        var current = IntArray(right.length + 1)
        left.forEachIndexed { leftIndex, leftChar ->
            current[0] = leftIndex + 1
            right.forEachIndexed { rightIndex, rightChar ->
                current[rightIndex + 1] = min(
                    min(current[rightIndex] + 1, previous[rightIndex + 1] + 1),
                    previous[rightIndex] + if (leftChar == rightChar) 0 else 1
                )
            }
            val swap = previous
            previous = current
            current = swap
        }
        return previous[right.length]
    }

    private fun cleanText(value: String): String = value
        .replace(SPECIAL_WHISPER_TOKEN, " ")
        .replace(Regex("\\s+"), " ")
        .trim(' ', '\t', '\n', '\r', '♪', '♫')

    private fun tokenize(value: String): List<String> = value
        .split(WHITESPACE)
        .filter(String::isNotBlank)

    private fun normalizeToken(value: String): String = Normalizer
        .normalize(value, Normalizer.Form.NFC)
        .lowercase(Locale.ROOT)
        .replace(NON_WORD_CHARACTERS, "")

    private fun normalizeForComparison(value: String): String = tokenize(value)
        .map(::normalizeToken)
        .filter(String::isNotBlank)
        .joinToString(" ")

    private fun isNonLyricMarker(value: String): Boolean {
        val marker = value
            .trim('[', ']', '(', ')', '{', '}', ' ')
            .lowercase(Locale.ROOT)
            .replace(Regex("[.!,।]"), "")
            .trim()
        return marker in NON_LYRIC_MARKERS
    }

    private const val MAX_WORDS_PER_PHRASE = 12
    private const val MAX_KNOWN_PHRASES = 2_000
    private const val MIN_CUE_DURATION_MS = 350L
    private const val DEFAULT_CUE_DURATION_MS = 2_500L
    private const val DEFAULT_TIMING_REFERENCE_CUE_DURATION_MS = 4_000L
    private const val MIN_TIMING_REFERENCE_CUE_DURATION_MS = 600L
    private const val DUPLICATE_JOIN_GAP_MS = 1_200L
    private const val START_PADDING_MS = 80L
    private const val END_PADDING_MS = 140L
    private const val INSERT_COST = 0.72f
    private const val DELETE_COST = 0.72f
    private const val MOVE_DIAGONAL: Byte = 1
    private const val MOVE_UP: Byte = 2
    private const val MOVE_LEFT: Byte = 3

    private val SENTENCE_BOUNDARY = Regex("(?<=[।!?;])\\s+|\\n+")
    private val WHITESPACE = Regex("\\s+")
    private val TIMESTAMP_PREFIX = Regex("^(?:\\[\\d{1,3}:\\d{1,2}(?:[.:]\\d{1,3})?])+\\s*")
    private val SPECIAL_WHISPER_TOKEN = Regex("<\\|[^|>]+\\|>")
    private val NON_WORD_CHARACTERS = Regex("[^\\p{L}\\p{M}\\p{N}']+")
    private val NON_LYRIC_MARKERS = setOf(
        "music", "instrumental", "applause", "silence", "background music",
        "সঙ্গীত", "বাদ্যযন্ত্র", "মিউজিক"
    )
}
