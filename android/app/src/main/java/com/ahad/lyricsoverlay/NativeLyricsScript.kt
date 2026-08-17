package com.ahad.lyricsoverlay

/** Script decisions used to keep Bengali songs in Bengali instead of translated/romanized text. */
object NativeLyricsScript {

    fun whisperLanguage(
        sourceTitle: String,
        artist: String,
        knownLyrics: String = ""
    ): String = if (
        hasMeaningfulBengali(knownLyrics) ||
        bengaliLetterCount("$sourceTitle $artist") >= MIN_METADATA_BENGALI_LETTERS
    ) {
        BENGALI_LANGUAGE_CODE
    } else {
        AUTO_LANGUAGE_CODE
    }

    fun expectsBengali(sourceTitle: String, artist: String): Boolean =
        bengaliLetterCount("$sourceTitle $artist") >= MIN_METADATA_BENGALI_LETTERS

    fun isAutomaticResultCompatible(
        sourceTitle: String,
        artist: String,
        lyrics: String
    ): Boolean = !expectsBengali(sourceTitle, artist) || hasMeaningfulBengali(lyrics)

    fun hasMeaningfulBengali(value: String): Boolean {
        val bengaliLetters = bengaliLetterCount(value)
        if (bengaliLetters < MIN_LYRICS_BENGALI_LETTERS) return false
        val allLetters = value.codePoints().toArray().count { codePoint -> Character.isLetter(codePoint) }
        return allLetters == 0 || bengaliLetters.toDouble() / allLetters >= MIN_BENGALI_LETTER_RATIO
    }

    private fun bengaliLetterCount(value: String): Int = value.codePoints().toArray().count { codePoint ->
        Character.isLetter(codePoint) && codePoint in BENGALI_BLOCK_START..BENGALI_BLOCK_END
    }

    const val AUTO_LANGUAGE_CODE = "auto"
    const val BENGALI_LANGUAGE_CODE = "bn"
    private const val BENGALI_BLOCK_START = 0x0980
    private const val BENGALI_BLOCK_END = 0x09ff
    private const val MIN_METADATA_BENGALI_LETTERS = 2
    private const val MIN_LYRICS_BENGALI_LETTERS = 4
    private const val MIN_BENGALI_LETTER_RATIO = 0.50
}
