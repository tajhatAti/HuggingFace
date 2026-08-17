package com.ahad.lyricsoverlay

import android.app.ActivityManager
import android.content.Context
import android.os.Handler
import android.os.Looper
import java.io.File
import java.io.IOException
import java.util.concurrent.CopyOnWriteArraySet
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicInteger

enum class AiLyricsMode {
    AUDIO_ONLY,
    ALIGN_KNOWN_LYRICS
}

/** Legacy phase names are retained so existing player and editor UI state remains compatible. */
enum class AiJobPhase {
    IDLE,
    SEARCHING_ONLINE,
    DOWNLOADING_MODEL,
    PREPARING_AUDIO,
    PROCESSING,
    SEARCHING_RECOGNIZED,
    FINALIZING,
    COMPLETED,
    FAILED,
    CANCELED
}

enum class AiLyricsResultSource {
    ONLINE,
    LOCAL_FILE,
    ALIGNED_ON_DEVICE,
    ON_DEVICE
}

data class AiLyricsJobState(
    val songId: Long? = null,
    val phase: AiJobPhase = AiJobPhase.IDLE,
    val progress: Int = 0,
    val message: String? = null,
    val rawLrc: String? = null,
    val resultSource: AiLyricsResultSource? = null,
    val resumed: Boolean = false
) {
    val isRunning: Boolean
        get() = phase == AiJobPhase.SEARCHING_ONLINE ||
            phase == AiJobPhase.DOWNLOADING_MODEL ||
            phase == AiJobPhase.PREPARING_AUDIO ||
            phase == AiJobPhase.PROCESSING ||
            phase == AiJobPhase.SEARCHING_RECOGNIZED ||
            phase == AiJobPhase.FINALIZING
}

/** Kept as a compatibility value object for the existing Smart Lyrics screen. */
data class OnDeviceModelStatus(
    val displayName: String,
    val downloadBytes: Long,
    val downloaded: Boolean,
    val obsoleteModelDownloaded: Boolean,
    val totalRamBytes: Long,
    val supported: Boolean
) {
    val downloadMegabytes: Int
        get() = (downloadBytes / (1_000L * 1_000L)).toInt()
    val totalRamGigabytes: Float
        get() = totalRamBytes / (1024f * 1024f * 1024f)
}

/**
 * Coordinates the online-only lyrics pipeline while preserving the asynchronous contract used by
 * the player, synchronized editor, floating overlay, and foreground progress notification.
 *
 * Audio is uploaded only to the owner's fixed Hugging Face Space. The server searches LRCLIB first
 * and reserves ZeroGPU transcription only when trustworthy synchronized lyrics are unavailable.
 */
object OnDeviceAiLyricsManager {

    fun interface Listener {
        fun onAiLyricsJobChanged(state: AiLyricsJobState)
    }

    private data class JobRequest(
        val id: Int,
        val song: Song,
        val mode: AiLyricsMode,
        val knownLyrics: String,
        val forceBengali: Boolean,
        val initialOnlineAlreadyChecked: Boolean
    )

    private val listeners = CopyOnWriteArraySet<Listener>()
    private val executor = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "lyr-online-worker").apply { isDaemon = true }
    }
    private val mainHandler = Handler(Looper.getMainLooper())
    private val generation = AtomicInteger(0)

    @Volatile
    private var state = AiLyricsJobState()

    @Volatile
    private var currentRequest: JobRequest? = null

    @Volatile
    private var client: OnlineLyricsClient? = null

    fun currentState(): AiLyricsJobState = state

    fun isDurationEligible(durationMs: Long): Boolean =
        durationMs <= 0L || durationMs <= MAX_AUDIO_DURATION_MS

    fun addListener(listener: Listener) {
        listeners += listener
        mainHandler.post { listener.onAiLyricsJobChanged(state) }
    }

    fun removeListener(listener: Listener) {
        listeners -= listener
    }

    fun modelStatus(context: Context): OnDeviceModelStatus {
        val memory = (context.getSystemService(Context.ACTIVITY_SERVICE) as? ActivityManager)
            ?.let { manager -> ActivityManager.MemoryInfo().also(manager::getMemoryInfo).totalMem }
            ?: 0L
        val oldModels = File(context.filesDir, OLD_MODEL_DIRECTORY)
            .listFiles()
            ?.any { it.isFile }
            ?: false
        return OnDeviceModelStatus(
            displayName = "Lyr Online · Whisper large-v3-turbo",
            downloadBytes = 0L,
            downloaded = false,
            obsoleteModelDownloaded = oldModels,
            totalRamBytes = memory,
            supported = true
        )
    }

    fun activeSong(): Song? = currentRequest?.song

    fun activeMode(): AiLyricsMode? = currentRequest?.mode

    @Synchronized
    fun start(
        context: Context,
        song: Song,
        mode: AiLyricsMode,
        knownLyrics: String,
        forceBengaliScript: Boolean = false,
        initialOnlineAlreadyChecked: Boolean = false
    ): Boolean {
        if (state.isRunning || !isDurationEligible(song.durationMs)) return false
        if (mode == AiLyricsMode.ALIGN_KNOWN_LYRICS && knownLyrics.isBlank()) return false

        val request = JobRequest(
            id = generation.incrementAndGet(),
            song = song,
            mode = mode,
            knownLyrics = knownLyrics.trim(),
            forceBengali = forceBengaliScript,
            initialOnlineAlreadyChecked = initialOnlineAlreadyChecked
        )
        currentRequest = request
        publish(
            AiLyricsJobState(
                songId = song.id,
                phase = AiJobPhase.SEARCHING_ONLINE,
                progress = 4,
                message = "Connecting to Lyr Online…"
            )
        )
        OnDeviceAiService.ensureRunning(context.applicationContext)
        executor.execute { execute(context.applicationContext, request) }
        return true
    }

    /** A killed process has no live HTTP request to restore; the next request starts cleanly. */
    @Synchronized
    fun restorePending(context: Context) {
        @Suppress("UNUSED_VARIABLE")
        val applicationContext = context.applicationContext
        if (state.isRunning && currentRequest == null) {
            publish(AiLyricsJobState())
        }
    }

    fun cancel() {
        val request = currentRequest ?: return
        generation.incrementAndGet()
        client?.cancel()
        currentRequest = null
        publish(
            AiLyricsJobState(
                songId = request.song.id,
                phase = AiJobPhase.CANCELED,
                progress = state.progress,
                message = "Online lyrics processing stopped."
            )
        )
    }

    fun clearFinishedResult() {
        if (state.isRunning) return
        currentRequest = null
        publish(AiLyricsJobState())
    }

    /** Removes model files left by older offline builds; the current app never downloads models. */
    fun deleteDownloadedModels(context: Context): Boolean {
        if (state.isRunning) return false
        val directory = File(context.filesDir, OLD_MODEL_DIRECTORY)
        return !directory.exists() || directory.deleteRecursively()
    }

    private fun execute(context: Context, request: JobRequest) {
        try {
            publishIfCurrent(
                request,
                AiLyricsJobState(
                    songId = request.song.id,
                    phase = AiJobPhase.PREPARING_AUDIO,
                    progress = 10,
                    message = "Preparing the song for its secure upload…"
                )
            )
            val result = extractWithRetry(context, request)
            ensureCurrent(request)
            publishIfCurrent(
                request,
                AiLyricsJobState(
                    songId = request.song.id,
                    phase = AiJobPhase.FINALIZING,
                    progress = 94,
                    message = "Checking LRC timing and Bengali text…"
                )
            )

            val rawLrc = if (request.mode == AiLyricsMode.ALIGN_KNOWN_LYRICS) {
                OnDeviceLyricsProcessor.alignKnownLyricsToTimedLrc(
                    knownLyrics = request.knownLyrics,
                    timedLrc = result.rawLrc,
                    songDurationMs = request.song.durationMs
                )
            } else {
                result.rawLrc
            }
            require(LrcParser.parse(rawLrc).isNotEmpty()) {
                "The server response did not contain synchronized lyric lines."
            }
            if (!result.title.isNullOrBlank() && !result.artist.isNullOrBlank()) {
                AppPreferences.setIdentifiedSong(request.song.id, result.title, result.artist)
            }
            val source = when {
                request.mode == AiLyricsMode.ALIGN_KNOWN_LYRICS ->
                    AiLyricsResultSource.ALIGNED_ON_DEVICE
                result.source.startsWith("lrclib") -> AiLyricsResultSource.ONLINE
                else -> AiLyricsResultSource.ON_DEVICE
            }
            val sourceDescription = when {
                result.source.startsWith("lrclib") -> "Synchronized lyrics found through LRCLIB."
                else -> "Synchronized lyrics created by Whisper on Hugging Face."
            }
            val warning = result.warnings.firstOrNull()
            publishIfCurrent(
                request,
                AiLyricsJobState(
                    songId = request.song.id,
                    phase = AiJobPhase.COMPLETED,
                    progress = 100,
                    message = listOfNotNull(sourceDescription, warning).joinToString(" "),
                    rawLrc = rawLrc,
                    resultSource = source
                )
            )
        } catch (error: Throwable) {
            if (!isCurrent(request)) return
            val message = friendlyError(error)
            currentRequest = currentRequest?.takeIf { it.id == request.id }
            publish(
                AiLyricsJobState(
                    songId = request.song.id,
                    phase = AiJobPhase.FAILED,
                    progress = state.progress,
                    message = message
                )
            )
        } finally {
            client = null
        }
    }

    private fun extractWithRetry(context: Context, request: JobRequest): OnlineLyricsClient.Result {
        var lastError: Throwable? = null
        repeat(MAX_ATTEMPTS) { attempt ->
            ensureCurrent(request)
            val onlineClient = OnlineLyricsClient(context.contentResolver)
            client = onlineClient
            try {
                val title = AppPreferences.songTitle(request.song.id)
                    ?: AppPreferences.identifiedSongTitle(request.song.id)
                    ?: request.song.title
                val artist = AppPreferences.identifiedSongArtist(request.song.id)
                    ?: request.song.artist
                return onlineClient.extract(
                    audioUri = request.song.contentUri,
                    displayName = request.song.fileName.ifBlank { request.song.sourceTitle },
                    title = title,
                    artist = artist,
                    durationMs = request.song.durationMs,
                    forceBengali = request.forceBengali,
                    skipLookup = request.initialOnlineAlreadyChecked
                ) { progress, message ->
                    val phase = if (progress < 60) {
                        AiJobPhase.PROCESSING
                    } else {
                        AiJobPhase.SEARCHING_RECOGNIZED
                    }
                    publishIfCurrent(
                        request,
                        AiLyricsJobState(
                            songId = request.song.id,
                            phase = phase,
                            progress = progress,
                            message = message
                        )
                    )
                }
            } catch (error: Throwable) {
                lastError = error
                if (!isCurrent(request) || !isTransient(error) || attempt == MAX_ATTEMPTS - 1) {
                    throw error
                }
                publishIfCurrent(
                    request,
                    AiLyricsJobState(
                        songId = request.song.id,
                        phase = AiJobPhase.SEARCHING_ONLINE,
                        progress = 8,
                        message = "The Space is waking up; retrying shortly…"
                    )
                )
                Thread.sleep(RETRY_DELAYS_MS[attempt])
            } finally {
                if (client === onlineClient) client = null
            }
        }
        throw lastError ?: IOException("Lyr Online did not return a result.")
    }

    private fun publishIfCurrent(request: JobRequest, next: AiLyricsJobState) {
        if (isCurrent(request)) publish(next)
    }

    private fun publish(next: AiLyricsJobState) {
        state = next
        mainHandler.post {
            val latest = state
            listeners.forEach { listener ->
                try {
                    listener.onAiLyricsJobChanged(latest)
                } catch (_: Throwable) {
                    // A stale Activity listener must not interrupt an online job.
                }
            }
        }
    }

    private fun ensureCurrent(request: JobRequest) {
        if (!isCurrent(request) || Thread.currentThread().isInterrupted) {
            throw IOException("Online lyrics processing was canceled.")
        }
    }

    private fun isCurrent(request: JobRequest): Boolean =
        generation.get() == request.id && currentRequest?.id == request.id

    private fun isTransient(error: Throwable): Boolean {
        val text = error.message.orEmpty()
        return error is IOException && (
            text.contains("HTTP 429") ||
                text.contains("HTTP 500") ||
                text.contains("HTTP 502") ||
                text.contains("HTTP 503") ||
                text.contains("HTTP 504") ||
                text.contains("timed out", ignoreCase = true) ||
                text.contains("reset", ignoreCase = true) ||
                text.contains("unexpected end", ignoreCase = true)
            )
    }

    private fun friendlyError(error: Throwable): String {
        val raw = error.message.orEmpty().trim()
        return when {
            raw.contains("Unable to resolve host", ignoreCase = true) ->
                "No internet connection. Connect and try again."
            raw.contains("HTTP 429") ->
                "Hugging Face is busy. Wait a minute and try again."
            raw.contains("HTTP 5") || raw.contains("timed out", ignoreCase = true) ->
                "Lyr Online is temporarily unavailable. Try again shortly."
            raw.contains("canceled", ignoreCase = true) ->
                "Online lyrics processing was canceled."
            raw.isNotBlank() -> raw.take(260)
            else -> "Lyr Online could not process this song."
        }
    }

    private const val MAX_AUDIO_DURATION_MS = 8L * 60L * 1_000L
    private const val OLD_MODEL_DIRECTORY = "on-device-ai-models"
    private const val MAX_ATTEMPTS = 3
    private val RETRY_DELAYS_MS = longArrayOf(4_000L, 10_000L)
}
