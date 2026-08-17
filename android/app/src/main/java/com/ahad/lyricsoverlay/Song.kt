package com.ahad.lyricsoverlay

import android.net.Uri

data class Song(
    val id: Long,
    val title: String,
    val sourceTitle: String,
    val artist: String,
    val album: String,
    val durationMs: Long,
    val dateAddedSeconds: Long,
    val contentUri: Uri,
    val albumId: Long,
    val albumArtUri: Uri?,
    val fileName: String,
    val relativePath: String?,
    val legacyDataPath: String?
)
