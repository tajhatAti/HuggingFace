package com.ahad.lyricsoverlay

/** Pure limits shared by the UI and the durable worker before any online or AI work starts. */
object SmartLyricsPolicy {
    const val MAX_AUDIO_DURATION_MS = 8L * 60L * 1_000L

    fun isDurationEligible(durationMs: Long): Boolean =
        durationMs <= 0L || durationMs <= MAX_AUDIO_DURATION_MS
}
