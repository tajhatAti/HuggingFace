package com.ahad.lyricsoverlay

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class NativeLyricsScriptTest {

    @Test
    fun bengaliMetadataForcesNativeBengaliTranscription() {
        assertEquals(
            NativeLyricsScript.BENGALI_LANGUAGE_CODE,
            NativeLyricsScript.whisperLanguage("আমার সোনার বাংলা", "রবীন্দ্রনাথ ঠাকুর")
        )
    }

    @Test
    fun latinMetadataKeepsAutomaticLanguageDetectionForEnglishOrRomanizedTitles() {
        assertEquals(
            NativeLyricsScript.AUTO_LANGUAGE_CODE,
            NativeLyricsScript.whisperLanguage("Perfect", "Ed Sheeran")
        )
        assertEquals(
            NativeLyricsScript.AUTO_LANGUAGE_CODE,
            NativeLyricsScript.whisperLanguage("Amar Shonar Bangla", "Rabindranath Tagore")
        )
    }

    @Test
    fun bengaliKnownLyricsSelectBengaliEvenWhenMetadataIsRomanized() {
        assertEquals(
            NativeLyricsScript.BENGALI_LANGUAGE_CODE,
            NativeLyricsScript.whisperLanguage(
                "Amar Shonar Bangla",
                "Rabindranath Tagore",
                "আমার সোনার বাংলা আমি তোমায় ভালোবাসি"
            )
        )
    }

    @Test
    fun romanizedLyricsAreRejectedForBengaliMetadata() {
        assertFalse(
            NativeLyricsScript.isAutomaticResultCompatible(
                "আমার গান",
                "বাংলা শিল্পী",
                "ami tomake bhalobashi shudhu tomake chai"
            )
        )
        assertTrue(
            NativeLyricsScript.isAutomaticResultCompatible(
                "আমার গান",
                "বাংলা শিল্পী",
                "আমি তোমাকে ভালোবাসি শুধু তোমাকে চাই"
            )
        )
    }

    @Test
    fun englishLyricsRemainCompatibleWithEnglishMetadata() {
        assertTrue(
            NativeLyricsScript.isAutomaticResultCompatible(
                "Perfect",
                "Ed Sheeran",
                "I found a love for me"
            )
        )
    }
}
