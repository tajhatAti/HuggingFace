package com.ahad.lyricsoverlay

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.content.res.ColorStateList
import android.net.Uri
import android.os.Bundle
import android.os.IBinder
import android.view.MotionEvent
import android.view.View
import android.widget.ImageButton
import android.widget.ImageView
import android.widget.SeekBar
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.graphics.ColorUtils
import androidx.core.widget.NestedScrollView
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import androidx.recyclerview.widget.SimpleItemAnimator
import com.google.android.material.card.MaterialCardView
import java.util.concurrent.Executors
import kotlin.math.abs
import kotlin.math.min

class NowPlayingActivity : AppCompatActivity(),
    PlayerService.PlayerListener,
    AppPreferenceListener {

    private lateinit var playerRoot: View
    private lateinit var scrollView: NestedScrollView
    private lateinit var playerContent: View
    private lateinit var emptyState: TextView
    private lateinit var queuePositionText: TextView
    private lateinit var artworkCard: MaterialCardView
    private lateinit var albumArt: ImageView
    private lateinit var songTitle: TextView
    private lateinit var songArtist: TextView
    private lateinit var seekBar: SeekBar
    private lateinit var elapsedTime: TextView
    private lateinit var remainingTime: TextView
    private lateinit var playPauseCard: MaterialCardView
    private lateinit var playPauseButton: ImageButton
    private lateinit var shuffleButton: ImageButton
    private lateinit var repeatButton: ImageButton
    private lateinit var lyricsEntryCard: MaterialCardView
    private lateinit var lyricsEntryIcon: ImageView
    private lateinit var lyricsEntryPreview: TextView
    private lateinit var upNextCard: View
    private lateinit var upNextSubtitle: TextView
    private lateinit var queueCountText: TextView
    private lateinit var queueRecyclerView: RecyclerView

    private lateinit var artworkLoader: MusicListAdapter
    private lateinit var queueAdapter: QueueSongAdapter
    private val externalResolverExecutor = Executors.newSingleThreadExecutor()

    private var customization = AppPreferences.snapshot()
    private var playerService: PlayerService? = null
    private var serviceBound = false
    private var userSeeking = false
    private var latestDurationMs = 0L
    private var displayedSongId: Long? = null
    private var displayedPlayingState: Boolean? = null
    private var shuffleEnabled = false
    private var repeatMode = PlayerRepeatMode.OFF
    private var externalHandledUri: String? = null
    private var previewLyrics: List<LrcLine> = emptyList()
    private var previewLineIndex = -1
    private var sleepTimerActive = false

    private val serviceConnection = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName?, binder: IBinder?) {
            playerService = (binder as? PlayerService.LocalBinder)?.getService()
            serviceBound = playerService != null
            playerService?.addListener(this@NowPlayingActivity)
            handleExternalAudioIntent(intent)
        }

        override fun onServiceDisconnected(name: ComponentName?) {
            serviceBound = false
            playerService = null
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_now_playing)
        externalHandledUri = savedInstanceState?.getString(STATE_EXTERNAL_URI)
        customization = AppPreferences.snapshot()
        bindViews()
        setupQueue()
        setupControls()
        sizeArtworkForScreen()
        AppUi.apply(this, playerRoot, customization)
        applyPlayerAccent()
        AppPreferences.registerListener(this)
    }

    override fun onStart() {
        super.onStart()
        serviceBound = bindService(
            Intent(this, PlayerService::class.java),
            serviceConnection,
            Context.BIND_AUTO_CREATE
        )
    }

    override fun onNewIntent(newIntent: Intent) {
        super.onNewIntent(newIntent)
        setIntent(newIntent)
        if (newIntent.action == Intent.ACTION_VIEW) {
            externalHandledUri = null
            showOpeningAudioState()
            handleExternalAudioIntent(newIntent)
        }
    }

    override fun onSaveInstanceState(outState: Bundle) {
        outState.putString(STATE_EXTERNAL_URI, externalHandledUri)
        super.onSaveInstanceState(outState)
    }

    override fun onStop() {
        playerService?.removeListener(this)
        if (serviceBound) {
            try {
                unbindService(serviceConnection)
            } catch (_: IllegalArgumentException) {
                // The system already disconnected the service.
            }
        }
        serviceBound = false
        playerService = null
        super.onStop()
    }

    override fun onDestroy() {
        AppPreferences.unregisterListener(this)
        artworkLoader.release()
        externalResolverExecutor.shutdownNow()
        super.onDestroy()
    }

    override fun onPlayerStateChanged(
        song: Song?,
        isPlaying: Boolean,
        isBuffering: Boolean,
        positionMs: Long,
        durationMs: Long
    ) {
        if (song == null) {
            if (intent.action != Intent.ACTION_VIEW || externalHandledUri != null) {
                playerContent.visibility = View.GONE
                emptyState.visibility = View.VISIBLE
                emptyState.setText(R.string.choose_song_from_library)
            }
            displayedSongId = null
            latestDurationMs = 0L
            updateTimeLabels(0L)
            return
        }

        playerContent.visibility = View.VISIBLE
        emptyState.visibility = View.GONE
        latestDurationMs = durationMs.coerceAtLeast(song.durationMs).coerceAtLeast(0L)
        val songChanged = displayedSongId != song.id
        if (songChanged) {
            displayedSongId = song.id
            songTitle.text = song.title
            songArtist.text = song.artist
            albumArt.animate().cancel()
            albumArt.animate()
                .alpha(0.15f)
                .scaleX(0.96f)
                .scaleY(0.96f)
                .setDuration(90L)
                .withEndAction {
                    artworkLoader.loadArtworkInto(albumArt, song, placeholderPaddingDp = 72f)
                    albumArt.animate()
                        .alpha(1f)
                        .scaleX(1f)
                        .scaleY(1f)
                        .setDuration(230L)
                        .start()
                }
                .start()
        } else {
            if (songTitle.text.toString() != song.title) songTitle.text = song.title
            if (songArtist.text.toString() != song.artist) songArtist.text = song.artist
        }

        updatePlayPauseButton(isPlaying, isBuffering)
        if (!userSeeking) {
            val clampedPosition = positionMs.coerceIn(0L, latestDurationMs.coerceAtLeast(0L))
            seekBar.progress = if (latestDurationMs > 0L) {
                ((clampedPosition * SEEK_MAX) / latestDurationMs).toInt()
            } else {
                0
            }
            updateTimeLabels(clampedPosition)
        }
        playerService?.currentQueueIndex()?.let(queueAdapter::setCurrentIndex)
        updateLyricsPreview(positionMs)
    }

    override fun onLyricsLoadStateChanged(state: LyricsLoadState) {
        lyricsEntryIcon.setImageResource(
            if (state == LyricsLoadState.SEARCHING) R.drawable.ic_auto_lyrics else R.drawable.ic_lyrics
        )
        when (state) {
            LyricsLoadState.IDLE -> lyricsEntryPreview.setText(R.string.lyrics_choose_song)
            LyricsLoadState.SEARCHING -> lyricsEntryPreview.setText(R.string.lyrics_loading)
            LyricsLoadState.NOT_FOUND -> lyricsEntryPreview.setText(R.string.lyrics_not_found_open_center)
            LyricsLoadState.SKIPPED_LONG_AUDIO -> {
                lyricsEntryPreview.setText(R.string.lyrics_long_audio_skipped_short)
            }
            LyricsLoadState.READY -> if (previewLyrics.isEmpty()) {
                lyricsEntryPreview.setText(R.string.open_live_lyrics)
            }
        }
    }

    override fun onAutomaticLyricsProgress(state: AiLyricsJobState) {
        if (!state.isRunning) return
        lyricsEntryIcon.setImageResource(R.drawable.ic_auto_lyrics)
        val progress = state.progress.coerceIn(0, 100)
        lyricsEntryPreview.text = state.message
            ?.takeIf(String::isNotBlank)
            ?.let { message -> if (progress > 0) "$message  $progress%" else message }
            ?: getString(R.string.lyrics_creating_automatically)
    }

    override fun onLyricsContentChanged(result: LyricsResult?) {
        previewLyrics = result?.rawLrc?.let(LrcParser::parse).orEmpty()
        previewLineIndex = -1
        if (previewLyrics.isEmpty() && result != null) {
            lyricsEntryPreview.setText(R.string.open_live_lyrics)
        } else {
            updateLyricsPreview(0L, force = true)
        }
    }

    override fun onSleepTimerChanged(endAtMs: Long, afterCurrentSong: Boolean) {
        sleepTimerActive = afterCurrentSong || endAtMs > System.currentTimeMillis()
        updateSleepTimerIcon()
    }

    override fun onQueueChanged(queue: List<Song>, currentIndex: Int) {
        queueAdapter.updateQueue(queue, currentIndex)
        queueCountText.text = resources.getQuantityString(
            R.plurals.queue_song_count,
            queue.size,
            queue.size
        )
        queuePositionText.text = if (queue.isNotEmpty() && currentIndex in queue.indices) {
            getString(R.string.queue_position, currentIndex + 1, queue.size)
        } else {
            getString(R.string.player_waiting)
        }
        upNextSubtitle.setText(
            if (queue.size == 1 && queue.firstOrNull()?.id?.let { it < 0L } == true) {
                R.string.opened_from_another_app
            } else {
                R.string.up_next_description
            }
        )
        if (currentIndex in queue.indices) {
            queueRecyclerView.post { queueRecyclerView.smoothScrollToPosition(currentIndex) }
        }
    }

    override fun onPlaybackModeChanged(
        shuffleEnabled: Boolean,
        repeatMode: PlayerRepeatMode
    ) {
        this.shuffleEnabled = shuffleEnabled
        this.repeatMode = repeatMode
        updatePlaybackModeButtons()
    }

    override fun onAppPreferenceChanged(snapshot: CustomizationSnapshot, changedKey: String) {
        runOnUiThread {
            if (isFinishing || isDestroyed) return@runOnUiThread
            val previous = customization
            customization = snapshot
            if (previous.themeMode != snapshot.themeMode) {
                LyrApplication.applyThemeMode(snapshot.themeMode)
                return@runOnUiThread
            }
            AppUi.apply(this, playerRoot, snapshot)
            queueAdapter.updateConfiguration(snapshot)
            artworkLoader.updateConfiguration(snapshot)
            applyPlayerAccent()
        }
    }

    private fun bindViews() {
        playerRoot = findViewById(R.id.playerRoot)
        scrollView = findViewById(R.id.playerScrollView)
        playerContent = findViewById(R.id.playerContent)
        emptyState = findViewById(R.id.playerEmptyState)
        queuePositionText = findViewById(R.id.queuePositionText)
        artworkCard = findViewById(R.id.playerArtworkCard)
        albumArt = findViewById(R.id.playerAlbumArt)
        songTitle = findViewById(R.id.playerSongTitle)
        songArtist = findViewById(R.id.playerSongArtist)
        seekBar = findViewById(R.id.fullPlayerSeekBar)
        elapsedTime = findViewById(R.id.elapsedTimeText)
        remainingTime = findViewById(R.id.remainingTimeText)
        playPauseCard = findViewById(R.id.playerPlayPauseCard)
        playPauseButton = findViewById(R.id.fullPlayPauseButton)
        shuffleButton = findViewById(R.id.shuffleButton)
        repeatButton = findViewById(R.id.repeatButton)
        lyricsEntryCard = findViewById(R.id.lyricsEntryCard)
        lyricsEntryIcon = findViewById(R.id.lyricsEntryIcon)
        lyricsEntryPreview = findViewById(R.id.lyricsEntryPreview)
        upNextCard = findViewById(R.id.upNextCard)
        upNextSubtitle = findViewById(R.id.upNextSubtitle)
        queueCountText = findViewById(R.id.queueCountText)
        queueRecyclerView = findViewById(R.id.upNextRecyclerView)
        seekBar.max = SEEK_MAX
        artworkLoader = MusicListAdapter(this, {}, {})
        artworkLoader.updateConfiguration(customization)
    }

    private fun setupQueue() {
        queueAdapter = QueueSongAdapter { index -> playerService?.playQueueIndex(index) }
        queueAdapter.updateConfiguration(customization)
        queueRecyclerView.layoutManager = LinearLayoutManager(this)
        queueRecyclerView.adapter = queueAdapter
        queueRecyclerView.setHasFixedSize(true)
        (queueRecyclerView.itemAnimator as? SimpleItemAnimator)?.supportsChangeAnimations = false
    }

    private fun setupControls() {
        findViewById<View>(R.id.closePlayerButton).setOnClickListener { closePlayer() }
        findViewById<View>(R.id.showQueueButton).setOnClickListener {
            scrollView.post {
                scrollView.smoothScrollTo(0, playerContent.top + upNextCard.top)
            }
        }
        findViewById<View>(R.id.showSleepTimerButton).setOnClickListener {
            SleepTimerDialog.show(this, playerService)
        }
        lyricsEntryCard.setOnClickListener { openLyricsCenter() }
        attachLyricsSwipe(lyricsEntryCard)
        attachLyricsSwipe(albumArt)
        findViewById<View>(R.id.fullPreviousButton).setOnClickListener {
            playerService?.previous()
        }
        playPauseButton.setOnClickListener { playerService?.togglePlayPause() }
        findViewById<View>(R.id.fullNextButton).setOnClickListener {
            playerService?.next()
        }
        shuffleButton.setOnClickListener { playerService?.toggleShuffle() }
        repeatButton.setOnClickListener { playerService?.cycleRepeatMode() }

        seekBar.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                if (fromUser) {
                    val position = if (latestDurationMs > 0L) {
                        latestDurationMs * progress / SEEK_MAX
                    } else {
                        0L
                    }
                    updateTimeLabels(position)
                }
            }

            override fun onStartTrackingTouch(seekBar: SeekBar?) {
                userSeeking = true
            }

            override fun onStopTrackingTouch(seekBar: SeekBar?) {
                val target = if (latestDurationMs > 0L) {
                    latestDurationMs * (seekBar?.progress ?: 0) / SEEK_MAX
                } else {
                    0L
                }
                playerService?.seekTo(target)
                userSeeking = false
            }
        })
    }

    private fun updateLyricsPreview(positionMs: Long, force: Boolean = false) {
        if (previewLyrics.isEmpty()) return
        val index = LrcParser.lineIndexAt(previewLyrics, positionMs)
        if (!force && index == previewLineIndex) return
        previewLineIndex = index
        lyricsEntryPreview.text = if (index in previewLyrics.indices) {
            previewLyrics[index].text
        } else {
            ""
        }
        lyricsEntryPreview.animate().cancel()
        if (index !in previewLyrics.indices) {
            lyricsEntryPreview.alpha = 0f
            lyricsEntryPreview.translationY = 0f
            return
        }
        lyricsEntryPreview.alpha = 0.35f
        lyricsEntryPreview.translationY = dp(5f).toFloat()
        lyricsEntryPreview.animate()
            .alpha(1f)
            .translationY(0f)
            .setDuration(220L)
            .start()
    }

    private fun openLyricsCenter() {
        if (displayedSongId == null) {
            Toast.makeText(this, R.string.no_song_for_lyrics, Toast.LENGTH_SHORT).show()
            return
        }
        startActivity(Intent(this, LyricsActivity::class.java))
        overridePendingTransition(R.anim.lyrics_enter, R.anim.player_background_fade)
    }

    private fun attachLyricsSwipe(view: View) {
        var downX = 0f
        var downY = 0f
        view.setOnTouchListener { touchedView, event ->
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    downX = event.rawX
                    downY = event.rawY
                    touchedView.parent?.requestDisallowInterceptTouchEvent(true)
                    touchedView.isPressed = true
                    true
                }
                MotionEvent.ACTION_UP -> {
                    touchedView.parent?.requestDisallowInterceptTouchEvent(false)
                    touchedView.isPressed = false
                    val horizontalDistance = abs(event.rawX - downX)
                    val upwardDistance = downY - event.rawY
                    if (upwardDistance > dp(56f).toFloat() && upwardDistance > horizontalDistance) {
                        openLyricsCenter()
                    } else {
                        touchedView.performClick()
                    }
                    true
                }
                MotionEvent.ACTION_CANCEL -> {
                    touchedView.parent?.requestDisallowInterceptTouchEvent(false)
                    touchedView.isPressed = false
                    true
                }
                else -> true
            }
        }
    }

    private fun sizeArtworkForScreen() {
        val horizontalSpace = resources.displayMetrics.widthPixels - dp(48f)
        val size = min(horizontalSpace, dp(330f)).coerceAtLeast(dp(220f))
        artworkCard.layoutParams = artworkCard.layoutParams.apply {
            width = size
            height = size
        }
    }

    private fun updateTimeLabels(positionMs: Long) {
        val safePosition = positionMs.coerceIn(0L, latestDurationMs.coerceAtLeast(0L))
        elapsedTime.text = MusicScannerUtil.formatDuration(safePosition)
        remainingTime.text = getString(
            R.string.remaining_time,
            MusicScannerUtil.formatDuration((latestDurationMs - safePosition).coerceAtLeast(0L))
        )
    }

    private fun updatePlayPauseButton(isPlaying: Boolean, isBuffering: Boolean) {
        val effectivePlaying = isPlaying || isBuffering
        if (displayedPlayingState == effectivePlaying) return
        displayedPlayingState = effectivePlaying
        playPauseButton.animate().cancel()
        playPauseButton.animate()
            .scaleX(0.72f)
            .scaleY(0.72f)
            .alpha(0.35f)
            .setDuration(90L)
            .withEndAction {
                playPauseButton.setImageResource(
                    if (effectivePlaying) R.drawable.ic_pause else R.drawable.ic_play
                )
                playPauseButton.contentDescription = getString(
                    if (effectivePlaying) R.string.pause else R.string.play
                )
                playPauseButton.animate()
                    .scaleX(1f)
                    .scaleY(1f)
                    .alpha(if (isBuffering) 0.72f else 1f)
                    .setDuration(170L)
                    .start()
            }
            .start()
    }

    private fun updatePlaybackModeButtons() {
        if (!::shuffleButton.isInitialized) return
        val selected = customization.accentColor
        val unselected = ContextCompat.getColor(this, R.color.text_muted)
        shuffleButton.imageTintList = ColorStateList.valueOf(
            if (shuffleEnabled) selected else unselected
        )
        shuffleButton.contentDescription = getString(
            if (shuffleEnabled) R.string.shuffle_on else R.string.shuffle_off
        )
        repeatButton.setImageResource(
            if (repeatMode == PlayerRepeatMode.ONE) R.drawable.ic_repeat_one else R.drawable.ic_repeat
        )
        repeatButton.imageTintList = ColorStateList.valueOf(
            if (repeatMode == PlayerRepeatMode.OFF) unselected else selected
        )
        repeatButton.contentDescription = getString(
            when (repeatMode) {
                PlayerRepeatMode.OFF -> R.string.repeat_off
                PlayerRepeatMode.ALL -> R.string.repeat_all
                PlayerRepeatMode.ONE -> R.string.repeat_one
            }
        )
    }

    private fun updateSleepTimerIcon() {
        if (!::playerRoot.isInitialized) return
        val button = findViewById<ImageButton>(R.id.showSleepTimerButton)
        button.imageTintList = ColorStateList.valueOf(
            if (sleepTimerActive) customization.accentColor
            else ContextCompat.getColor(this, R.color.text_muted)
        )
        button.animate().cancel()
        button.animate().rotation(if (sleepTimerActive) 12f else 0f).setDuration(180L).start()
    }

    private fun applyPlayerAccent() {
        val accent = customization.accentColor
        playPauseCard.setCardBackgroundColor(accent)
        playPauseCard.rippleColor = ColorStateList.valueOf(
            ColorUtils.setAlphaComponent(AppUi.contrastTextColor(accent), 45)
        )
        playPauseButton.imageTintList = ColorStateList.valueOf(AppUi.contrastTextColor(accent))
        artworkCard.setStrokeColor(ColorUtils.setAlphaComponent(accent, 90))
        lyricsEntryCard.setStrokeColor(ColorUtils.setAlphaComponent(accent, 65))
        lyricsEntryIcon.imageTintList = ColorStateList.valueOf(accent)
        updateSleepTimerIcon()
        updatePlaybackModeButtons()
    }

    private fun handleExternalAudioIntent(audioIntent: Intent) {
        if (audioIntent.action != Intent.ACTION_VIEW) return
        val uri = audioIntent.data ?: return
        if (externalHandledUri == uri.toString() || playerService == null) return
        externalHandledUri = uri.toString()
        showOpeningAudioState()
        retainReadPermission(audioIntent, uri)

        externalResolverExecutor.execute {
            try {
                val song = ExternalSongResolver.resolve(applicationContext, uri)
                runOnUiThread {
                    if (isFinishing || isDestroyed) return@runOnUiThread
                    val service = playerService ?: return@runOnUiThread
                    try {
                        ContextCompat.startForegroundService(
                            this,
                            Intent(this, PlayerService::class.java)
                                .setAction(PlayerService.ACTION_START)
                        )
                        service.playSongs(listOf(song), 0)
                    } catch (_: Exception) {
                        showUnableToOpenAudio()
                    }
                }
            } catch (_: Exception) {
                runOnUiThread { showUnableToOpenAudio() }
            }
        }
    }

    private fun retainReadPermission(audioIntent: Intent, uri: Uri) {
        if (uri.scheme != "content") return
        val flags = audioIntent.flags and
            (Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
        if (flags and Intent.FLAG_GRANT_READ_URI_PERMISSION == 0) return
        if (audioIntent.flags and Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION == 0) return
        try {
            contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
        } catch (_: SecurityException) {
            // Temporary read access remains valid for this user-initiated playback.
        }
    }

    private fun showOpeningAudioState() {
        if (!::emptyState.isInitialized) return
        playerContent.visibility = View.GONE
        emptyState.visibility = View.VISIBLE
        emptyState.setText(R.string.opening_audio)
    }

    private fun showUnableToOpenAudio() {
        if (isFinishing || isDestroyed) return
        playerContent.visibility = View.GONE
        emptyState.visibility = View.VISIBLE
        emptyState.setText(R.string.unable_to_open_audio)
        Toast.makeText(this, R.string.unable_to_open_audio, Toast.LENGTH_LONG).show()
    }

    private fun closePlayer() {
        finish()
        overridePendingTransition(R.anim.player_background_fade, R.anim.player_exit)
    }

    override fun onBackPressed() {
        closePlayer()
    }

    private fun dp(value: Float): Int =
        (value * resources.displayMetrics.density).toInt()

    companion object {
        private const val SEEK_MAX = 1_000
        private const val STATE_EXTERNAL_URI = "external_audio_uri"
    }
}
