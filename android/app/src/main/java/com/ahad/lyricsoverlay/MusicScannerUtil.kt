package com.ahad.lyricsoverlay

import android.content.ContentUris
import android.content.Context
import android.net.Uri
import android.os.Build
import android.provider.MediaStore
import java.util.Locale
import java.util.concurrent.TimeUnit

object MusicScannerUtil {

    private val supportedExtensions = setOf("mp3", "m4a", "wav", "flac")
    private val supportedMimeTypes = setOf(
        "audio/mpeg",
        "audio/mp4",
        "audio/x-m4a",
        "audio/wav",
        "audio/x-wav",
        "audio/flac"
    )

    fun scan(context: Context): List<Song> {
        val songs = mutableListOf<Song>()
        val collection = MediaStore.Audio.Media.EXTERNAL_CONTENT_URI
        val projection = mutableListOf(
            MediaStore.Audio.Media._ID,
            MediaStore.Audio.Media.TITLE,
            MediaStore.Audio.Media.ARTIST,
            MediaStore.Audio.Media.ALBUM,
            MediaStore.Audio.Media.DURATION,
            MediaStore.Audio.Media.DATE_ADDED,
            MediaStore.Audio.Media.ALBUM_ID,
            MediaStore.Audio.Media.DISPLAY_NAME,
            MediaStore.Audio.Media.MIME_TYPE
        ).apply {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                add(MediaStore.Audio.Media.RELATIVE_PATH)
            } else {
                @Suppress("DEPRECATION")
                add(MediaStore.Audio.Media.DATA)
            }
        }.toTypedArray()

        val selection = "${MediaStore.Audio.Media.DURATION} > 0"
        val sortOrder = "${MediaStore.Audio.Media.TITLE} COLLATE NOCASE ASC"

        try {
            context.contentResolver.query(
                collection,
                projection,
                selection,
                null,
                sortOrder
            )?.use { cursor ->
                val idColumn = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media._ID)
                val titleColumn = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.TITLE)
                val artistColumn = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.ARTIST)
                val albumColumn = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.ALBUM)
                val durationColumn = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.DURATION)
                val dateAddedColumn = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.DATE_ADDED)
                val albumIdColumn = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.ALBUM_ID)
                val displayNameColumn = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.DISPLAY_NAME)
                val mimeColumn = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.MIME_TYPE)
                val relativePathColumn = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    cursor.getColumnIndex(MediaStore.Audio.Media.RELATIVE_PATH)
                } else {
                    -1
                }
                @Suppress("DEPRECATION")
                val dataColumn = if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) {
                    cursor.getColumnIndex(MediaStore.Audio.Media.DATA)
                } else {
                    -1
                }

                while (cursor.moveToNext()) {
                    val id = cursor.getLong(idColumn)
                    val fileName = cursor.getString(displayNameColumn).orEmpty()
                    val mimeType = cursor.getString(mimeColumn).orEmpty().lowercase(Locale.ROOT)
                    val extension = fileName.substringAfterLast('.', "").lowercase(Locale.ROOT)

                    if (extension !in supportedExtensions && mimeType !in supportedMimeTypes) continue

                    val rawTitle = cursor.getString(titleColumn).orEmpty().trim()
                    val rawArtist = cursor.getString(artistColumn).orEmpty().trim()
                    val rawAlbum = cursor.getString(albumColumn).orEmpty().trim()
                    val albumId = cursor.getLong(albumIdColumn)
                    val duration = cursor.getLong(durationColumn).coerceAtLeast(0L)
                    val dateAdded = cursor.getLong(dateAddedColumn).coerceAtLeast(0L)
                    val contentUri = ContentUris.withAppendedId(collection, id)
                    val albumArtUri = if (albumId > 0) {
                        ContentUris.withAppendedId(ALBUM_ART_BASE_URI, albumId)
                    } else {
                        null
                    }

                    val mediaStoreTitle = rawTitle.ifBlank {
                        fileName.substringBeforeLast('.').ifBlank { "Unknown song" }
                    }
                    songs += Song(
                        id = id,
                        title = AppPreferences.songTitle(id)
                            ?: AppPreferences.identifiedSongTitle(id)
                            ?: mediaStoreTitle,
                        sourceTitle = mediaStoreTitle,
                        artist = AppPreferences.identifiedSongArtist(id)
                            ?: rawArtist.takeUnless {
                                it.isBlank() || it.equals("<unknown>", ignoreCase = true)
                            }
                            ?: context.getString(R.string.unknown_artist),
                        album = rawAlbum
                            .takeUnless { it.isBlank() || it.equals("<unknown>", ignoreCase = true) }
                            ?: context.getString(R.string.unknown_album),
                        durationMs = duration,
                        dateAddedSeconds = dateAdded,
                        contentUri = contentUri,
                        albumId = albumId,
                        albumArtUri = albumArtUri,
                        fileName = fileName,
                        relativePath = if (relativePathColumn >= 0) {
                            cursor.getString(relativePathColumn)
                        } else {
                            null
                        },
                        legacyDataPath = if (dataColumn >= 0) cursor.getString(dataColumn) else null
                    )
                }
            }
        } catch (_: SecurityException) {
            return emptyList()
        } catch (_: IllegalArgumentException) {
            return emptyList()
        }

        return songs
    }

    fun formatDuration(durationMs: Long): String {
        val totalSeconds = TimeUnit.MILLISECONDS.toSeconds(durationMs.coerceAtLeast(0L))
        val hours = totalSeconds / 3_600
        val minutes = (totalSeconds % 3_600) / 60
        val seconds = totalSeconds % 60
        return if (hours > 0) {
            String.format(Locale.getDefault(), "%d:%02d:%02d", hours, minutes, seconds)
        } else {
            String.format(Locale.getDefault(), "%d:%02d", minutes, seconds)
        }
    }

    private val ALBUM_ART_BASE_URI: Uri = Uri.parse("content://media/external/audio/albumart")
}
