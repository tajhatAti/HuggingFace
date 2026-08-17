package com.ahad.lyricsoverlay

import android.Manifest
import android.animation.ObjectAnimator
import android.animation.ValueAnimator
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.IBinder
import android.provider.Settings
import android.text.InputType
import android.view.View
import android.view.ViewGroup
import android.widget.ImageButton
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.SeekBar
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.recyclerview.widget.GridLayoutManager
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import androidx.recyclerview.widget.SimpleItemAnimator
import com.google.android.material.card.MaterialCardView
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import java.util.Locale
import java.util.concurrent.Executors

class MainActivity : AppCompatActivity(),
    PlayerService.PlayerListener,
    AppPreferenceListener {

    private lateinit var mainRoot: View
    private lateinit var libraryContentContainer: ViewGroup
    private lateinit var librarySummary: TextView
    private lateinit var refreshLibraryButton: ImageButton
    private lateinit var layoutModeButton: ImageButton
    private lateinit var recyclerView: RecyclerView
    private lateinit var emptyMessage: TextView
    private lateinit var permissionBanner: View
    private lateinit var permissionMessage: TextView
    private lateinit var adapter: MusicListAdapter

    private lateinit var miniPlayer: MaterialCardView
    private lateinit var miniAlbumArt: ImageView
    private lateinit var miniSongTitle: TextView
    private lateinit var miniSongArtist: TextView
    private lateinit var miniLyricsStatus: TextView
    private lateinit var playPauseButton: ImageButton
    private lateinit var seekBar: SeekBar

    private val scannerExecutor = Executors.newSingleThreadExecutor()
    private val scannedSongs = mutableListOf<Song>()
    private val visibleSongs = mutableListOf<Song>()
    private var customization = AppPreferences.snapshot()
    private var playerService: PlayerService? = null
    private var serviceBound = false
    private var pendingSongId: Long? = null
    private var userSeeking = false
    private var latestDurationMs = 0L
    private var displayedSongId: Long? = null
    private var displayedPlayingState: Boolean? = null
    private var lyricsLoadState = LyricsLoadState.IDLE
    private var automaticLyricsState = AiLyricsJobState()
    private var overlayPermissionPromptShown = false
    private var layoutAnimationGeneration = 0
    private var libraryScanGeneration = 0
    private var refreshAnimator: ObjectAnimator? = null
    private var lyricsStatusAnimator: ObjectAnimator? = null

    private val serviceConnection = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName?, binder: IBinder?) {
            playerService = (binder as? PlayerService.LocalBinder)?.getService()
            serviceBound = playerService != null
            playerService?.addListener(this@MainActivity)
            pendingSongId?.let { songId ->
                pendingSongId = null
                visibleSongs.firstOrNull { it.id == songId }?.let(::playSong)
            }
            if (Settings.canDrawOverlays(this@MainActivity)) {
                playerService?.refreshOverlayNow()
            }
        }

        override fun onServiceDisconnected(name: ComponentName?) {
            serviceBound = false
            playerService = null
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        customization = AppPreferences.snapshot()
        bindViews()
        setupRecyclerView()
        setupPlayerControls()
        setupTopControls()
        AppUi.apply(this, mainRoot, customization)
        updateLayoutButton()
        updateLibrarySummary()
        AppPreferences.registerListener(this)
        requestMissingPermissions()

        if (hasAudioPermission()) scanMusicLibrary()
    }

    override fun onStart() {
        super.onStart()
        applyLatestCustomization()
        serviceBound = bindService(
            Intent(this, PlayerService::class.java),
            serviceConnection,
            Context.BIND_AUTO_CREATE
        )
    }

    override fun onResume() {
        super.onResume()
        updateLyricsStatus()
        if (Settings.canDrawOverlays(this)) {
            playerService?.refreshOverlayNow()
        } else if (displayedSongId != null) {
            maybeShowOverlayPermissionPrompt()
        }
    }

    override fun onStop() {
        playerService?.removeListener(this)
        if (serviceBound) {
            try {
                unbindService(serviceConnection)
            } catch (_: IllegalArgumentException) {
                // Service was already disconnected.
            }
        }
        serviceBound = false
        playerService = null
        super.onStop()
    }

    override fun onDestroy() {
        AppPreferences.unregisterListener(this)
        scannerExecutor.shutdownNow()
        refreshAnimator?.cancel()
        lyricsStatusAnimator?.cancel()
        adapter.release()
        super.onDestroy()
    }

    override fun onAppPreferenceChanged(snapshot: CustomizationSnapshot, changedKey: String) {
        runOnUiThread {
            if (isFinishing || isDestroyed) return@runOnUiThread
            val previous = customization
            customization = snapshot

            AppPreferences.songIdFromTitleKey(changedKey)?.let { songId ->
                applyRenamedSong(songId)
                return@runOnUiThread
            }
            AppPreferences.songIdFromIdentifiedKey(changedKey)?.let { songId ->
                applyIdentifiedSong(songId)
                return@runOnUiThread
            }

            if (previous.themeMode != snapshot.themeMode) {
                LyrApplication.applyThemeMode(snapshot.themeMode)
                return@runOnUiThread
            }

            AppUi.apply(this, mainRoot, snapshot)
            updateLyricsStatus()
            val structureChanged = previous.layoutMode != snapshot.layoutMode ||
                previous.gridColumns != snapshot.gridColumns ||
                previous.itemStyle != snapshot.itemStyle
            val sortChanged = previous.sortOrder != snapshot.sortOrder

            if (sortChanged) {
                sortAndDisplaySongs(preserveAnchor = true)
            }
            if (structureChanged) {
                rebuildRecyclerView(snapshot, animate = true)
            } else if (previous.accentColor != snapshot.accentColor ||
                previous.appFont != snapshot.appFont
            ) {
                adapter.updateConfiguration(snapshot)
            }
            updateLayoutButton()
            updateLibrarySummary()
        }
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQUEST_PERMISSIONS) {
            if (hasAudioPermission()) {
                permissionBanner.visibility = View.GONE
                scanMusicLibrary()
            } else {
                showPermissionRequired()
            }
        }
    }

    override fun onPlayerStateChanged(
        song: Song?,
        isPlaying: Boolean,
        isBuffering: Boolean,
        positionMs: Long,
        durationMs: Long
    ) {
        if (song == null) {
            miniPlayer.visibility = View.GONE
            miniLyricsStatus.visibility = View.GONE
            displayedSongId = null
            adapter.setPlayingSong(null)
            return
        }

        miniPlayer.visibility = View.VISIBLE
        adapter.setPlayingSong(song.id)
        latestDurationMs = durationMs.coerceAtLeast(song.durationMs)

        if (displayedSongId != song.id) {
            displayedSongId = song.id
            miniAlbumArt.animate().cancel()
            miniAlbumArt.animate().alpha(0f).setDuration(90L).withEndAction {
                adapter.loadArtworkInto(miniAlbumArt, song)
                miniAlbumArt.animate().alpha(1f).setDuration(180L).start()
            }.start()
            updateLyricsStatus()
        }
        if (miniSongTitle.text.toString() != song.title) miniSongTitle.text = song.title
        if (miniSongArtist.text.toString() != song.artist) miniSongArtist.text = song.artist

        updatePlayPauseIcon(isPlaying, isBuffering)
        if (!userSeeking) {
            seekBar.progress = if (latestDurationMs > 0) {
                ((positionMs.coerceIn(0L, latestDurationMs) * SEEK_MAX) / latestDurationMs).toInt()
            } else {
                0
            }
        }
    }

    override fun onLyricsLoadStateChanged(state: LyricsLoadState) {
        lyricsLoadState = state
        updateLyricsStatus()
    }

    override fun onAutomaticLyricsProgress(state: AiLyricsJobState) {
        automaticLyricsState = state
        updateLyricsStatus()
    }

    private fun bindViews() {
        mainRoot = findViewById(R.id.mainRoot)
        libraryContentContainer = findViewById(R.id.libraryContentContainer)
        librarySummary = findViewById(R.id.librarySummary)
        refreshLibraryButton = findViewById(R.id.refreshLibraryButton)
        layoutModeButton = findViewById(R.id.layoutModeButton)
        recyclerView = findViewById(R.id.songRecyclerView)
        emptyMessage = findViewById(R.id.emptyMessage)
        permissionBanner = findViewById(R.id.permissionBanner)
        permissionMessage = findViewById(R.id.permissionMessage)

        miniPlayer = findViewById(R.id.miniPlayer)
        miniAlbumArt = findViewById(R.id.miniAlbumArt)
        miniSongTitle = findViewById(R.id.miniSongTitle)
        miniSongArtist = findViewById(R.id.miniSongArtist)
        miniLyricsStatus = findViewById(R.id.miniLyricsStatus)
        playPauseButton = findViewById(R.id.playPauseButton)
        seekBar = findViewById(R.id.playerSeekBar)
        seekBar.max = SEEK_MAX
    }

    private fun setupRecyclerView() {
        adapter = MusicListAdapter(
            context = this,
            onSongClicked = ::playSong,
            onSongLongClicked = ::showRenameSongDialog
        )
        recyclerView.adapter = adapter
        recyclerView.layoutManager = createLayoutManager(customization)
        recyclerView.setHasFixedSize(false)
        recyclerView.setItemViewCacheSize(10)
        (recyclerView.itemAnimator as? SimpleItemAnimator)?.apply {
            supportsChangeAnimations = false
            addDuration = 150L
            removeDuration = 120L
            moveDuration = 180L
            changeDuration = 120L
        }
        adapter.updateConfiguration(customization)
    }

    private fun setupTopControls() {
        refreshLibraryButton.setOnClickListener {
            if (hasAudioPermission()) {
                scanMusicLibrary(preserveAnchor = true)
            } else {
                requestMissingPermissions(forceAudioRequest = true)
            }
        }
        findViewById<View>(R.id.settingsButton).setOnClickListener {
            startActivity(Intent(this, SettingsActivity::class.java))
        }
        layoutModeButton.setOnClickListener {
            val nextMode = if (customization.layoutMode == LibraryLayoutMode.LIST) {
                LibraryLayoutMode.GRID
            } else {
                LibraryLayoutMode.LIST
            }
            AppPreferences.setLayoutMode(nextMode)
        }
        findViewById<View>(R.id.grantPermissionButton).setOnClickListener {
            requestMissingPermissions(forceAudioRequest = true)
        }
    }

    private fun setupPlayerControls() {
        miniPlayer.setOnClickListener {
            if (displayedSongId != null) openNowPlaying()
        }
        playPauseButton.setOnClickListener { playerService?.togglePlayPause() }
        findViewById<View>(R.id.previousButton).setOnClickListener { playerService?.previous() }
        findViewById<View>(R.id.nextButton).setOnClickListener { playerService?.next() }

        seekBar.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) = Unit

            override fun onStartTrackingTouch(seekBar: SeekBar?) {
                userSeeking = true
            }

            override fun onStopTrackingTouch(seekBar: SeekBar?) {
                val progress = seekBar?.progress ?: 0
                val target = if (latestDurationMs > 0) {
                    latestDurationMs * progress / SEEK_MAX
                } else {
                    0L
                }
                playerService?.seekTo(target)
                userSeeking = false
            }
        })
    }

    private fun playSong(song: Song) {
        val position = visibleSongs.indexOfFirst { it.id == song.id }
        if (position < 0) return
        val service = playerService
        if (service == null) {
            pendingSongId = song.id
            Toast.makeText(this, R.string.preparing_player, Toast.LENGTH_SHORT).show()
            return
        }

        try {
            ContextCompat.startForegroundService(
                this,
                Intent(this, PlayerService::class.java).setAction(PlayerService.ACTION_START)
            )
            service.playSongs(visibleSongs, position)
            openNowPlaying()
        } catch (_: Exception) {
            Toast.makeText(this, R.string.unable_to_start_playback, Toast.LENGTH_SHORT).show()
        }
    }

    private fun openNowPlaying() {
        startActivity(Intent(this, NowPlayingActivity::class.java))
        overridePendingTransition(R.anim.player_enter, R.anim.player_background_fade)
    }

    private fun scanMusicLibrary(preserveAnchor: Boolean = false) {
        val generation = ++libraryScanGeneration
        startRefreshAnimation()
        if (!preserveAnchor || visibleSongs.isEmpty()) {
            emptyMessage.visibility = View.VISIBLE
            emptyMessage.setText(R.string.loading_music)
        }
        scannerExecutor.execute {
            val result = runCatching { MusicScannerUtil.scan(applicationContext) }
            runOnUiThread {
                if (isFinishing || isDestroyed || generation != libraryScanGeneration) return@runOnUiThread
                stopRefreshAnimation()
                result.onSuccess { songs ->
                    scannedSongs.clear()
                    scannedSongs.addAll(songs)
                    playerService?.synchronizeSongMetadata(songs)
                    sortAndDisplaySongs(preserveAnchor = preserveAnchor)
                    emptyMessage.visibility = if (visibleSongs.isEmpty()) View.VISIBLE else View.GONE
                    if (visibleSongs.isEmpty()) emptyMessage.setText(R.string.no_songs)
                    updateLibrarySummary()
                }.onFailure {
                    emptyMessage.visibility = if (visibleSongs.isEmpty()) View.VISIBLE else View.GONE
                    if (visibleSongs.isEmpty()) emptyMessage.setText(R.string.no_songs)
                    Toast.makeText(this, R.string.library_refresh_failed, Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private fun startRefreshAnimation() {
        refreshAnimator?.cancel()
        refreshLibraryButton.isEnabled = false
        refreshAnimator = ObjectAnimator.ofFloat(refreshLibraryButton, View.ROTATION, 0f, 360f).apply {
            duration = 800L
            repeatCount = ValueAnimator.INFINITE
            start()
        }
    }

    private fun stopRefreshAnimation() {
        refreshAnimator?.cancel()
        refreshAnimator = null
        refreshLibraryButton.rotation = 0f
        refreshLibraryButton.isEnabled = true
    }

    private fun sortAndDisplaySongs(preserveAnchor: Boolean) {
        val anchor = if (preserveAnchor) captureScrollAnchor() else null
        val titleComparator = compareBy<Song> { it.title.lowercase(Locale.ROOT) }
            .thenBy { it.id }
        val sorted = when (customization.sortOrder) {
            LibrarySortOrder.TITLE -> scannedSongs.sortedWith(titleComparator)
            LibrarySortOrder.ARTIST -> scannedSongs.sortedWith(
                compareBy<Song> { it.artist.lowercase(Locale.ROOT) }
                    .thenBy { it.title.lowercase(Locale.ROOT) }
                    .thenBy { it.id }
            )
            LibrarySortOrder.DATE_ADDED -> scannedSongs.sortedWith(
                compareByDescending<Song> { it.dateAddedSeconds }
                    .then(titleComparator)
            )
            LibrarySortOrder.DURATION -> scannedSongs.sortedWith(
                compareByDescending<Song> { it.durationMs }
                    .then(titleComparator)
            )
        }
        visibleSongs.clear()
        visibleSongs.addAll(sorted)
        adapter.submitList(sorted) {
            restoreScrollAnchor(anchor)
        }
        emptyMessage.visibility = if (visibleSongs.isEmpty()) View.VISIBLE else View.GONE
        updateLibrarySummary()
    }

    private fun rebuildRecyclerView(snapshot: CustomizationSnapshot, animate: Boolean) {
        val anchor = captureScrollAnchor()
        val generation = ++layoutAnimationGeneration
        val applyChange = {
            recyclerView.layoutManager = createLayoutManager(snapshot)
            recyclerView.recycledViewPool.clear()
            adapter.updateConfiguration(snapshot)
            restoreScrollAnchor(anchor)
        }

        recyclerView.animate().cancel()
        if (!animate || recyclerView.visibility != View.VISIBLE) {
            applyChange()
            recyclerView.alpha = 1f
            return
        }
        recyclerView.animate()
            .alpha(0f)
            .setDuration(85L)
            .withEndAction {
                if (generation != layoutAnimationGeneration) return@withEndAction
                applyChange()
                recyclerView.animate().alpha(1f).setDuration(155L).start()
            }
            .start()
    }

    private fun createLayoutManager(snapshot: CustomizationSnapshot): LinearLayoutManager =
        if (snapshot.layoutMode == LibraryLayoutMode.GRID) {
            GridLayoutManager(this, snapshot.gridColumns)
        } else {
            LinearLayoutManager(this)
        }

    private fun captureScrollAnchor(): ScrollAnchor? {
        val layoutManager = recyclerView.layoutManager as? LinearLayoutManager ?: return null
        val position = layoutManager.findFirstVisibleItemPosition()
        if (position == RecyclerView.NO_POSITION) return null
        val view = layoutManager.findViewByPosition(position)
        return ScrollAnchor(
            songId = adapter.songIdAt(position),
            fallbackPosition = position,
            topOffset = (view?.top ?: recyclerView.paddingTop) - recyclerView.paddingTop
        )
    }

    private fun restoreScrollAnchor(anchor: ScrollAnchor?) {
        anchor ?: return
        recyclerView.post {
            val layoutManager = recyclerView.layoutManager as? LinearLayoutManager ?: return@post
            val byId = anchor.songId?.let { id -> visibleSongs.indexOfFirst { it.id == id } } ?: -1
            val position = if (byId >= 0) byId else anchor.fallbackPosition
                .coerceIn(0, (visibleSongs.size - 1).coerceAtLeast(0))
            if (visibleSongs.isNotEmpty()) {
                layoutManager.scrollToPositionWithOffset(position, anchor.topOffset)
            }
        }
    }

    private fun applyLatestCustomization() {
        val latest = AppPreferences.snapshot()
        if (latest != customization) onAppPreferenceChanged(latest, "resume")
        else AppUi.apply(this, mainRoot, latest)
    }

    private fun updateLayoutButton() {
        val isList = customization.layoutMode == LibraryLayoutMode.LIST
        layoutModeButton.setImageResource(if (isList) R.drawable.ic_grid_view else R.drawable.ic_list_view)
        layoutModeButton.contentDescription = getString(
            if (isList) R.string.switch_to_grid else R.string.switch_to_list
        )
        layoutModeButton.imageTintList = android.content.res.ColorStateList.valueOf(customization.accentColor)
    }

    private fun showRenameSongDialog(song: Song) {
        val titleInput = EditText(this).apply {
            setText(song.title)
            setSelection(text.length)
            hint = getString(R.string.rename_song_hint)
            inputType = InputType.TYPE_CLASS_TEXT or
                InputType.TYPE_TEXT_FLAG_CAP_SENTENCES or
                InputType.TYPE_TEXT_FLAG_AUTO_CORRECT
            maxLines = 2
            setSelectAllOnFocus(false)
        }
        val inputContainer = FrameLayout(this).apply {
            val horizontalPadding = (24 * resources.displayMetrics.density).toInt()
            val verticalPadding = (8 * resources.displayMetrics.density).toInt()
            setPadding(horizontalPadding, verticalPadding, horizontalPadding, 0)
            addView(
                titleInput,
                FrameLayout.LayoutParams(
                    FrameLayout.LayoutParams.MATCH_PARENT,
                    FrameLayout.LayoutParams.WRAP_CONTENT
                )
            )
        }
        val hasCustomTitle = AppPreferences.songTitle(song.id) != null
        val builder = MaterialAlertDialogBuilder(this)
            .setTitle(R.string.rename_song)
            .setMessage(R.string.rename_song_description)
            .setView(inputContainer)
            .setNegativeButton(android.R.string.cancel, null)
            .setPositiveButton(R.string.save, null)
        if (hasCustomTitle) {
            builder.setNeutralButton(R.string.restore_original_title) { _, _ ->
                AppPreferences.clearSongTitle(song.id)
                Toast.makeText(this, R.string.original_title_restored, Toast.LENGTH_SHORT).show()
            }
        }
        val dialog = builder.create()
        dialog.setOnShowListener {
            dialog.getButton(android.content.DialogInterface.BUTTON_POSITIVE).setOnClickListener {
                val renamedTitle = titleInput.text?.toString()?.trim().orEmpty()
                if (renamedTitle.isBlank()) {
                    titleInput.error = getString(R.string.song_title_required)
                } else {
                    AppPreferences.setSongTitle(song.id, renamedTitle)
                    Toast.makeText(this, R.string.song_renamed, Toast.LENGTH_SHORT).show()
                    dialog.dismiss()
                }
            }
            titleInput.requestFocus()
        }
        dialog.show()
    }

    private fun applyRenamedSong(songId: Long) {
        val renamedTitle = AppPreferences.songTitle(songId)
        if (renamedTitle == null) {
            scanMusicLibrary(preserveAnchor = true)
            return
        }
        val index = scannedSongs.indexOfFirst { it.id == songId }
        if (index < 0) return
        scannedSongs[index] = scannedSongs[index].copy(title = renamedTitle)
        playerService?.updateSongTitle(songId, renamedTitle)
        sortAndDisplaySongs(preserveAnchor = true)
    }

    private fun applyIdentifiedSong(songId: Long) {
        val identifiedTitle = AppPreferences.identifiedSongTitle(songId) ?: return
        val identifiedArtist = AppPreferences.identifiedSongArtist(songId) ?: return
        val index = scannedSongs.indexOfFirst { it.id == songId }
        if (index < 0) return
        val displayTitle = AppPreferences.songTitle(songId) ?: identifiedTitle
        scannedSongs[index] = scannedSongs[index].copy(
            title = displayTitle,
            artist = identifiedArtist
        )
        playerService?.updateSongIdentity(songId, displayTitle, identifiedArtist)
        sortAndDisplaySongs(preserveAnchor = true)
    }

    private fun updateLibrarySummary() {
        val sortLabel = when (customization.sortOrder) {
            LibrarySortOrder.TITLE -> getString(R.string.sort_title_short)
            LibrarySortOrder.ARTIST -> getString(R.string.sort_artist_short)
            LibrarySortOrder.DATE_ADDED -> getString(R.string.sort_date_short)
            LibrarySortOrder.DURATION -> getString(R.string.sort_duration_short)
        }
        val modeLabel = if (customization.layoutMode == LibraryLayoutMode.LIST) {
            getString(R.string.list_view)
        } else {
            getString(R.string.grid_view_columns, customization.gridColumns)
        }
        librarySummary.text = getString(
            R.string.library_summary,
            visibleSongs.size,
            sortLabel,
            modeLabel
        )
    }

    private fun updateLyricsStatus() {
        if (!::miniLyricsStatus.isInitialized || displayedSongId == null) {
            if (::miniLyricsStatus.isInitialized) {
                miniLyricsStatus.visibility = View.GONE
                stopLyricsStatusAnimation()
            }
            return
        }
        miniLyricsStatus.visibility = View.VISIBLE
        updateLyricsStatusAnimation()
        miniLyricsStatus.setTextColor(customization.accentColor)
        if (automaticLyricsState.isRunning) {
            val progress = automaticLyricsState.progress.coerceIn(0, 100)
            miniLyricsStatus.text = automaticLyricsState.message
                ?.takeIf(String::isNotBlank)
                ?.let { message -> if (progress > 0) "$message  $progress%" else message }
                ?: getString(R.string.lyrics_creating_automatically)
            miniLyricsStatus.isClickable = true
            miniLyricsStatus.setOnClickListener {
                startActivity(Intent(this, LyricsActivity::class.java))
            }
            return
        }
        if (lyricsLoadState == LyricsLoadState.SKIPPED_LONG_AUDIO) {
            miniLyricsStatus.setText(R.string.lyrics_long_audio_skipped_short)
            miniLyricsStatus.isClickable = true
            miniLyricsStatus.setOnClickListener {
                MaterialAlertDialogBuilder(this)
                    .setTitle(R.string.lyrics_long_audio_title)
                    .setMessage(R.string.lyrics_long_audio_explanation)
                    .setPositiveButton(android.R.string.ok, null)
                    .show()
            }
            return
        }
        if (!Settings.canDrawOverlays(this)) {
            miniLyricsStatus.setText(R.string.lyrics_overlay_permission_needed)
            miniLyricsStatus.isClickable = true
            miniLyricsStatus.setOnClickListener { openOverlayPermissionSettings() }
            return
        }

        when (lyricsLoadState) {
            LyricsLoadState.IDLE,
            LyricsLoadState.SEARCHING -> {
                miniLyricsStatus.setText(R.string.lyrics_searching)
                miniLyricsStatus.isClickable = false
                miniLyricsStatus.setOnClickListener(null)
            }
            LyricsLoadState.READY -> {
                miniLyricsStatus.setText(R.string.lyrics_ready)
                miniLyricsStatus.isClickable = false
                miniLyricsStatus.setOnClickListener(null)
            }
            LyricsLoadState.NOT_FOUND -> {
                miniLyricsStatus.setText(R.string.lyrics_not_found_retry)
                miniLyricsStatus.isClickable = true
                miniLyricsStatus.setOnClickListener { playerService?.retryLyrics() }
            }
            // Handled before overlay permission because the eight-minute policy must stay visible.
            LyricsLoadState.SKIPPED_LONG_AUDIO -> Unit
        }
    }

    private fun updateLyricsStatusAnimation() {
        val shouldAnimate = lyricsLoadState == LyricsLoadState.SEARCHING || automaticLyricsState.isRunning
        if (!shouldAnimate) {
            stopLyricsStatusAnimation()
            return
        }
        if (lyricsStatusAnimator?.isRunning == true) return
        lyricsStatusAnimator = ObjectAnimator.ofFloat(miniLyricsStatus, View.ALPHA, 1f, 0.5f, 1f).apply {
            duration = 1_250L
            repeatCount = ValueAnimator.INFINITE
            start()
        }
    }

    private fun stopLyricsStatusAnimation() {
        lyricsStatusAnimator?.cancel()
        lyricsStatusAnimator = null
        if (::miniLyricsStatus.isInitialized) miniLyricsStatus.alpha = 1f
    }

    private fun maybeShowOverlayPermissionPrompt() {
        if (Settings.canDrawOverlays(this) || overlayPermissionPromptShown) return
        overlayPermissionPromptShown = true
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.overlay_permission_title)
            .setMessage(R.string.overlay_playback_permission_explanation)
            .setNegativeButton(R.string.not_now, null)
            .setPositiveButton(R.string.open_overlay_permission) { _, _ ->
                openOverlayPermissionSettings()
            }
            .show()
    }

    private fun openOverlayPermissionSettings() {
        try {
            startActivity(
                Intent(
                    Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                    Uri.parse("package:$packageName")
                )
            )
        } catch (_: Exception) {
            try {
                startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION))
            } catch (_: Exception) {
                Toast.makeText(this, R.string.unable_to_open_overlay_settings, Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun requestMissingPermissions(forceAudioRequest: Boolean = false) {
        val missing = mutableListOf<String>()
        val audioPermission = requiredAudioPermission()
        if (forceAudioRequest ||
            ContextCompat.checkSelfPermission(this, audioPermission) != PackageManager.PERMISSION_GRANTED
        ) {
            missing += audioPermission
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            missing += Manifest.permission.POST_NOTIFICATIONS
        }

        if (missing.isNotEmpty()) {
            requestPermissions(missing.distinct().toTypedArray(), REQUEST_PERMISSIONS)
        }
        if (!hasAudioPermission()) showPermissionRequired()
    }

    private fun showPermissionRequired() {
        permissionBanner.visibility = View.VISIBLE
        permissionMessage.setText(R.string.permission_needed)
        emptyMessage.visibility = View.VISIBLE
        emptyMessage.setText(R.string.permission_needed)
    }

    private fun hasAudioPermission(): Boolean = ContextCompat.checkSelfPermission(
        this,
        requiredAudioPermission()
    ) == PackageManager.PERMISSION_GRANTED

    private fun requiredAudioPermission(): String =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            Manifest.permission.READ_MEDIA_AUDIO
        } else {
            Manifest.permission.READ_EXTERNAL_STORAGE
        }

    private fun updatePlayPauseIcon(isPlaying: Boolean, isBuffering: Boolean) {
        val effectivePlaying = isPlaying || isBuffering
        if (displayedPlayingState == effectivePlaying) return
        displayedPlayingState = effectivePlaying

        playPauseButton.animate().cancel()
        playPauseButton.animate()
            .alpha(0.35f)
            .scaleX(0.72f)
            .scaleY(0.72f)
            .rotationBy(70f)
            .setDuration(110L)
            .withEndAction {
                playPauseButton.setImageResource(
                    if (effectivePlaying) R.drawable.ic_pause else R.drawable.ic_play
                )
                playPauseButton.contentDescription = getString(
                    if (effectivePlaying) R.string.pause else R.string.play
                )
                playPauseButton.imageTintList = android.content.res.ColorStateList.valueOf(
                    AppUi.contrastTextColor(customization.accentColor)
                )
                playPauseButton.animate()
                    .alpha(1f)
                    .scaleX(1f)
                    .scaleY(1f)
                    .rotation(0f)
                    .setDuration(190L)
                    .start()
            }
            .start()
    }

    private data class ScrollAnchor(
        val songId: Long?,
        val fallbackPosition: Int,
        val topOffset: Int
    )

    companion object {
        private const val REQUEST_PERMISSIONS = 601
        private const val SEEK_MAX = 1_000
    }
}
