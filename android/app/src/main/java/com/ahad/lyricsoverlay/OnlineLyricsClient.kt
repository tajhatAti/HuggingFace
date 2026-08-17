package com.ahad.lyricsoverlay

import android.content.ContentResolver
import android.net.Uri
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedInputStream
import java.io.BufferedOutputStream
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.util.UUID
import java.util.concurrent.atomic.AtomicBoolean

/** Minimal Gradio client for the owner's fixed Lyr Online Hugging Face Space. */
class OnlineLyricsClient(
    private val resolver: ContentResolver
) {
    data class Result(
        val rawLrc: String,
        val plainLyrics: String,
        val source: String,
        val title: String?,
        val artist: String?,
        val warnings: List<String>
    )

    private val canceled = AtomicBoolean(false)

    @Volatile
    private var activeConnection: HttpURLConnection? = null

    fun cancel() {
        canceled.set(true)
        activeConnection?.disconnect()
    }

    fun extract(
        audioUri: Uri,
        displayName: String,
        title: String,
        artist: String,
        durationMs: Long,
        forceBengali: Boolean,
        skipLookup: Boolean,
        onProgress: (Int, String) -> Unit
    ): Result {
        canceled.set(false)
        if (!skipLookup) {
            onProgress(10, "Searching synchronized lyrics by title and artist…")
            lookup(title, artist, durationMs)?.let { return it }
        }
        ensureActive()
        onProgress(18, "No trustworthy match found; uploading the song securely…")
        val uploadedPath = uploadAudio(audioUri, displayName, onProgress)
        ensureActive()
        onProgress(62, "Whisper is listening on Hugging Face ZeroGPU…")
        val eventId = createPrediction(uploadedPath, title, artist, forceBengali)
        ensureActive()
        onProgress(78, "Building synchronized lyric timing…")
        return awaitPrediction(eventId, "transcribe_song")
    }

    private fun lookup(title: String, artist: String, durationMs: Long): Result? {
        if (title.isBlank() && artist.isBlank()) return null
        val payload = JSONObject()
            .put("title", title)
            .put("artist", artist)
            .put("duration_seconds", durationMs.coerceAtLeast(0L) / 1_000.0)
        val connection = open(
            "$SPACE_ROOT/gradio_api/call/v2/lookup_lyrics",
            "POST",
            REQUEST_TIMEOUT_MS
        ).apply {
            doOutput = true
            setRequestProperty("Content-Type", "application/json; charset=utf-8")
        }
        activeConnection = connection
        val eventId = try {
            connection.outputStream.bufferedWriter(Charsets.UTF_8).use { it.write(payload.toString()) }
            JSONObject(readResponse(connection)).optString("event_id").takeIf { it.isNotBlank() }
                ?: return null
        } finally {
            connection.disconnect()
            activeConnection = null
        }
        return try {
            awaitPrediction(eventId, "lookup_lyrics")
        } catch (error: NoLyricsResultException) {
            null
        }
    }

    private fun uploadAudio(
        uri: Uri,
        displayName: String,
        onProgress: (Int, String) -> Unit
    ): String {
        val boundary = "----LyrOnline${UUID.randomUUID()}"
        val safeName = displayName
            .replace(Regex("[\\r\\n\\\"]"), "_")
            .take(180)
            .ifBlank { "song.mp3" }
        val mime = resolver.getType(uri) ?: "audio/*"
        val declaredSize = resolver.openAssetFileDescriptor(uri, "r")?.use { it.length } ?: -1L
        if (declaredSize > MAX_UPLOAD_BYTES) {
            throw IOException("This song is larger than 80 MB.")
        }
        val connection = open("$SPACE_ROOT/gradio_api/upload", "POST", UPLOAD_TIMEOUT_MS).apply {
            doOutput = true
            setChunkedStreamingMode(BUFFER_BYTES)
            setRequestProperty("Content-Type", "multipart/form-data; boundary=$boundary")
        }
        activeConnection = connection
        try {
            BufferedOutputStream(connection.outputStream, BUFFER_BYTES).use { output ->
                output.write("--$boundary\r\n".toByteArray())
                output.write(
                    "Content-Disposition: form-data; name=\"files\"; filename=\"$safeName\"\r\n".toByteArray()
                )
                output.write("Content-Type: $mime\r\n\r\n".toByteArray())
                resolver.openInputStream(uri)?.use { raw ->
                    BufferedInputStream(raw, BUFFER_BYTES).use { input ->
                        val buffer = ByteArray(BUFFER_BYTES)
                        var uploaded = 0L
                        while (true) {
                            ensureActive()
                            val count = input.read(buffer)
                            if (count < 0) break
                            uploaded += count
                            if (uploaded > MAX_UPLOAD_BYTES) {
                                throw IOException("This song is larger than 80 MB.")
                            }
                            output.write(buffer, 0, count)
                            if (declaredSize > 0L) {
                                val percent = 18 + (uploaded * 38L / declaredSize).toInt().coerceIn(0, 38)
                                onProgress(percent, "Uploading song… ${((uploaded * 100L) / declaredSize).coerceIn(0, 100)}%")
                            }
                        }
                    }
                } ?: throw IOException("The selected audio file cannot be opened.")
                output.write("\r\n--$boundary--\r\n".toByteArray())
                output.flush()
            }
            val body = readResponse(connection)
            val paths = JSONArray(body)
            return paths.optString(0).takeIf { it.isNotBlank() }
                ?: throw IOException("Lyr Online did not accept the audio upload.")
        } finally {
            connection.disconnect()
            activeConnection = null
        }
    }

    private fun createPrediction(
        uploadedPath: String,
        title: String,
        artist: String,
        forceBengali: Boolean
    ): String {
        val payload = JSONObject()
            .put(
                "audio_path",
                JSONObject()
                    .put("path", uploadedPath)
                    .put("meta", JSONObject().put("_type", "gradio.FileData"))
            )
            .put("title", title)
            .put("artist", artist)
            .put("language_label", if (forceBengali) "বাংলা" else "Auto detect")
        val connection = open(
            "$SPACE_ROOT/gradio_api/call/v2/transcribe_song",
            "POST",
            REQUEST_TIMEOUT_MS
        ).apply {
            doOutput = true
            setRequestProperty("Content-Type", "application/json; charset=utf-8")
        }
        activeConnection = connection
        try {
            connection.outputStream.bufferedWriter(Charsets.UTF_8).use { it.write(payload.toString()) }
            val response = JSONObject(readResponse(connection))
            return response.optString("event_id").takeIf { it.isNotBlank() }
                ?: throw IOException("Lyr Online did not start the lyrics job.")
        } finally {
            connection.disconnect()
            activeConnection = null
        }
    }

    private fun awaitPrediction(eventId: String, endpoint: String): Result {
        val safeEventId = eventId.takeIf { EVENT_ID.matches(it) }
            ?: throw IOException("Lyr Online returned an invalid job ID.")
        require(endpoint == "lookup_lyrics" || endpoint == "transcribe_song")
        val connection = open(
            "$SPACE_ROOT/gradio_api/call/$endpoint/$safeEventId",
            "GET",
            INFERENCE_TIMEOUT_MS
        ).apply {
            setRequestProperty("Accept", "text/event-stream")
        }
        activeConnection = connection
        try {
            if (connection.responseCode !in 200..299) {
                throw IOException("Lyr Online returned HTTP ${connection.responseCode}.")
            }
            var event = ""
            connection.inputStream.bufferedReader(Charsets.UTF_8).useLines { lines ->
                lines.forEach { line ->
                    ensureActive()
                    when {
                        line.startsWith("event:") -> event = line.substringAfter(':').trim()
                        line.startsWith("data:") && event == "complete" -> {
                            return parseCompleted(line.substringAfter(':').trim())
                        }
                        line.startsWith("data:") && event == "error" -> {
                            throw IOException("Lyr Online could not process this song.")
                        }
                    }
                }
            }
            throw IOException("Lyr Online ended without a lyrics result.")
        } finally {
            connection.disconnect()
            activeConnection = null
        }
    }

    private fun parseCompleted(data: String): Result {
        val outputs = JSONArray(data)
        val rawLrc = outputs.optString(1).trim()
        val plain = outputs.optString(2).trim()
        val structured = outputs.optJSONObject(3) ?: JSONObject()
        if (!structured.optBoolean("ok", false) || rawLrc.isBlank()) {
            val error = structured.optString("error").takeIf { it.isNotBlank() }
                ?: "No usable synchronized lyrics were produced."
            throw NoLyricsResultException(error)
        }
        val warningValues = structured.optJSONArray("warnings")
        val warnings = buildList {
            if (warningValues != null) {
                for (index in 0 until warningValues.length()) {
                    warningValues.optString(index).takeIf { it.isNotBlank() }?.let(::add)
                }
            }
        }
        return Result(
            rawLrc = rawLrc,
            plainLyrics = plain,
            source = structured.optString("source", "whisper_ai"),
            title = structured.optString("title").takeIf { it.isNotBlank() },
            artist = structured.optString("artist").takeIf { it.isNotBlank() },
            warnings = warnings
        )
    }

    private fun open(url: String, method: String, timeoutMs: Int): HttpURLConnection {
        ensureActive()
        return (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = CONNECT_TIMEOUT_MS
            readTimeout = timeoutMs
            instanceFollowRedirects = false
            useCaches = false
            setRequestProperty("Accept", "application/json")
            setRequestProperty("User-Agent", USER_AGENT)
        }
    }

    private fun readResponse(connection: HttpURLConnection): String {
        val status = connection.responseCode
        if (status in 300..399) throw IOException("Unexpected server redirect.")
        val input = if (status in 200..299) connection.inputStream else connection.errorStream
        val body = input?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
        if (status !in 200..299) {
            throw IOException("Lyr Online returned HTTP $status${body.take(180).let { if (it.isBlank()) "" else ": $it" }}")
        }
        return body
    }

    private fun ensureActive() {
        if (canceled.get() || Thread.currentThread().isInterrupted) {
            throw IOException("Online lyrics processing was canceled.")
        }
    }

    private class NoLyricsResultException(message: String) : IOException(message)

    companion object {
        const val SPACE_ROOT = "https://madarauchihagmailcom-my.hf.space"
        private const val USER_AGENT =
            "LyrMusic/3.0 (com.ahad.lyricsoverlay; https://github.com/tajhatAti/HuggingFace)"
        private const val MAX_UPLOAD_BYTES = 80L * 1_000L * 1_000L
        private const val CONNECT_TIMEOUT_MS = 15_000
        private const val UPLOAD_TIMEOUT_MS = 180_000
        private const val REQUEST_TIMEOUT_MS = 30_000
        private const val INFERENCE_TIMEOUT_MS = 240_000
        private const val BUFFER_BYTES = 64 * 1_024
        private val EVENT_ID = Regex("[A-Za-z0-9_-]{8,200}")
    }
}
