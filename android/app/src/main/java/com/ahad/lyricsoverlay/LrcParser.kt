package com.ahad.lyricsoverlay

import java.util.Locale

data class LrcLine(
    val timestampMs: Long,
    val text: String,
    /**
     * Optional exclusive end time. Ordinary LRC does not define cue ends, so Lyr stores one as
     * an empty timestamp immediately after the lyric, for example:
     * [00:12.00] A sung phrase
     * [00:15.40]
     */
    val endTimestampMs: Long? = null
)

object LrcParser {

    private data class TimedEvent(
        val timestampMs: Long,
        val text: String,
        val sourceOrder: Int
    )

    private val timestampRegex = Regex("""\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?]""")
    private val offsetRegex = Regex("""\[offset:([+-]?\d+)]""", RegexOption.IGNORE_CASE)
    private val metadataRegex = Regex("""^\[(ar|ti|al|by|re|ve|length):.*]$""", RegexOption.IGNORE_CASE)

    fun parse(rawLrc: String): List<LrcLine> {
        if (rawLrc.isBlank()) return emptyList()

        val offset = offsetRegex.find(rawLrc)?.groupValues?.getOrNull(1)?.toLongOrNull() ?: 0L
        val events = mutableListOf<TimedEvent>()
        var sourceOrder = 0

        rawLrc.lineSequence().forEach { originalLine ->
            val line = originalLine.trim().removePrefix("\uFEFF")
            if (line.isBlank() || metadataRegex.matches(line) || offsetRegex.matches(line)) {
                return@forEach
            }

            val timestamps = timestampRegex.findAll(line).toList()
            if (timestamps.isEmpty()) return@forEach
            val lyricText = timestampRegex.replace(line, "").trim()

            timestamps.forEach { match ->
                events += TimedEvent(
                    timestampMs = parseTimestamp(match, offset),
                    text = lyricText,
                    sourceOrder = sourceOrder++
                )
            }
        }

        if (events.none { it.text.isNotBlank() }) return emptyList()

        val parsed = mutableListOf<LrcLine>()
        events
            .distinctBy { it.timestampMs to it.text }
            .sortedWith(compareBy<TimedEvent> { it.timestampMs }.thenBy { it.sourceOrder })
            .forEach { event ->
                if (event.text.isBlank()) {
                    val previousIndex = parsed.lastIndex
                    if (previousIndex >= 0) {
                        val previous = parsed[previousIndex]
                        if (event.timestampMs > previous.timestampMs &&
                            (previous.endTimestampMs == null || event.timestampMs < previous.endTimestampMs)
                        ) {
                            parsed[previousIndex] = previous.copy(endTimestampMs = event.timestampMs)
                        }
                    }
                } else {
                    parsed += LrcLine(event.timestampMs, event.text)
                }
            }

        return parsed.distinctBy { it.timestampMs to it.text }
    }

    /** Creates the plain-lyrics payload required when a timed LRC is published. */
    fun toPlainLyrics(rawLrc: String): String = rawLrc
        .lineSequence()
        .map { it.trim().removePrefix("\uFEFF") }
        .filterNot { line ->
            line.isBlank() || metadataRegex.matches(line) || offsetRegex.matches(line)
        }
        .map { timestampRegex.replace(it, "").trim() }
        .filter { it.isNotBlank() }
        .joinToString("\n")

    /** Moves every parsed cue together. Positive values show lyrics later. */
    fun shiftTimestamps(rawLrc: String, deltaMs: Long): String {
        val lines = parse(rawLrc)
        if (lines.isEmpty()) return rawLrc
        return serialize(lines.map { line ->
            line.copy(
                timestampMs = (line.timestampMs + deltaMs).coerceAtLeast(0L),
                endTimestampMs = line.endTimestampMs
                    ?.let { (it + deltaMs).coerceAtLeast(0L) }
            )
        })
    }

    /**
     * Stretches or compresses timestamps when the matched recording has a different duration.
     * A duration ratio is safer than guessing from the final lyric line, which often ends well
     * before the audio itself.
     */
    fun fitToDuration(rawLrc: String, sourceDurationMs: Long, targetDurationMs: Long): String {
        if (sourceDurationMs <= 0L || targetDurationMs <= 0L) return rawLrc
        val lines = parse(rawLrc)
        if (lines.isEmpty()) return rawLrc
        val ratio = targetDurationMs.toDouble() / sourceDurationMs.toDouble()
        return serialize(lines.map { line ->
            line.copy(
                timestampMs = (line.timestampMs * ratio).toLong().coerceAtLeast(0L),
                endTimestampMs = line.endTimestampMs
                    ?.let { (it * ratio).toLong().coerceAtLeast(0L) }
            )
        })
    }

    /**
     * Serializes end-aware cues as standard timestamped lyric lines followed by empty timestamp
     * markers. Other LRC players can still read the text; Lyr uses the empty markers to become
     * blank during instrumental and vocal gaps.
     */
    fun serialize(lines: List<LrcLine>): String = lines
        .sortedBy(LrcLine::timestampMs)
        .joinToString("\n") { line ->
            buildString {
                append(formatTimestamp(line.timestampMs))
                append(line.text.trim())
                line.endTimestampMs
                    ?.takeIf { it > line.timestampMs }
                    ?.let { end ->
                        append('\n')
                        append(formatTimestamp(end).trimEnd())
                    }
            }
        }

    private fun parseTimestamp(match: MatchResult, offsetMs: Long): Long {
        val minutes = match.groupValues[1].toLong()
        val seconds = match.groupValues[2].toLong()
        val fractionText = match.groupValues.getOrNull(3).orEmpty()
        val fractionMs = when (fractionText.length) {
            1 -> fractionText.toLongOrNull()?.times(100L) ?: 0L
            2 -> fractionText.toLongOrNull()?.times(10L) ?: 0L
            3 -> fractionText.toLongOrNull() ?: 0L
            else -> 0L
        }
        return (minutes * 60_000L + seconds * 1_000L + fractionMs + offsetMs)
            .coerceAtLeast(0L)
    }

    private fun formatTimestamp(timestampMs: Long): String {
        val safe = timestampMs.coerceAtLeast(0L)
        val minutes = safe / 60_000L
        val seconds = (safe % 60_000L) / 1_000L
        val centiseconds = (safe % 1_000L) / 10L
        return String.format(Locale.US, "[%02d:%02d.%02d] ", minutes, seconds, centiseconds)
    }

    /** Returns the active cue, or -1 before a cue and after its explicit exclusive end. */
    fun lineIndexAt(lines: List<LrcLine>, positionMs: Long): Int {
        if (lines.isEmpty() || positionMs < lines.first().timestampMs) return -1

        var low = 0
        var high = lines.lastIndex
        var answer = -1
        while (low <= high) {
            val middle = (low + high) ushr 1
            if (lines[middle].timestampMs <= positionMs) {
                answer = middle
                low = middle + 1
            } else {
                high = middle - 1
            }
        }
        if (answer < 0) return -1
        val explicitEnd = lines[answer].endTimestampMs
        return if (explicitEnd != null && positionMs >= explicitEnd) -1 else answer
    }
}
