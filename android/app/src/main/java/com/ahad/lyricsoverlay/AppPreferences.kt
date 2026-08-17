package com.ahad.lyricsoverlay

import android.content.Context
import android.content.SharedPreferences
import android.graphics.Color
import androidx.annotation.FontRes
import java.util.concurrent.CopyOnWriteArraySet

enum class LibraryLayoutMode { LIST, GRID }
enum class LibraryItemStyle { FLAT, ROUNDED, COMPACT }
enum class LibrarySortOrder { TITLE, ARTIST, DATE_ADDED, DURATION }
enum class AppThemeMode { SYSTEM, LIGHT, DARK }
enum class PlayerRepeatMode { OFF, ALL, ONE }

enum class AppFont(val displayName: String, @FontRes val resourceId: Int) {
    ROBOTO("Roboto", R.font.roboto),
    POPPINS("Poppins", R.font.poppins),
    NUNITO("Nunito", R.font.nunito),
    LORA("Lora", R.font.lora),
    SOURCE_SANS("Source Sans 3", R.font.source_sans_3),
    HIND_SILIGURI("Hind Siliguri · বাংলা", R.font.hind_siliguri_regular),
    HIND_SILIGURI_MEDIUM("Hind Siliguri Medium · বাংলা", R.font.hind_siliguri_medium),
    HIND_SILIGURI_BOLD("Hind Siliguri Bold · বাংলা", R.font.hind_siliguri_bold),
    ATMA("Atma · বাংলা", R.font.atma_regular),
    ATMA_MEDIUM("Atma Medium · বাংলা", R.font.atma_medium)
}

data class CustomizationSnapshot(
    val layoutMode: LibraryLayoutMode,
    val gridColumns: Int,
    val accentColor: Int,
    val themeMode: AppThemeMode,
    val itemStyle: LibraryItemStyle,
    val sortOrder: LibrarySortOrder,
    val appFont: AppFont
)

fun interface AppPreferenceListener {
    fun onAppPreferenceChanged(snapshot: CustomizationSnapshot, changedKey: String)
}

/**
 * The single source of truth for every visual/library preference in the app.
 * Activities and services never open this SharedPreferences file directly.
 */
object AppPreferences {
    const val KEY_LAYOUT_MODE = "library_layout_mode"
    const val KEY_GRID_COLUMNS = "library_grid_columns"
    const val KEY_ACCENT_COLOR = "app_accent_color"
    const val KEY_THEME_MODE = "app_theme_mode"
    const val KEY_ITEM_STYLE = "library_item_style"
    const val KEY_SORT_ORDER = "library_sort_order"
    const val KEY_APP_FONT = "app_font"
    const val KEY_PLAYER_SHUFFLE = "player_shuffle"
    const val KEY_PLAYER_REPEAT_MODE = "player_repeat_mode"
    const val KEY_SLEEP_TIMER_END_AT = "sleep_timer_end_at"
    const val KEY_SLEEP_AFTER_CURRENT_SONG = "sleep_after_current_song"

    const val KEY_OVERLAY_FONT_SIZE = "overlay_font_size"
    const val KEY_OVERLAY_FONT_STYLE = "overlay_font_style"
    const val KEY_OVERLAY_TEXT_COLOR = "overlay_text_color"
    const val KEY_OVERLAY_ANIMATION = "overlay_animation"
    const val KEY_OVERLAY_X = "overlay_x"
    const val KEY_OVERLAY_Y = "overlay_y"
    const val KEY_SONG_TITLE_PREFIX = "song_title_"
    const val KEY_IDENTIFIED_TITLE_PREFIX = "identified_song_title_"
    const val KEY_IDENTIFIED_ARTIST_PREFIX = "identified_song_artist_"

    const val OVERLAY_FONT_REGULAR = "regular"
    const val OVERLAY_FONT_BOLD = "bold"
    const val OVERLAY_FONT_SERIF = "serif"
    const val OVERLAY_FONT_MONOSPACE = "monospace"
    const val OVERLAY_FONT_HIND_SILIGURI = "hind_siliguri"
    const val OVERLAY_FONT_HIND_SILIGURI_MEDIUM = "hind_siliguri_medium"
    const val OVERLAY_FONT_HIND_SILIGURI_BOLD = "hind_siliguri_bold"
    const val OVERLAY_FONT_ATMA = "atma"
    const val OVERLAY_FONT_ATMA_MEDIUM = "atma_medium"

    const val OVERLAY_ANIMATION_FADE = "fade"
    const val OVERLAY_ANIMATION_SCALE = "scale"
    const val OVERLAY_ANIMATION_SLIDE = "slide"
    const val OVERLAY_ANIMATION_RISE = "rise"
    const val OVERLAY_ANIMATION_POP = "pop"
    const val OVERLAY_ANIMATION_FLIP = "flip"
    const val OVERLAY_ANIMATION_NONE = "none"

    const val DEFAULT_OVERLAY_FONT_SIZE = 24f
    const val MIN_OVERLAY_FONT_SIZE = 14f
    const val MAX_OVERLAY_FONT_SIZE = 42f
    val DEFAULT_ACCENT_COLOR: Int = Color.rgb(124, 77, 255)
    val DEFAULT_OVERLAY_COLOR: Int = Color.WHITE

    private const val PREFERENCES_FILE = "lyr_app_preferences"
    private const val LEGACY_OVERLAY_FILE = "lyrics_overlay_settings"

    @Volatile
    private var initialized = false
    private lateinit var preferences: SharedPreferences
    private val listeners = CopyOnWriteArraySet<AppPreferenceListener>()

    private val sharedPreferenceListener =
        SharedPreferences.OnSharedPreferenceChangeListener { _, key ->
            if (key == null) return@OnSharedPreferenceChangeListener
            val current = snapshot()
            listeners.forEach { listener -> listener.onAppPreferenceChanged(current, key) }
        }

    @Synchronized
    fun initialize(context: Context) {
        if (initialized) return
        val applicationContext = context.applicationContext
        preferences = applicationContext.getSharedPreferences(PREFERENCES_FILE, Context.MODE_PRIVATE)
        migrateLegacyOverlayPreferences(applicationContext)
        preferences.registerOnSharedPreferenceChangeListener(sharedPreferenceListener)
        initialized = true
    }

    fun registerListener(listener: AppPreferenceListener, notifyImmediately: Boolean = false) {
        checkInitialized()
        listeners += listener
        if (notifyImmediately) listener.onAppPreferenceChanged(snapshot(), "initial")
    }

    fun unregisterListener(listener: AppPreferenceListener) {
        listeners -= listener
    }

    fun snapshot(): CustomizationSnapshot {
        checkInitialized()
        return CustomizationSnapshot(
            layoutMode = enumValue(KEY_LAYOUT_MODE, LibraryLayoutMode.LIST),
            gridColumns = preferences.getInt(KEY_GRID_COLUMNS, 2).coerceIn(2, 3),
            accentColor = opaqueColor(preferences.getInt(KEY_ACCENT_COLOR, DEFAULT_ACCENT_COLOR)),
            themeMode = enumValue(KEY_THEME_MODE, AppThemeMode.SYSTEM),
            itemStyle = enumValue(KEY_ITEM_STYLE, LibraryItemStyle.ROUNDED),
            sortOrder = enumValue(KEY_SORT_ORDER, LibrarySortOrder.TITLE),
            appFont = enumValue(KEY_APP_FONT, AppFont.ROBOTO)
        )
    }

    fun setLayoutMode(value: LibraryLayoutMode) =
        preferences.edit().putString(KEY_LAYOUT_MODE, value.name).apply()

    fun setGridColumns(value: Int) =
        preferences.edit().putInt(KEY_GRID_COLUMNS, value.coerceIn(2, 3)).apply()

    fun setAccentColor(value: Int) =
        preferences.edit().putInt(KEY_ACCENT_COLOR, opaqueColor(value)).apply()

    fun setThemeMode(value: AppThemeMode) =
        preferences.edit().putString(KEY_THEME_MODE, value.name).apply()

    fun setItemStyle(value: LibraryItemStyle) =
        preferences.edit().putString(KEY_ITEM_STYLE, value.name).apply()

    fun setSortOrder(value: LibrarySortOrder) =
        preferences.edit().putString(KEY_SORT_ORDER, value.name).apply()

    fun setAppFont(value: AppFont) =
        preferences.edit().putString(KEY_APP_FONT, value.name).apply()

    fun playerShuffleEnabled(): Boolean = preferences.getBoolean(KEY_PLAYER_SHUFFLE, false)

    fun setPlayerShuffleEnabled(value: Boolean) = preferences.edit()
        .putBoolean(KEY_PLAYER_SHUFFLE, value)
        .apply()

    fun playerRepeatMode(): PlayerRepeatMode =
        enumValue(KEY_PLAYER_REPEAT_MODE, PlayerRepeatMode.OFF)

    fun setPlayerRepeatMode(value: PlayerRepeatMode) = preferences.edit()
        .putString(KEY_PLAYER_REPEAT_MODE, value.name)
        .apply()

    fun sleepTimerEndAtMs(): Long = preferences.getLong(KEY_SLEEP_TIMER_END_AT, 0L)
        .takeIf { it > System.currentTimeMillis() }
        ?: 0L

    fun sleepAfterCurrentSong(): Boolean =
        preferences.getBoolean(KEY_SLEEP_AFTER_CURRENT_SONG, false)

    fun setSleepTimer(endAtMs: Long) = preferences.edit()
        .putLong(KEY_SLEEP_TIMER_END_AT, endAtMs.coerceAtLeast(0L))
        .putBoolean(KEY_SLEEP_AFTER_CURRENT_SONG, false)
        .apply()

    fun setSleepAfterCurrentSong() = preferences.edit()
        .remove(KEY_SLEEP_TIMER_END_AT)
        .putBoolean(KEY_SLEEP_AFTER_CURRENT_SONG, true)
        .apply()

    fun clearSleepTimer() = preferences.edit()
        .remove(KEY_SLEEP_TIMER_END_AT)
        .remove(KEY_SLEEP_AFTER_CURRENT_SONG)
        .apply()

    fun songTitle(songId: Long): String? = preferences
        .getString(songTitleKey(songId), null)
        ?.trim()
        ?.takeIf(String::isNotEmpty)

    fun setSongTitle(songId: Long, title: String) {
        val cleanedTitle = title.trim().take(160)
        if (cleanedTitle.isEmpty()) return
        preferences.edit().putString(songTitleKey(songId), cleanedTitle).apply()
    }

    fun clearSongTitle(songId: Long) = preferences.edit()
        .remove(songTitleKey(songId))
        .apply()

    fun songIdFromTitleKey(key: String): Long? = key
        .takeIf { it.startsWith(KEY_SONG_TITLE_PREFIX) }
        ?.removePrefix(KEY_SONG_TITLE_PREFIX)
        ?.toLongOrNull()

    fun identifiedSongTitle(songId: Long): String? = preferences
        .getString(identifiedTitleKey(songId), null)
        ?.trim()
        ?.takeIf(String::isNotEmpty)

    fun identifiedSongArtist(songId: Long): String? = preferences
        .getString(identifiedArtistKey(songId), null)
        ?.trim()
        ?.takeIf(String::isNotEmpty)

    fun setIdentifiedSong(songId: Long, title: String, artist: String) {
        val cleanedTitle = title.trim().take(160)
        val cleanedArtist = artist.trim().take(160)
        if (cleanedTitle.isBlank() || cleanedArtist.isBlank()) return
        preferences.edit()
            .putString(identifiedTitleKey(songId), cleanedTitle)
            .putString(identifiedArtistKey(songId), cleanedArtist)
            .apply()
    }

    fun songIdFromIdentifiedKey(key: String): Long? = when {
        key.startsWith(KEY_IDENTIFIED_TITLE_PREFIX) -> key.removePrefix(KEY_IDENTIFIED_TITLE_PREFIX)
        key.startsWith(KEY_IDENTIFIED_ARTIST_PREFIX) -> key.removePrefix(KEY_IDENTIFIED_ARTIST_PREFIX)
        else -> null
    }?.toLongOrNull()

    fun overlayFontSize(): Float = preferences.getFloat(
        KEY_OVERLAY_FONT_SIZE,
        DEFAULT_OVERLAY_FONT_SIZE
    ).coerceIn(MIN_OVERLAY_FONT_SIZE, MAX_OVERLAY_FONT_SIZE)

    fun setOverlayFontSize(value: Float) = preferences.edit()
        .putFloat(KEY_OVERLAY_FONT_SIZE, value.coerceIn(MIN_OVERLAY_FONT_SIZE, MAX_OVERLAY_FONT_SIZE))
        .apply()

    fun overlayFontStyle(): String = preferences.getString(
        KEY_OVERLAY_FONT_STYLE,
        OVERLAY_FONT_BOLD
    ) ?: OVERLAY_FONT_BOLD

    fun setOverlayFontStyle(value: String) = preferences.edit()
        .putString(KEY_OVERLAY_FONT_STYLE, value)
        .apply()

    fun overlayTextColor(): Int = opaqueColor(
        preferences.getInt(KEY_OVERLAY_TEXT_COLOR, DEFAULT_OVERLAY_COLOR)
    )

    fun setOverlayTextColor(value: Int) = preferences.edit()
        .putInt(KEY_OVERLAY_TEXT_COLOR, opaqueColor(value))
        .apply()

    fun overlayAnimation(): String = preferences.getString(
        KEY_OVERLAY_ANIMATION,
        OVERLAY_ANIMATION_SCALE
    ) ?: OVERLAY_ANIMATION_SCALE

    fun setOverlayAnimation(value: String) = preferences.edit()
        .putString(KEY_OVERLAY_ANIMATION, value)
        .apply()

    fun overlayX(): Int? = if (preferences.contains(KEY_OVERLAY_X)) {
        preferences.getInt(KEY_OVERLAY_X, 0)
    } else {
        null
    }

    fun overlayY(): Int? = if (preferences.contains(KEY_OVERLAY_Y)) {
        preferences.getInt(KEY_OVERLAY_Y, 0)
    } else {
        null
    }

    fun setOverlayPosition(x: Int, y: Int) = preferences.edit()
        .putInt(KEY_OVERLAY_X, x)
        .putInt(KEY_OVERLAY_Y, y)
        .apply()

    fun resetOverlayPosition() = preferences.edit()
        .remove(KEY_OVERLAY_X)
        .remove(KEY_OVERLAY_Y)
        .apply()

    private inline fun <reified T : Enum<T>> enumValue(key: String, fallback: T): T {
        val value = preferences.getString(key, fallback.name) ?: return fallback
        return enumValues<T>().firstOrNull { it.name == value } ?: fallback
    }

    private fun songTitleKey(songId: Long): String = "$KEY_SONG_TITLE_PREFIX$songId"

    private fun identifiedTitleKey(songId: Long): String = "$KEY_IDENTIFIED_TITLE_PREFIX$songId"

    private fun identifiedArtistKey(songId: Long): String = "$KEY_IDENTIFIED_ARTIST_PREFIX$songId"

    private fun opaqueColor(color: Int): Int = Color.rgb(
        Color.red(color),
        Color.green(color),
        Color.blue(color)
    )

    private fun checkInitialized() {
        check(initialized) { "AppPreferences.initialize(context) must be called first" }
    }

    private fun migrateLegacyOverlayPreferences(context: Context) {
        val legacy = context.getSharedPreferences(LEGACY_OVERLAY_FILE, Context.MODE_PRIVATE)
        if (legacy.all.isEmpty()) return
        val editor = preferences.edit()
        if (!preferences.contains(KEY_OVERLAY_FONT_SIZE) && legacy.contains("font_size")) {
            editor.putFloat(KEY_OVERLAY_FONT_SIZE, legacy.getFloat("font_size", DEFAULT_OVERLAY_FONT_SIZE))
        }
        if (!preferences.contains(KEY_OVERLAY_FONT_STYLE) && legacy.contains("font_style")) {
            editor.putString(KEY_OVERLAY_FONT_STYLE, legacy.getString("font_style", OVERLAY_FONT_BOLD))
        }
        if (!preferences.contains(KEY_OVERLAY_TEXT_COLOR) && legacy.contains("text_color")) {
            editor.putInt(KEY_OVERLAY_TEXT_COLOR, legacy.getInt("text_color", DEFAULT_OVERLAY_COLOR))
        }
        if (!preferences.contains(KEY_OVERLAY_ANIMATION) && legacy.contains("animation_style")) {
            editor.putString(
                KEY_OVERLAY_ANIMATION,
                legacy.getString("animation_style", OVERLAY_ANIMATION_SCALE)
            )
        }
        if (!preferences.contains(KEY_OVERLAY_X) && legacy.contains("position_x")) {
            editor.putInt(KEY_OVERLAY_X, legacy.getInt("position_x", 0))
        }
        if (!preferences.contains(KEY_OVERLAY_Y) && legacy.contains("position_y")) {
            editor.putInt(KEY_OVERLAY_Y, legacy.getInt("position_y", 0))
        }
        editor.apply()
    }
}
