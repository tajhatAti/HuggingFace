package com.ahad.lyricsoverlay

import android.app.Application
import androidx.appcompat.app.AppCompatDelegate

class LyrApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        AppPreferences.initialize(this)
        applyThemeMode(AppPreferences.snapshot().themeMode)
        OnDeviceAiLyricsManager.restorePending(this)
    }

    companion object {
        fun applyThemeMode(mode: AppThemeMode) {
            val nightMode = when (mode) {
                AppThemeMode.SYSTEM -> AppCompatDelegate.MODE_NIGHT_FOLLOW_SYSTEM
                AppThemeMode.LIGHT -> AppCompatDelegate.MODE_NIGHT_NO
                AppThemeMode.DARK -> AppCompatDelegate.MODE_NIGHT_YES
            }
            if (AppCompatDelegate.getDefaultNightMode() != nightMode) {
                AppCompatDelegate.setDefaultNightMode(nightMode)
            }
        }
    }
}
