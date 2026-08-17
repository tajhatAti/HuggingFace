package com.ahad.lyricsoverlay

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SmartLyricsPolicyTest {

    @Test
    fun eightMinutesIsTheHardSongProcessingLimit() {
        assertTrue(SmartLyricsPolicy.isDurationEligible(0L))
        assertTrue(SmartLyricsPolicy.isDurationEligible(7L * 60L * 1_000L))
        assertTrue(SmartLyricsPolicy.isDurationEligible(SmartLyricsPolicy.MAX_AUDIO_DURATION_MS))
        assertFalse(SmartLyricsPolicy.isDurationEligible(SmartLyricsPolicy.MAX_AUDIO_DURATION_MS + 1L))
        assertFalse(SmartLyricsPolicy.isDurationEligible(12L * 60L * 1_000L))
    }
}
