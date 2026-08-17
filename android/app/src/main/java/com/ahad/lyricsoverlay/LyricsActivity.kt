package com.ahad.lyricsoverlay

import android.animation.ObjectAnimator
import android.animation.ValueAnimator
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.content.res.ColorStateList
import android.net.Uri
import android.os.Bundle
import android.os.IBinder
import android.provider.Settings
import android.view.View
import android.view.inputmethod.EditorInfo
import android.widget.EditText
import android.widget.ImageButton
import android.widget.ImageView
import android.widget.SeekBar
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.graphics.ColorUtils
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.LinearSmoothScroller
import androidx.recyclerview.widget.RecyclerView
import androidx.recyclerview.widget.SimpleItemAnimator
import com.google.android.material.button.MaterialButton
import com.google.android.material.button.MaterialButtonToggleGroup
import com.google.android.material.card.MaterialCardView
import com.google.android.material.checkbox.MaterialCheckBox
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.android.material.progressindicator.LinearProgressIndicator
import com.google.android.material.tabs.TabLayout
import com.google.android.material.textfield.TextInputEditText
import com.google.android.material.textfield.TextInputLayout
import java.util.Locale
import java.util.concurrent.Executors

class LyricsActivity : AppCompatActivity(),
    PlayerService.PlayerListener,
    AppPreferenceListener {

    private lateinit var root: View
    private lateinit var songSubtitle: TextView
    private lateinit var tabs: TabLayout
    private lateinit var liveSection: View
    private lateinit var onlineSection: View
    private lateinit var aiSection: View
    private lateinit var editSection: View
    private lateinit var liveRecyclerView: RecyclerView
    private lateinit var liveEmptyState: View
    private lateinit var liveEmptyTitle: TextView
    private lateinit var sourceBadge: TextView
    private lateinit var fixTimingButton: MaterialButton
    private lateinit var overlayStatusButton: MaterialButton
    private lateinit var searchInput: TextInputEditText
    private lateinit var searchButton: MaterialButton
    private lateinit var searchStatus: TextView
    private lateinit var onlineRecyclerView: RecyclerView
    private lateinit var aiModelStatus: TextView
    private lateinit var deleteAiModelButton: MaterialButton
    private lateinit var aiModeToggle: MaterialButtonToggleGroup
    private lateinit var aiKnownLyricsLayout: TextInputLayout
    private lateinit var aiKnownLyricsInput: TextInputEditText
    private lateinit var aiBengaliCheckBox: MaterialCheckBox
    private lateinit var startAiButton: MaterialButton
    private lateinit var cancelAiButton: MaterialButton
    private lateinit var reviewAiButton: MaterialButton
    private lateinit var aiProgress: LinearProgressIndicator
    private lateinit var aiStatus: TextView
    private lateinit var aiProcessSteps: View
    private lateinit var aiStepIcons: List<ImageView>
    private lateinit var aiStepTexts: List<TextView>
    private lateinit var aiPreviewTitle: TextView
    private lateinit var aiPreviewRecyclerView: RecyclerView
    private lateinit var editor: EditText
    private lateinit var saveButton: MaterialButton
    private lateinit var publishButton: MaterialButton
    private lateinit var publishStatus: TextView
    private lateinit var elapsedTime: TextView
    private lateinit var seekBar: SeekBar
    private lateinit var playPauseCard: MaterialCardView
    private lateinit var playPauseButton: ImageButton
    private lateinit var timerButton: ImageButton

    private lateinit var lyricAdapter: LyricLineAdapter
    private lateinit var aiPreviewAdapter: LyricLineAdapter
    private lateinit var onlineAdapter: OnlineLyricsAdapter
    private lateinit var repository: LyricsRepository
    private val worker = Executors.newSingleThreadExecutor()

    private var customization = AppPreferences.snapshot()
    private var playerService: PlayerService? = null
    private var serviceBound = false
    private var currentSong: Song? = null
    private var currentLyrics: LyricsResult? = null
    private var currentLines: List<LrcLine> = emptyList()
    private var latestPositionMs = 0L
    private var latestDurationMs = 0L
    private var activeLineIndex = -1
    private var autoScrollSuppressedUntil = 0L
    private var userSeeking = false
    private var editorProgrammaticChange = false
    private var editorDirty = false
    private var importedPending = false
    private var aiDraftPending = false
    private var smartResultPending = false
    private var aiPreviewLines: List<LrcLine> = emptyList()
    private var aiPreviewActiveIndex = -1
    private var searchGeneration = 0
    private var publishGeneration = 0
    private var selectedTab = TAB_LIVE
    private var activeStepAnimator: ObjectAnimator? = null
    private var appliedSmartResultKey: String? = null

    private val aiJobListener = OnDeviceAiLyricsManager.Listener(::renderAiJobState)

    private val serviceConnection = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName?, binder: IBinder?) {
            playerService = (binder as? PlayerService.LocalBinder)?.getService()
            serviceBound = playerService != null
            playerService?.addListener(this@LyricsActivity)
            applySmartOnlineResult(OnDeviceAiLyricsManager.currentState())
        }

        override fun onServiceDisconnected(name: ComponentName?) {
            serviceBound = false
            playerService = null
        }
    }

    private val importLrcLauncher = registerForActivityResult(
        ActivityResultContracts.OpenDocument()
    ) { uri ->
        if (uri != null) importLrc(uri)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_lyrics)
        repository = LyricsRepository(applicationContext)
        customization = AppPreferences.snapshot()
        selectedTab = savedInstanceState?.getInt(STATE_TAB, TAB_LIVE) ?: TAB_LIVE
        bindViews()
        setupTabs()
        setupLists()
        setupControls()
        applyCustomization()
        AppPreferences.registerListener(this)
    }

    override fun onStart() {
        super.onStart()
        serviceBound = bindService(
            Intent(this, PlayerService::class.java),
            serviceConnection,
            Context.BIND_AUTO_CREATE
        )
        OnDeviceAiLyricsManager.addListener(aiJobListener)
    }

    override fun onResume() {
        super.onResume()
        updateOverlayButton()
        if (::aiModelStatus.isInitialized) updateAiModelStatus()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        outState.putInt(STATE_TAB, selectedTab)
        super.onSaveInstanceState(outState)
    }

    override fun onStop() {
        OnDeviceAiLyricsManager.removeListener(aiJobListener)
        playerService?.removeListener(this)
        if (serviceBound) {
            try {
                unbindService(serviceConnection)
            } catch (_: IllegalArgumentException) {
                // Already disconnected by Android.
            }
        }
        serviceBound = false
        playerService = null
        super.onStop()
    }

    override fun onDestroy() {
        searchGeneration++
        publishGeneration++
        worker.shutdownNow()
        activeStepAnimator?.cancel()
        AppPreferences.unregisterListener(this)
        super.onDestroy()
    }

    override fun onPlayerStateChanged(
        song: Song?,
        isPlaying: Boolean,
        isBuffering: Boolean,
        positionMs: Long,
        durationMs: Long
    ) {
        val songChanged = song?.id != currentSong?.id
        currentSong = song
        latestPositionMs = positionMs.coerceAtLeast(0L)
        latestDurationMs = durationMs.coerceAtLeast(song?.durationMs ?: 0L)
        songSubtitle.text = song?.let { "${it.title} · ${it.artist}" }
            ?: getString(R.string.nothing_playing)
        if (songChanged) {
            editorDirty = false
            importedPending = false
            aiDraftPending = false
            smartResultPending = false
            setEditorText("")
            onlineAdapter.submitList(emptyList())
            searchStatus.setText(R.string.search_select_download_hint)
            searchInput.setText(song?.let { "${it.sourceTitle} ${knownArtistText(it)}" }?.trim().orEmpty())
        }
        updatePlayPause(isPlaying, isBuffering)
        if (!userSeeking) {
            seekBar.progress = if (latestDurationMs > 0L) {
                ((latestPositionMs * SEEK_MAX) / latestDurationMs).toInt()
            } else {
                0
            }
            elapsedTime.text = MusicScannerUtil.formatDuration(latestPositionMs)
        }
        updateActiveLine(latestPositionMs)
        updateAiPreviewLine(latestPositionMs)
        if (songChanged) renderAiJobState(OnDeviceAiLyricsManager.currentState())
    }

    override fun onLyricsLoadStateChanged(state: LyricsLoadState) {
        when (state) {
            LyricsLoadState.IDLE -> showLyricsEmpty(R.string.lyrics_choose_song)
            LyricsLoadState.SEARCHING -> showLyricsEmpty(R.string.lyrics_loading)
            LyricsLoadState.NOT_FOUND -> showLyricsEmpty(R.string.no_timed_lyrics)
            LyricsLoadState.SKIPPED_LONG_AUDIO -> showLyricsEmpty(R.string.lyrics_long_audio_explanation)
            LyricsLoadState.READY -> if (currentLines.isEmpty()) showLyricsEmpty(R.string.no_timed_lyrics)
        }
    }

    override fun onLyricsContentChanged(result: LyricsResult?) {
        currentLyrics = result
        currentLines = result?.rawLrc?.let(LrcParser::parse).orEmpty()
        lyricAdapter.updateLines(currentLines)
        activeLineIndex = -1
        if (currentLines.isEmpty()) {
            liveRecyclerView.visibility = View.INVISIBLE
            liveEmptyState.visibility = View.VISIBLE
            sourceBadge.setText(R.string.no_timed_lyrics)
            fixTimingButton.visibility = View.GONE
        } else {
            liveRecyclerView.visibility = View.VISIBLE
            liveEmptyState.visibility = View.GONE
            sourceBadge.setText(sourceLabel(result))
            fixTimingButton.visibility = View.VISIBLE
            updateActiveLine(latestPositionMs, force = true)
        }
        if (!editorDirty && result != null) setEditorText(result.rawLrc)
    }

    override fun onSleepTimerChanged(endAtMs: Long, afterCurrentSong: Boolean) {
        val active = afterCurrentSong || endAtMs > System.currentTimeMillis()
        timerButton.imageTintList = ColorStateList.valueOf(
            if (active) customization.accentColor
            else ContextCompat.getColor(this, R.color.text_secondary)
        )
        timerButton.animate().cancel()
        timerButton.animate().rotation(if (active) 12f else 0f).setDuration(180L).start()
    }

    override fun onAppPreferenceChanged(snapshot: CustomizationSnapshot, changedKey: String) {
        runOnUiThread {
            if (isFinishing || isDestroyed) return@runOnUiThread
            val oldTheme = customization.themeMode
            customization = snapshot
            if (oldTheme != snapshot.themeMode) {
                LyrApplication.applyThemeMode(snapshot.themeMode)
                return@runOnUiThread
            }
            applyCustomization()
        }
    }

    private fun bindViews() {
        root = findViewById(R.id.lyricsRoot)
        songSubtitle = findViewById(R.id.lyricsSongSubtitle)
        tabs = findViewById(R.id.lyricsTabs)
        liveSection = findViewById(R.id.liveLyricsSection)
        onlineSection = findViewById(R.id.onlineLyricsSection)
        aiSection = findViewById(R.id.aiLyricsSection)
        editSection = findViewById(R.id.editLyricsSection)
        liveRecyclerView = findViewById(R.id.liveLyricsRecyclerView)
        liveEmptyState = findViewById(R.id.liveLyricsEmptyState)
        liveEmptyTitle = findViewById(R.id.liveLyricsEmptyTitle)
        sourceBadge = findViewById(R.id.lyricsSourceBadge)
        fixTimingButton = findViewById(R.id.fixLyricsTimingButton)
        overlayStatusButton = findViewById(R.id.overlayStatusButton)
        searchInput = findViewById(R.id.lyricsSearchInput)
        searchButton = findViewById(R.id.searchLyricsButton)
        searchStatus = findViewById(R.id.onlineLyricsStatus)
        onlineRecyclerView = findViewById(R.id.onlineLyricsRecyclerView)
        aiModelStatus = findViewById(R.id.aiModelStatus)
        deleteAiModelButton = findViewById(R.id.deleteAiModelButton)
        aiModeToggle = findViewById(R.id.aiModeToggle)
        aiKnownLyricsLayout = findViewById(R.id.aiKnownLyricsInputLayout)
        aiKnownLyricsInput = findViewById(R.id.aiKnownLyricsInput)
        aiBengaliCheckBox = findViewById(R.id.aiBengaliCheckBox)
        startAiButton = findViewById(R.id.startAiLyricsButton)
        cancelAiButton = findViewById(R.id.cancelAiLyricsButton)
        reviewAiButton = findViewById(R.id.reviewAiLyricsButton)
        aiProgress = findViewById(R.id.aiLyricsProgress)
        aiStatus = findViewById(R.id.aiLyricsStatus)
        aiProcessSteps = findViewById(R.id.aiProcessSteps)
        aiStepIcons = listOf(
            findViewById(R.id.aiStepOnlineIcon),
            findViewById(R.id.aiStepPrepareIcon),
            findViewById(R.id.aiStepListenIcon),
            findViewById(R.id.aiStepRetryIcon),
            findViewById(R.id.aiStepFinishIcon)
        )
        aiStepTexts = listOf(
            findViewById(R.id.aiStepOnlineText),
            findViewById(R.id.aiStepPrepareText),
            findViewById(R.id.aiStepListenText),
            findViewById(R.id.aiStepRetryText),
            findViewById(R.id.aiStepFinishText)
        )
        aiPreviewTitle = findViewById(R.id.aiPreviewTitle)
        aiPreviewRecyclerView = findViewById(R.id.aiLyricsPreviewRecyclerView)
        editor = findViewById(R.id.lrcEditor)
        saveButton = findViewById(R.id.saveLyricsButton)
        publishButton = findViewById(R.id.publishLyricsButton)
        publishStatus = findViewById(R.id.publishLyricsStatus)
        elapsedTime = findViewById(R.id.lyricsElapsedTime)
        seekBar = findViewById(R.id.lyricsSeekBar)
        playPauseCard = findViewById(R.id.lyricsPlayPauseCard)
        playPauseButton = findViewById(R.id.lyricsPlayPauseButton)
        timerButton = findViewById(R.id.lyricsTimerButton)
        seekBar.max = SEEK_MAX
        updateAiModelStatus()
    }

    private fun setupTabs() {
        tabs.addTab(tabs.newTab().setText(R.string.lyrics_tab_live).setIcon(R.drawable.ic_lyrics))
        tabs.addTab(tabs.newTab().setText(R.string.lyrics_tab_online).setIcon(R.drawable.ic_search))
        tabs.addTab(tabs.newTab().setText(R.string.lyrics_tab_ai).setIcon(R.drawable.ic_auto_lyrics))
        tabs.addTab(tabs.newTab().setText(R.string.lyrics_tab_edit).setIcon(R.drawable.ic_edit))
        tabs.addOnTabSelectedListener(object : TabLayout.OnTabSelectedListener {
            override fun onTabSelected(tab: TabLayout.Tab) = showTab(tab.position, animate = true)
            override fun onTabUnselected(tab: TabLayout.Tab) = Unit
            override fun onTabReselected(tab: TabLayout.Tab) {
                if (tab.position == TAB_LIVE && activeLineIndex >= 0) centerActiveLine(smooth = true)
            }
        })
        tabs.getTabAt(selectedTab)?.select()
        showTab(selectedTab, animate = false)
    }

    private fun setupLists() {
        lyricAdapter = LyricLineAdapter { line ->
            autoScrollSuppressedUntil = 0L
            playerService?.seekTo(line.timestampMs)
            updateActiveLine(line.timestampMs, force = true)
        }
        lyricAdapter.updateConfiguration(customization)
        liveRecyclerView.layoutManager = LinearLayoutManager(this)
        liveRecyclerView.adapter = lyricAdapter
        (liveRecyclerView.itemAnimator as? SimpleItemAnimator)?.supportsChangeAnimations = false
        liveRecyclerView.addOnScrollListener(object : RecyclerView.OnScrollListener() {
            override fun onScrollStateChanged(recyclerView: RecyclerView, newState: Int) {
                if (newState == RecyclerView.SCROLL_STATE_DRAGGING) {
                    autoScrollSuppressedUntil = android.os.SystemClock.elapsedRealtime() + USER_SCROLL_PAUSE_MS
                }
            }
        })

        onlineAdapter = OnlineLyricsAdapter(::confirmOnlineSelection)
        onlineAdapter.updateConfiguration(customization)
        onlineRecyclerView.layoutManager = LinearLayoutManager(this)
        onlineRecyclerView.adapter = onlineAdapter
        (onlineRecyclerView.itemAnimator as? SimpleItemAnimator)?.supportsChangeAnimations = false

        aiPreviewAdapter = LyricLineAdapter { line ->
            playerService?.seekTo(line.timestampMs)
            updateAiPreviewLine(line.timestampMs, force = true)
        }
        aiPreviewAdapter.updateConfiguration(customization)
        aiPreviewRecyclerView.layoutManager = LinearLayoutManager(this)
        aiPreviewRecyclerView.adapter = aiPreviewAdapter
        (aiPreviewRecyclerView.itemAnimator as? SimpleItemAnimator)?.supportsChangeAnimations = false
    }

    private fun setupControls() {
        findViewById<View>(R.id.lyricsBackButton).setOnClickListener { closeLyrics() }
        timerButton.setOnClickListener { SleepTimerDialog.show(this, playerService) }
        fixTimingButton.setOnClickListener { showTimingCorrectionDialog() }
        findViewById<View>(R.id.retryAutomaticLyricsButton).setOnClickListener {
            playerService?.retryLyrics()
        }
        findViewById<View>(R.id.findOnlineLyricsButton).setOnClickListener { tabs.getTabAt(TAB_ONLINE)?.select() }
        findViewById<View>(R.id.createAiLyricsButton).setOnClickListener { tabs.getTabAt(TAB_AI)?.select() }
        findViewById<View>(R.id.openLyricsEditorButton).setOnClickListener { tabs.getTabAt(TAB_EDIT)?.select() }
        aiModeToggle.addOnButtonCheckedListener { _, checkedId, isChecked ->
            if (isChecked) {
                aiKnownLyricsLayout.visibility = if (checkedId == R.id.aiKnownLyricsModeButton) {
                    View.VISIBLE
                } else {
                    View.GONE
                }
            }
        }
        startAiButton.setOnClickListener { confirmOnDeviceAi() }
        cancelAiButton.setOnClickListener { OnDeviceAiLyricsManager.cancel() }
        deleteAiModelButton.setOnClickListener {
            if (OnDeviceAiLyricsManager.deleteDownloadedModels(applicationContext)) {
                Toast.makeText(this, R.string.ai_model_deleted, Toast.LENGTH_LONG).show()
                updateAiModelStatus()
                OnDeviceAiLyricsManager.clearFinishedResult()
            }
        }
        reviewAiButton.setOnClickListener { loadAiDraftIntoEditor() }
        searchButton.setOnClickListener { searchOnline() }
        searchInput.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_SEARCH) {
                searchOnline()
                true
            } else {
                false
            }
        }
        editor.setOnFocusChangeListener { _, hasFocus ->
            if (hasFocus && !editorProgrammaticChange) editorDirty = true
        }
        findViewById<View>(R.id.importLrcButton).setOnClickListener {
            importLrcLauncher.launch(arrayOf("text/*", "application/octet-stream"))
        }
        findViewById<View>(R.id.insertTimestampButton).setOnClickListener { insertCurrentTimestamp() }
        saveButton.setOnClickListener { saveEditedLyrics() }
        findViewById<View>(R.id.restoreAutomaticLyricsButton).setOnClickListener {
            restoreAutomaticLyrics()
        }
        publishButton.setOnClickListener { confirmPublish() }
        overlayStatusButton.setOnClickListener { openOrRefreshOverlay() }
        findViewById<View>(R.id.lyricsPreviousButton).setOnClickListener { playerService?.previous() }
        playPauseButton.setOnClickListener { playerService?.togglePlayPause() }
        findViewById<View>(R.id.lyricsNextButton).setOnClickListener { playerService?.next() }
        seekBar.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                if (fromUser) {
                    val position = if (latestDurationMs > 0L) latestDurationMs * progress / SEEK_MAX else 0L
                    elapsedTime.text = MusicScannerUtil.formatDuration(position)
                    updateActiveLine(position)
                    updateAiPreviewLine(position)
                }
            }

            override fun onStartTrackingTouch(seekBar: SeekBar?) {
                userSeeking = true
                autoScrollSuppressedUntil = 0L
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

    private fun showTab(index: Int, animate: Boolean) {
        selectedTab = index.coerceIn(TAB_LIVE, TAB_EDIT)
        val sections = listOf(liveSection, onlineSection, aiSection, editSection)
        sections.forEachIndexed { sectionIndex, section ->
            if (sectionIndex == selectedTab) {
                section.visibility = View.VISIBLE
                section.animate().cancel()
                if (animate) {
                    section.alpha = 0f
                    section.translationX = if (sectionIndex > TAB_LIVE) {
                        dp(18f).toFloat()
                    } else {
                        -dp(18f).toFloat()
                    }
                    section.animate().alpha(1f).translationX(0f).setDuration(230L).start()
                } else {
                    section.alpha = 1f
                    section.translationX = 0f
                }
            } else {
                section.animate().cancel()
                section.visibility = View.GONE
            }
        }
    }

    private fun updateActiveLine(positionMs: Long, force: Boolean = false) {
        if (currentLines.isEmpty()) return
        val index = LrcParser.lineIndexAt(currentLines, positionMs)
        if (!force && index == activeLineIndex) return
        activeLineIndex = index
        lyricAdapter.setActiveIndex(index)
        if (index >= 0 && android.os.SystemClock.elapsedRealtime() >= autoScrollSuppressedUntil) {
            centerActiveLine(smooth = !force)
        }
    }

    private fun centerActiveLine(smooth: Boolean) {
        val target = activeLineIndex
        if (target !in currentLines.indices) return
        if (!smooth) {
            (liveRecyclerView.layoutManager as? LinearLayoutManager)
                ?.scrollToPositionWithOffset(target, liveRecyclerView.height / 2 - dp(38f))
            return
        }
        val scroller = object : LinearSmoothScroller(this) {
            override fun calculateDtToFit(
                viewStart: Int,
                viewEnd: Int,
                boxStart: Int,
                boxEnd: Int,
                snapPreference: Int
            ): Int = (boxStart + boxEnd) / 2 - (viewStart + viewEnd) / 2
        }
        scroller.targetPosition = target
        liveRecyclerView.layoutManager?.startSmoothScroll(scroller)
    }

    private fun confirmOnDeviceAi() {
        val song = currentSong
        if (song == null) {
            Toast.makeText(this, R.string.no_song_for_lyrics, Toast.LENGTH_SHORT).show()
            return
        }
        if (!OnDeviceAiLyricsManager.isDurationEligible(song.durationMs)) {
            Toast.makeText(this, R.string.ai_duration_too_long, Toast.LENGTH_LONG).show()
            return
        }
        if (OnDeviceAiLyricsManager.currentState().isRunning) {
            Toast.makeText(this, R.string.ai_job_already_running, Toast.LENGTH_LONG).show()
            return
        }
        val model = OnDeviceAiLyricsManager.modelStatus(applicationContext)
        val mode = if (aiModeToggle.checkedButtonId == R.id.aiKnownLyricsModeButton) {
            AiLyricsMode.ALIGN_KNOWN_LYRICS
        } else {
            AiLyricsMode.AUDIO_ONLY
        }
        val knownLyrics = aiKnownLyricsInput.text?.toString().orEmpty().trim()
        if (mode == AiLyricsMode.ALIGN_KNOWN_LYRICS && knownLyrics.isBlank()) {
            aiKnownLyricsLayout.error = getString(R.string.ai_known_lyrics_required)
            aiKnownLyricsInput.requestFocus()
            return
        }
        aiKnownLyricsLayout.error = null

        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.ai_local_confirmation_title)
            .setMessage(
                if (model.supported) {
                    getString(
                        R.string.ai_local_confirmation_message,
                        model.displayName,
                        model.downloadMegabytes
                    )
                } else {
                    getString(R.string.ai_online_only_confirmation_message)
                }
            )
            .setNegativeButton(android.R.string.cancel, null)
            .setPositiveButton(R.string.ai_confirm_local) { _, _ ->
                val started = OnDeviceAiLyricsManager.start(
                    context = applicationContext,
                    song = song,
                    mode = mode,
                    knownLyrics = knownLyrics,
                    forceBengaliScript = aiBengaliCheckBox.isChecked
                )
                if (!started) {
                    Toast.makeText(this, R.string.ai_job_already_running, Toast.LENGTH_LONG).show()
                }
            }
            .show()
    }

    private fun updateAiModelStatus() {
        val model = OnDeviceAiLyricsManager.modelStatus(applicationContext)
        val ram = String.format(Locale.US, "%.1f", model.totalRamGigabytes)
        aiModelStatus.text = when {
            !model.supported -> getString(R.string.ai_model_unsupported)
            model.downloaded -> getString(
                R.string.ai_model_ready,
                model.displayName,
                ram
            )
            else -> getString(
                R.string.ai_model_selected,
                model.displayName,
                ram,
                model.downloadMegabytes
            )
        }
        val running = OnDeviceAiLyricsManager.currentState().isRunning
        deleteAiModelButton.visibility = if ((model.downloaded || model.obsoleteModelDownloaded) && !running) View.VISIBLE else View.GONE
        deleteAiModelButton.isEnabled = !running
        startAiButton.isEnabled = !running
    }

    private fun renderAiJobState(state: AiLyricsJobState) {
        if (!::aiStatus.isInitialized || isFinishing || isDestroyed) return
        val belongsToCurrentSong = state.songId != null && state.songId == currentSong?.id
        val model = OnDeviceAiLyricsManager.modelStatus(applicationContext)
        val controlsEnabled = !state.isRunning
        aiKnownLyricsInput.isEnabled = controlsEnabled
        aiBengaliCheckBox.isEnabled = controlsEnabled
        startAiButton.isEnabled = controlsEnabled
        deleteAiModelButton.isEnabled = controlsEnabled
        deleteAiModelButton.visibility = if ((model.downloaded || model.obsoleteModelDownloaded) && controlsEnabled) View.VISIBLE else View.GONE
        findViewById<MaterialButton>(R.id.aiAudioOnlyModeButton).isEnabled = controlsEnabled
        findViewById<MaterialButton>(R.id.aiKnownLyricsModeButton).isEnabled = controlsEnabled
        cancelAiButton.visibility = if (state.isRunning) View.VISIBLE else View.GONE

        if (state.songId != null && !belongsToCurrentSong) {
            aiStatus.setText(
                if (state.isRunning) R.string.ai_other_song_running
                else R.string.ai_idle_status
            )
            aiProgress.visibility = if (state.isRunning) View.VISIBLE else View.GONE
            aiProgress.setProgressCompat(state.progress, true)
            showAiPreview(emptyList())
            reviewAiButton.visibility = View.GONE
            aiProcessSteps.visibility = View.GONE
            activeStepAnimator?.cancel()
            activeStepAnimator = null
            updateAiModelStatus()
            return
        }

        val statusText = when (state.phase) {
            AiJobPhase.IDLE -> getString(R.string.ai_idle_status)
            AiJobPhase.SEARCHING_ONLINE -> getString(R.string.ai_searching_metadata_status)
            AiJobPhase.DOWNLOADING_MODEL -> getString(
                R.string.ai_downloading_status,
                ((state.progress * 100) / 35).coerceIn(0, 100)
            )
            AiJobPhase.PREPARING_AUDIO -> getString(
                R.string.ai_preparing_status,
                (((state.progress - 36) * 100) / 12).coerceIn(0, 100)
            )
            AiJobPhase.PROCESSING -> getString(
                R.string.ai_processing_status,
                (((state.progress - 50) * 100) / 44).coerceIn(0, 100)
            )
            AiJobPhase.SEARCHING_RECOGNIZED -> getString(R.string.ai_searching_recognized_status)
            AiJobPhase.FINALIZING -> getString(R.string.ai_finalizing_status)
            AiJobPhase.COMPLETED -> when (state.resultSource) {
                AiLyricsResultSource.ONLINE -> getString(R.string.ai_online_completed_status)
                AiLyricsResultSource.LOCAL_FILE -> getString(R.string.ai_local_file_completed_status)
                AiLyricsResultSource.ALIGNED_ON_DEVICE -> getString(R.string.ai_aligned_completed_status)
                AiLyricsResultSource.ON_DEVICE,
                null -> getString(R.string.ai_completed_status)
            }
            AiJobPhase.FAILED -> getString(
                R.string.ai_failed_status,
                state.message ?: getString(R.string.lyrics_search_failed)
            )
            AiJobPhase.CANCELED -> getString(R.string.ai_canceled_status)
        }
        aiStatus.text = if (!state.message.isNullOrBlank() && state.isRunning) {
            "$statusText\n${getString(R.string.ai_local_detail, state.message)}"
        } else {
            statusText
        }
        aiProgress.visibility = if (state.isRunning || state.phase == AiJobPhase.COMPLETED) {
            View.VISIBLE
        } else {
            View.GONE
        }
        aiProgress.setProgressCompat(state.progress.coerceIn(0, 100), true)

        val resultLines = if (state.phase == AiJobPhase.COMPLETED) {
            state.rawLrc?.let(LrcParser::parse).orEmpty()
        } else {
            emptyList()
        }
        showAiPreview(resultLines)
        reviewAiButton.visibility = if (resultLines.isNotEmpty()) View.VISIBLE else View.GONE
        if (resultLines.isNotEmpty()) updateAiPreviewLine(latestPositionMs, force = true)
        renderProcessSteps(state)
        applySmartOnlineResult(state)
        updateAiModelStatus()
    }

    private fun renderProcessSteps(state: AiLyricsJobState) {
        val visible = state.phase != AiJobPhase.IDLE && state.songId == currentSong?.id
        aiProcessSteps.visibility = if (visible) View.VISIBLE else View.GONE
        activeStepAnimator?.cancel()
        activeStepAnimator = null
        if (!visible) return

        val activeIndex = when (state.phase) {
            AiJobPhase.SEARCHING_ONLINE -> 0
            AiJobPhase.DOWNLOADING_MODEL,
            AiJobPhase.PREPARING_AUDIO -> 1
            AiJobPhase.PROCESSING -> 2
            AiJobPhase.SEARCHING_RECOGNIZED -> 3
            AiJobPhase.FINALIZING -> 4
            else -> -1
        }
        val completedThrough = when (state.phase) {
            AiJobPhase.DOWNLOADING_MODEL,
            AiJobPhase.PREPARING_AUDIO -> 0
            AiJobPhase.PROCESSING -> 1
            AiJobPhase.SEARCHING_RECOGNIZED -> 2
            AiJobPhase.FINALIZING -> 3
            AiJobPhase.COMPLETED -> 4
            AiJobPhase.FAILED -> when {
                state.progress >= 95 -> 2
                state.progress >= 50 -> 1
                else -> 0
            }
            else -> -1
        }
        val initialOnlineCompletion = state.phase == AiJobPhase.COMPLETED &&
            (state.resultSource == AiLyricsResultSource.ONLINE &&
                state.message?.contains("after local listening", ignoreCase = true) != true &&
                state.message?.contains("local sample", ignoreCase = true) != true ||
                state.message?.contains("downloaded timing", ignoreCase = true) == true ||
                state.message?.contains("after the online search", ignoreCase = true) == true)
        val accent = customization.accentColor
        val muted = ContextCompat.getColor(this, R.color.text_muted)
        aiStepIcons.forEachIndexed { index, icon ->
            val completed = if (initialOnlineCompletion) index == 0 || index == 4 else index <= completedThrough
            when {
                index == activeIndex -> {
                    icon.setImageResource(R.drawable.ic_refresh)
                    icon.imageTintList = ColorStateList.valueOf(accent)
                }
                completed -> {
                    icon.setImageResource(R.drawable.ic_check_circle)
                    icon.imageTintList = ColorStateList.valueOf(accent)
                }
                else -> {
                    icon.setImageResource(R.drawable.ic_step_waiting)
                    icon.imageTintList = ColorStateList.valueOf(muted)
                }
            }
            aiStepTexts[index].setTextColor(if (completed || index == activeIndex) accent else muted)
            aiStepTexts[index].alpha = if (completed || index == activeIndex) 1f else 0.72f
        }
        if (activeIndex >= 0) {
            activeStepAnimator = ObjectAnimator.ofFloat(
                aiStepIcons[activeIndex],
                View.ROTATION,
                0f,
                360f
            ).apply {
                duration = 900L
                repeatCount = ValueAnimator.INFINITE
                start()
            }
        }
    }

    private fun applySmartOnlineResult(state: AiLyricsJobState) {
        if (state.phase != AiJobPhase.COMPLETED ||
            state.resultSource !in setOf(
                AiLyricsResultSource.ONLINE,
                AiLyricsResultSource.LOCAL_FILE
            ) ||
            state.songId != currentSong?.id ||
            state.rawLrc.isNullOrBlank()
        ) return
        val service = playerService ?: return
        val key = "${state.songId}:${state.rawLrc.hashCode()}"
        if (appliedSmartResultKey == key) return
        appliedSmartResultKey = key
        service.reloadLyricsFromStorage()
    }

    private fun showAiPreview(lines: List<LrcLine>) {
        if (lines == aiPreviewLines) return
        aiPreviewLines = lines
        aiPreviewActiveIndex = -1
        aiPreviewAdapter.updateLines(lines)
        val visibility = if (lines.isEmpty()) View.GONE else View.VISIBLE
        aiPreviewTitle.visibility = visibility
        aiPreviewRecyclerView.visibility = visibility
    }

    private fun updateAiPreviewLine(positionMs: Long, force: Boolean = false) {
        if (aiPreviewLines.isEmpty()) return
        val index = LrcParser.lineIndexAt(aiPreviewLines, positionMs)
        if (!force && index == aiPreviewActiveIndex) return
        aiPreviewActiveIndex = index
        aiPreviewAdapter.setActiveIndex(index)
        if (index in aiPreviewLines.indices && selectedTab == TAB_AI) {
            (aiPreviewRecyclerView.layoutManager as? LinearLayoutManager)
                ?.scrollToPositionWithOffset(index, aiPreviewRecyclerView.height / 2 - dp(34f))
        }
    }

    private fun loadAiDraftIntoEditor() {
        val state = OnDeviceAiLyricsManager.currentState()
        val rawLrc = state.rawLrc
        if (state.phase != AiJobPhase.COMPLETED ||
            state.songId != currentSong?.id ||
            rawLrc.isNullOrBlank()
        ) return
        setEditorText(rawLrc)
        editorDirty = true
        importedPending = false
        aiDraftPending = state.resultSource == AiLyricsResultSource.ON_DEVICE ||
            state.resultSource == AiLyricsResultSource.ALIGNED_ON_DEVICE
        smartResultPending = true
        tabs.getTabAt(TAB_EDIT)?.select()
        Toast.makeText(
            this,
            if (state.resultSource == AiLyricsResultSource.ONLINE ||
                state.resultSource == AiLyricsResultSource.LOCAL_FILE
            ) {
                R.string.smart_lyrics_loaded_in_editor
            } else {
                R.string.ai_draft_loaded_in_editor
            },
            Toast.LENGTH_LONG
        ).show()
    }

    private fun searchOnline() {
        val song = currentSong
        if (song == null) {
            Toast.makeText(this, R.string.no_song_for_lyrics, Toast.LENGTH_SHORT).show()
            return
        }
        val query = searchInput.text?.toString().orEmpty()
        val generation = ++searchGeneration
        searchButton.isEnabled = false
        searchStatus.setText(R.string.lyrics_searching_online)
        onlineAdapter.submitList(emptyList())
        worker.execute {
            val response = repository.searchOnline(song, query)
            runOnUiThread {
                if (isFinishing || isDestroyed || generation != searchGeneration || currentSong?.id != song.id) {
                    return@runOnUiThread
                }
                searchButton.isEnabled = true
                onlineAdapter.submitList(response.results)
                searchStatus.text = when {
                    response.error == LyricsNetworkError.RATE_LIMITED -> getString(
                        R.string.lyrics_rate_limited,
                        response.retryAfterSeconds ?: 10
                    )
                    response.error != null -> getString(R.string.lyrics_search_failed)
                    response.results.isEmpty() -> getString(R.string.lyrics_no_search_results)
                    else -> getString(R.string.lyrics_results_found, response.results.size)
                }
            }
        }
    }

    private fun confirmOnlineSelection(candidate: OnlineLyricsCandidate) {
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.use_online_lyrics_title)
            .setMessage(
                getString(
                    R.string.use_online_lyrics_message,
                    candidate.trackName,
                    candidate.artistName,
                    candidate.albumName.ifBlank { getString(R.string.unknown_album) },
                    MusicScannerUtil.formatDuration((candidate.durationSeconds * 1_000).toLong())
                )
            )
            .setNegativeButton(android.R.string.cancel, null)
            .setPositiveButton(R.string.download_and_use) { _, _ ->
                if (playerService?.useOnlineLyrics(candidate) == true) {
                    editorDirty = false
                    importedPending = false
                    aiDraftPending = false
                    smartResultPending = false
                    tabs.getTabAt(TAB_LIVE)?.select()
                    Toast.makeText(this, R.string.lyrics_saved, Toast.LENGTH_SHORT).show()
                }
            }
            .show()
    }

    private fun importLrc(uri: Uri) {
        val songId = currentSong?.id
        worker.execute {
            val text = try {
                contentResolver.openInputStream(uri)?.bufferedReader(Charsets.UTF_8)?.use { reader ->
                    val content = reader.readText()
                    content.takeIf { it.length <= MAX_LRC_CHARACTERS }
                }
            } catch (_: Exception) {
                null
            }
            runOnUiThread {
                if (isFinishing || isDestroyed || currentSong?.id != songId) return@runOnUiThread
                if (text == null) {
                    Toast.makeText(this, R.string.unable_to_import_lrc, Toast.LENGTH_LONG).show()
                } else {
                    setEditorText(text)
                    editorDirty = true
                    importedPending = true
                    aiDraftPending = false
                    smartResultPending = false
                    Toast.makeText(this, R.string.lrc_imported, Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private fun insertCurrentTimestamp() {
        if (currentSong == null) {
            Toast.makeText(this, R.string.no_song_for_lyrics, Toast.LENGTH_SHORT).show()
            return
        }
        val totalCentiseconds = latestPositionMs.coerceAtLeast(0L) / 10L
        val minutes = totalCentiseconds / 6_000L
        val seconds = (totalCentiseconds % 6_000L) / 100L
        val centiseconds = totalCentiseconds % 100L
        val stamp = String.format(Locale.US, "[%02d:%02d.%02d] ", minutes, seconds, centiseconds)
        val original = editor.text?.toString().orEmpty()
        val lines = original.split('\n').toMutableList()
        val selection = editor.selectionStart.coerceIn(0, original.length)
        val cursorLine = original.substring(0, selection).count { it == '\n' }
            .coerceIn(0, lines.lastIndex.coerceAtLeast(0))
        fun isUntimedLyric(line: String): Boolean {
            val value = line.trim()
            return value.isNotEmpty() &&
                !TIMED_LINE_PREFIX.containsMatchIn(value) &&
                !LRC_METADATA_LINE.matches(value)
        }

        val searchOrder = (cursorLine until lines.size) + (0 until cursorLine)
        val lineIndex = searchOrder.firstOrNull { isUntimedLyric(lines[it]) }
        if (lineIndex == null) {
            if (original.isBlank()) {
                setEditorText(stamp)
                editorDirty = true
                editor.requestFocus()
            } else {
                Toast.makeText(this, R.string.all_lyrics_lines_timed, Toast.LENGTH_SHORT).show()
            }
            return
        }

        lines[lineIndex] = stamp + lines[lineIndex].trimStart()
        val updated = lines.joinToString("\n")
        editor.setText(updated)
        val nextLineIndex = ((lineIndex + 1) until lines.size)
            .firstOrNull { isUntimedLyric(lines[it]) }
            ?: (0 until lineIndex).firstOrNull { isUntimedLyric(lines[it]) }
        val nextSelection = if (nextLineIndex != null) {
            lines.take(nextLineIndex).sumOf { it.length + 1 }
        } else {
            lines.take(lineIndex).sumOf { it.length + 1 } + lines[lineIndex].length
        }
        editor.setSelection(nextSelection.coerceIn(0, updated.length))
        editorDirty = true
        editor.requestFocus()
    }

    private fun saveEditedLyrics() {
        if (currentSong == null) {
            Toast.makeText(this, R.string.no_song_for_lyrics, Toast.LENGTH_SHORT).show()
            return
        }
        val raw = editor.text?.toString().orEmpty()
        if (LrcParser.parse(raw).isEmpty()) {
            Toast.makeText(this, R.string.invalid_lrc, Toast.LENGTH_LONG).show()
            return
        }
        val source = when {
            aiDraftPending || currentLyrics?.source == LyricsSource.AI_GENERATED -> {
                LyricsSource.AI_GENERATED
            }
            importedPending -> LyricsSource.IMPORTED_FILE
            else -> LyricsSource.USER_EDITED
        }
        if (playerService?.saveUserLyrics(raw, source) == true) {
            val clearSmartResult = smartResultPending
            editorDirty = false
            importedPending = false
            aiDraftPending = false
            smartResultPending = false
            if (clearSmartResult) OnDeviceAiLyricsManager.clearFinishedResult()
            tabs.getTabAt(TAB_LIVE)?.select()
            Toast.makeText(this, R.string.lyrics_saved, Toast.LENGTH_SHORT).show()
        }
    }

    private fun restoreAutomaticLyrics() {
        if (currentSong == null) return
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.restore_automatic_lyrics)
            .setMessage(R.string.automatic_lyrics_restored)
            .setNegativeButton(android.R.string.cancel, null)
            .setPositiveButton(R.string.restore_automatic_lyrics) { _, _ ->
                editorDirty = false
                importedPending = false
                aiDraftPending = false
                smartResultPending = false
                setEditorText("")
                playerService?.restoreAutomaticLyrics()
                tabs.getTabAt(TAB_LIVE)?.select()
            }
            .show()
    }

    private fun confirmPublish() {
        val song = currentSong
        val raw = editor.text?.toString().orEmpty()
        if (song == null) {
            Toast.makeText(this, R.string.no_song_for_lyrics, Toast.LENGTH_SHORT).show()
            return
        }
        if (LrcParser.parse(raw).isEmpty()) {
            Toast.makeText(this, R.string.invalid_lrc, Toast.LENGTH_LONG).show()
            return
        }
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.publish_confirmation_title)
            .setMessage(R.string.publish_confirmation_message)
            .setNegativeButton(android.R.string.cancel, null)
            .setPositiveButton(R.string.publish_publicly) { _, _ -> publishLyrics(song, raw) }
            .show()
    }

    private fun publishLyrics(song: Song, raw: String) {
        val generation = ++publishGeneration
        publishButton.isEnabled = false
        publishStatus.text = getString(R.string.publish_working, "0")
        worker.execute {
            val result = repository.publishToLrclib(song, raw) { attempts ->
                runOnUiThread {
                    if (generation == publishGeneration) {
                        publishStatus.text = getString(
                            R.string.publish_working,
                            String.format(Locale.US, "%,d", attempts)
                        )
                    }
                }
            }
            runOnUiThread {
                if (isFinishing || isDestroyed || generation != publishGeneration) return@runOnUiThread
                publishButton.isEnabled = true
                publishStatus.text = if (result.successful) {
                    getString(R.string.publish_success)
                } else {
                    getString(R.string.publish_failed, result.message ?: getString(R.string.lyrics_search_failed))
                }
            }
        }
    }

    private fun setEditorText(value: String) {
        editorProgrammaticChange = true
        editor.setText(value)
        editor.setSelection(editor.text?.length ?: 0)
        editorProgrammaticChange = false
    }

    private fun showLyricsEmpty(titleRes: Int) {
        if (currentLines.isNotEmpty()) return
        liveRecyclerView.visibility = View.INVISIBLE
        liveEmptyState.visibility = View.VISIBLE
        liveEmptyTitle.setText(titleRes)
    }

    private fun showTimingCorrectionDialog() {
        val result = currentLyrics ?: return
        val songDurationMs = latestDurationMs.takeIf { it > 0L }
            ?: currentSong?.durationMs?.takeIf { it > 0L }
            ?: 0L
        val dialogView = layoutInflater.inflate(R.layout.dialog_lyrics_timing, null)
        val durationStatus = dialogView.findViewById<TextView>(R.id.timingDurationStatus)
        val adjustmentStatus = dialogView.findViewById<TextView>(R.id.timingAdjustmentStatus)
        val referenceDurationMs = result.referenceDurationMs
        durationStatus.text = if (referenceDurationMs != null && songDurationMs > 0L) {
            getString(
                if (result.timingAutoAdjusted) {
                    R.string.timing_duration_comparison_adjusted
                } else {
                    R.string.timing_duration_comparison
                },
                MusicScannerUtil.formatDuration(referenceDurationMs),
                MusicScannerUtil.formatDuration(songDurationMs)
            )
        } else {
            getString(
                R.string.timing_duration_unknown,
                MusicScannerUtil.formatDuration(songDurationMs)
            )
        }

        var cumulativeShiftMs = 0L
        fun applyShift(deltaMs: Long) {
            if (playerService?.shiftCurrentLyrics(deltaMs) == true) {
                cumulativeShiftMs += deltaMs
                adjustmentStatus.text = getString(
                    R.string.timing_manual_adjustment,
                    String.format(Locale.US, "%+.1f", cumulativeShiftMs / 1_000.0)
                )
            }
        }
        dialogView.findViewById<View>(R.id.moveLyricsEarlierButton).setOnClickListener {
            applyShift(-SMALL_TIMING_STEP_MS)
        }
        dialogView.findViewById<View>(R.id.moveLyricsLaterButton).setOnClickListener {
            applyShift(SMALL_TIMING_STEP_MS)
        }
        dialogView.findViewById<View>(R.id.moveLyricsEarlierLargeButton).setOnClickListener {
            applyShift(-LARGE_TIMING_STEP_MS)
        }
        dialogView.findViewById<View>(R.id.moveLyricsLaterLargeButton).setOnClickListener {
            applyShift(LARGE_TIMING_STEP_MS)
        }
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.fix_lyrics_timing_title)
            .setView(dialogView)
            .setNegativeButton(R.string.close, null)
            .show()
    }

    private fun sourceLabel(result: LyricsResult?): Int {
        if (result?.timingAutoAdjusted == true) return R.string.lyrics_source_online_adjusted
        return when (result?.source) {
            LyricsSource.USER_EDITED -> R.string.lyrics_source_edited
            LyricsSource.AI_GENERATED -> R.string.lyrics_source_ai
            LyricsSource.IMPORTED_FILE -> R.string.lyrics_source_imported
            LyricsSource.ONLINE_SELECTED -> R.string.lyrics_source_selected
            LyricsSource.DOWNLOADED_CACHE -> R.string.lyrics_source_cache
            LyricsSource.LOCAL_SIDECAR -> R.string.lyrics_source_local
            LyricsSource.ONLINE_AUTO -> R.string.lyrics_source_online
            null -> R.string.no_timed_lyrics
        }
    }

    private fun knownArtistText(song: Song): String = song.artist.takeUnless {
        it.equals(getString(R.string.unknown_artist), ignoreCase = true)
    }.orEmpty()

    private fun openOrRefreshOverlay() {
        if (Settings.canDrawOverlays(this)) {
            playerService?.refreshOverlayNow()
            Toast.makeText(this, R.string.floating_overlay_verified, Toast.LENGTH_LONG).show()
            updateOverlayButton()
        } else {
            try {
                startActivity(
                    Intent(
                        Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                        Uri.parse("package:$packageName")
                    )
                )
            } catch (_: Exception) {
                Toast.makeText(this, R.string.unable_to_open_overlay_settings, Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun updateOverlayButton() {
        if (!::overlayStatusButton.isInitialized) return
        val allowed = Settings.canDrawOverlays(this)
        overlayStatusButton.setText(
            if (allowed) R.string.floating_overlay_ready else R.string.enable_floating_overlay
        )
        overlayStatusButton.icon = ContextCompat.getDrawable(this, R.drawable.ic_lyrics)
        overlayStatusButton.iconTint = ColorStateList.valueOf(
            if (allowed) ContextCompat.getColor(this, R.color.success) else customization.accentColor
        )
        if (allowed) playerService?.refreshOverlayNow()
    }

    private fun updatePlayPause(isPlaying: Boolean, isBuffering: Boolean) {
        val active = isPlaying || isBuffering
        val expected = if (active) R.drawable.ic_pause else R.drawable.ic_play
        if (playPauseButton.tag == expected) return
        playPauseButton.tag = expected
        playPauseButton.animate().cancel()
        playPauseButton.animate().scaleX(0.72f).scaleY(0.72f).alpha(0.4f).setDuration(80L)
            .withEndAction {
                playPauseButton.setImageResource(expected)
                playPauseButton.contentDescription = getString(if (active) R.string.pause else R.string.play)
                playPauseButton.animate().scaleX(1f).scaleY(1f)
                    .alpha(if (isBuffering) 0.7f else 1f).setDuration(160L).start()
            }.start()
    }

    private fun applyCustomization() {
        AppUi.applySystemBars(this)
        AppUi.applyTypeface(root, customization.appFont)
        if (::lyricAdapter.isInitialized) lyricAdapter.updateConfiguration(customization)
        if (::onlineAdapter.isInitialized) onlineAdapter.updateConfiguration(customization)
        if (::aiPreviewAdapter.isInitialized) aiPreviewAdapter.updateConfiguration(customization)
        val accent = customization.accentColor
        tabs.setSelectedTabIndicatorColor(accent)
        tabs.setTabTextColors(ContextCompat.getColor(this, R.color.text_secondary), accent)
        seekBar.progressTintList = ColorStateList.valueOf(accent)
        seekBar.thumbTintList = ColorStateList.valueOf(accent)
        aiProgress.setIndicatorColor(accent)
        aiBengaliCheckBox.buttonTintList = ColorStateList(
            arrayOf(intArrayOf(android.R.attr.state_checked), intArrayOf()),
            intArrayOf(accent, ContextCompat.getColor(this, R.color.text_secondary))
        )
        playPauseCard.setCardBackgroundColor(accent)
        playPauseCard.rippleColor = ColorStateList.valueOf(
            ColorUtils.setAlphaComponent(AppUi.contrastTextColor(accent), 45)
        )
        playPauseButton.imageTintList = ColorStateList.valueOf(AppUi.contrastTextColor(accent))
        val onAccent = AppUi.contrastTextColor(accent)
        listOf(
            searchButton,
            saveButton,
            startAiButton,
            reviewAiButton,
            findViewById<MaterialButton>(R.id.createAiLyricsButton)
        ).forEach { button ->
            button.backgroundTintList = ColorStateList.valueOf(accent)
            button.setTextColor(onAccent)
            button.iconTint = ColorStateList.valueOf(onAccent)
        }
        listOf(
            R.id.findOnlineLyricsButton,
            R.id.openLyricsEditorButton,
            R.id.retryAutomaticLyricsButton,
            R.id.aiAudioOnlyModeButton,
            R.id.aiKnownLyricsModeButton,
            R.id.cancelAiLyricsButton,
            R.id.deleteAiModelButton,
            R.id.importLrcButton,
            R.id.insertTimestampButton,
            R.id.restoreAutomaticLyricsButton,
            R.id.publishLyricsButton,
            R.id.overlayStatusButton,
            R.id.fixLyricsTimingButton
        ).forEach { id ->
            findViewById<MaterialButton>(id).apply {
                setTextColor(accent)
                iconTint = ColorStateList.valueOf(accent)
                strokeColor = ColorStateList.valueOf(ColorUtils.setAlphaComponent(accent, 150))
            }
        }
        val aiModeBackground = ColorStateList(
            arrayOf(intArrayOf(android.R.attr.state_checked), intArrayOf()),
            intArrayOf(ColorUtils.setAlphaComponent(accent, 35), android.graphics.Color.TRANSPARENT)
        )
        findViewById<MaterialButton>(R.id.aiAudioOnlyModeButton).backgroundTintList = aiModeBackground
        findViewById<MaterialButton>(R.id.aiKnownLyricsModeButton).backgroundTintList = aiModeBackground
        if (::aiProcessSteps.isInitialized) renderProcessSteps(OnDeviceAiLyricsManager.currentState())
        updateOverlayButton()
        playerService?.let { service ->
            onSleepTimerChanged(service.sleepTimerEndAtMs(), service.sleepsAfterCurrentSong())
        }
    }

    private fun closeLyrics() {
        finish()
        overridePendingTransition(R.anim.player_background_fade, R.anim.lyrics_exit)
    }

    override fun onBackPressed() = closeLyrics()

    private fun dp(value: Float): Int = (value * resources.displayMetrics.density).toInt()

    companion object {
        private const val TAB_LIVE = 0
        private const val TAB_ONLINE = 1
        private const val TAB_AI = 2
        private const val TAB_EDIT = 3
        private const val SEEK_MAX = 1_000
        private const val USER_SCROLL_PAUSE_MS = 5_000L
        private const val SMALL_TIMING_STEP_MS = 500L
        private const val LARGE_TIMING_STEP_MS = 5_000L
        private const val MAX_LRC_CHARACTERS = 1_000_000
        private const val STATE_TAB = "lyrics_selected_tab"
        private val TIMED_LINE_PREFIX = Regex("""^\[\d{1,3}:\d{1,2}(?:[.:]\d{1,3})?]""")
        private val LRC_METADATA_LINE = Regex("""^\[[A-Za-z]{1,10}:.*]$""")
    }
}
