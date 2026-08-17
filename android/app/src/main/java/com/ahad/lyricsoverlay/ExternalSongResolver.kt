package com.ahad.lyricsoverlay

import android.content.Context
import android.media.MediaMetadataRetriever
import android.net.Uri
import android.provider.OpenableColumns
import kotlin.math.absoluteValue

/** Builds a playable queue item from an audio URI shared by another Android app. */
object ExternalSongResolver {

    fun resolve(context: Context, uri: Uri): Song {
        val displayName = queryDisplayName(context, uri)
            ?: uri.lastPathSegment?.substringAfterLast('/')
            ?: context.getString(R.string.external_audio)

        var metadataTitle: String? = null
        var metadataArtist: String? = null
        var metadataAlbum: String? = null
        var durationMs = 0L
        val retriever = MediaMetadataRetriever()
        try {
            retriever.setDataSource(context, uri)
            metadataTitle = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_TITLE)
            metadataArtist = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_ARTIST)
            metadataAlbum = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_ALBUM)
            durationMs = retriever
                .extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)
                ?.toLongOrNull()
                ?.coerceAtLeast(0L)
                ?: 0L
        } catch (_: Exception) {
            // The URI can still be playable even when its provider exposes no metadata.
        } finally {
            try {
                retriever.release()
            } catch (_: Exception) {
                // Ignore a provider closing while metadata is read.
            }
        }

        val fallbackTitle = displayName
            .substringBeforeLast('.', displayName)
            .trim()
            .ifBlank { context.getString(R.string.external_audio) }
        val sourceTitle = metadataTitle?.trim().takeUnless { it.isNullOrEmpty() } ?: fallbackTitle
        val visibleTitle = sourceTitle
        val artist = metadataArtist?.trim().takeUnless { it.isNullOrEmpty() }
            ?: context.getString(R.string.unknown_artist)
        val album = metadataAlbum?.trim().takeUnless { it.isNullOrEmpty() }
            ?: context.getString(R.string.unknown_album)
        val stableId = stableExternalId(uri)

        return Song(
            id = stableId,
            title = visibleTitle,
            sourceTitle = sourceTitle,
            artist = artist,
            album = album,
            durationMs = durationMs,
            dateAddedSeconds = System.currentTimeMillis() / 1_000L,
            contentUri = uri,
            albumId = -1L,
            albumArtUri = null,
            fileName = displayName,
            relativePath = null,
            legacyDataPath = if (uri.scheme == "file") uri.path else null
        )
    }

    private fun queryDisplayName(context: Context, uri: Uri): String? = try {
        context.contentResolver.query(
            uri,
            arrayOf(OpenableColumns.DISPLAY_NAME),
            null,
            null,
            null
        )?.use { cursor ->
            val index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            if (index >= 0 && cursor.moveToFirst()) cursor.getString(index) else null
        }
    } catch (_: Exception) {
        null
    }

    private fun stableExternalId(uri: Uri): Long {
        val hash = uri.toString().hashCode().toLong().absoluteValue.coerceAtLeast(1L)
        return -hash
    }
}
