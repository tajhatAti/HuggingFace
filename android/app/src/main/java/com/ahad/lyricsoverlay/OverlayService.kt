package com.ahad.lyricsoverlay

import android.animation.ArgbEvaluator
import android.animation.ValueAnimator
import android.app.Service
import android.content.Intent
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.Typeface
import android.os.Binder
import android.os.Build
import android.os.IBinder
import android.provider.Settings
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.view.animation.AccelerateDecelerateInterpolator
import android.view.animation.DecelerateInterpolator
import android.view.animation.OvershootInterpolator
import android.widget.TextView
import androidx.core.content.res.ResourcesCompat

class OverlayService : Service(), AppPreferenceListener {

    inner class LocalBinder : Binder() {
        fun getService(): OverlayService = this@OverlayService
    }

    private val binder = LocalBinder()
    private lateinit var windowManager: WindowManager

    private var lyricTextView: TextView? = null
    private var layoutParams: WindowManager.LayoutParams? = null
    private var lyrics: List<LrcLine> = emptyList()
    private var currentLineIndex = -1
    private var animationGeneration = 0
    private var colorAnimator: ValueAnimator? = null

    private var fontSizeSp = DEFAULT_FONT_SIZE
    private var fontStyle = FONT_BOLD
    private var preferredColor = DEFAULT_TEXT_COLOR
    private var animationStyle = ANIMATION_SCALE

    override fun onCreate() {
        super.onCreate()
        windowManager = getSystemService(WINDOW_SERVICE) as WindowManager
        loadPreferences()
        AppPreferences.registerListener(this)
    }

    override fun onBind(intent: Intent?): IBinder = binder

    override fun onDestroy() {
        animationGeneration++
        colorAnimator?.cancel()
        AppPreferences.unregisterListener(this)
        removeOverlay()
        super.onDestroy()
    }

    override fun onAppPreferenceChanged(
        snapshot: CustomizationSnapshot,
        changedKey: String
    ) {
        if (!changedKey.startsWith("overlay_")) return
        loadPreferences()
        applyTextAppearance()
        if (changedKey == AppPreferences.KEY_OVERLAY_X ||
            changedKey == AppPreferences.KEY_OVERLAY_Y
        ) {
            applySavedPosition()
        }
    }

    fun setLyrics(rawLrc: String?) {
        lyrics = rawLrc?.let(LrcParser::parse).orEmpty()
        currentLineIndex = -1
        animationGeneration++
        if (lyrics.isEmpty()) removeOverlay()
    }

    fun updatePlayback(positionMs: Long, isPlaying: Boolean) {
        if (lyrics.isEmpty()) {
            removeOverlay()
            return
        }

        val lineIndex = LrcParser.lineIndexAt(lyrics, positionMs)
        if (lineIndex < 0) {
            lyricTextView?.visibility = View.INVISIBLE
            currentLineIndex = -1
            return
        }

        if (lineIndex != currentLineIndex || lyricTextView == null) {
            if (showLine(lyrics[lineIndex].text, lineIndex)) {
                currentLineIndex = lineIndex
            }
        } else if (lyricTextView?.visibility != View.VISIBLE) {
            lyricTextView?.visibility = View.VISIBLE
        }

        // Pausing intentionally leaves the current line visible.
        @Suppress("UNUSED_VARIABLE")
        val playbackActive = isPlaying
    }

    fun clearLyrics() {
        lyrics = emptyList()
        currentLineIndex = -1
        removeOverlay()
    }

    private fun showLine(text: String, lineIndex: Int): Boolean {
        if (text.isBlank() || !Settings.canDrawOverlays(this)) return false
        val textView = ensureOverlay() ?: return false
        val generation = ++animationGeneration
        textView.animate().cancel()
        colorAnimator?.cancel()
        textView.visibility = View.VISIBLE

        if (animationStyle == ANIMATION_NONE || textView.text.isNullOrEmpty() || textView.alpha == 0f) {
            setAndAnimateIn(textView, text, lineIndex, generation)
            return true
        }

        val outgoing = textView.animate()
            .alpha(0f)
            .setDuration(95L)
            .setInterpolator(AccelerateDecelerateInterpolator())

        when (animationStyle) {
            ANIMATION_SLIDE -> outgoing.translationX(-dp(22f).toFloat())
            ANIMATION_RISE -> outgoing.translationY(-dp(12f).toFloat())
            ANIMATION_FLIP -> outgoing.rotationX(-55f).scaleY(0.92f)
            ANIMATION_POP -> outgoing.scaleX(0.72f).scaleY(0.72f)
            ANIMATION_FADE -> outgoing.scaleX(0.98f).scaleY(0.98f)
            else -> outgoing.scaleX(0.88f).scaleY(0.88f)
        }

        outgoing.withEndAction {
            if (generation == animationGeneration) {
                setAndAnimateIn(textView, text, lineIndex, generation)
            }
        }.start()
        return true
    }

    private fun setAndAnimateIn(
        textView: TextView,
        text: String,
        lineIndex: Int,
        generation: Int
    ) {
        if (generation != animationGeneration) return

        val startColor = textView.currentTextColor
        val targetColor = colorVariantForLine(preferredColor, lineIndex)
        textView.text = text
        textView.visibility = View.VISIBLE
        textView.translationX = 0f
        textView.translationY = 0f
        textView.rotationX = 0f
        textView.rotationY = 0f
        textView.scaleX = 1f
        textView.scaleY = 1f

        if (animationStyle == ANIMATION_NONE) {
            textView.alpha = 1f
            textView.setTextColor(targetColor)
            return
        }

        textView.alpha = 0f
        when (animationStyle) {
            ANIMATION_SLIDE -> textView.translationX = dp(26f).toFloat()
            ANIMATION_RISE -> textView.translationY = dp(18f).toFloat()
            ANIMATION_FLIP -> {
                textView.rotationX = 72f
                textView.scaleY = 0.90f
            }
            ANIMATION_POP -> {
                textView.scaleX = 0.62f
                textView.scaleY = 0.62f
            }
            ANIMATION_FADE -> {
                textView.scaleX = 0.98f
                textView.scaleY = 0.98f
            }
            else -> {
                textView.scaleX = 0.86f
                textView.scaleY = 0.86f
            }
        }

        colorAnimator = ValueAnimator.ofObject(ArgbEvaluator(), startColor, targetColor).apply {
            duration = 240L
            addUpdateListener { animator ->
                textView.setTextColor(animator.animatedValue as Int)
            }
            start()
        }

        textView.animate()
            .alpha(1f)
            .translationX(0f)
            .translationY(0f)
            .rotationX(0f)
            .scaleX(1f)
            .scaleY(1f)
            .setDuration(if (animationStyle == ANIMATION_POP) 300L else 235L)
            .setInterpolator(
                when (animationStyle) {
                    ANIMATION_POP -> OvershootInterpolator(1.25f)
                    ANIMATION_RISE, ANIMATION_SLIDE -> DecelerateInterpolator(1.6f)
                    else -> AccelerateDecelerateInterpolator()
                }
            )
            .start()
    }

    private fun ensureOverlay(): TextView? {
        lyricTextView?.let { return it }
        if (!Settings.canDrawOverlays(this)) return null

        val textView = TextView(this).apply {
            setBackgroundColor(Color.TRANSPARENT)
            background = null
            gravity = Gravity.CENTER
            maxLines = 3
            maxWidth = resources.displayMetrics.widthPixels - dp(28f)
            setPadding(dp(6f), dp(6f), dp(6f), dp(6f))
            includeFontPadding = false
            alpha = 0f
        }
        applyTextAppearance(textView)
        attachDragListener(textView)

        val windowType = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        } else {
            @Suppress("DEPRECATION")
            WindowManager.LayoutParams.TYPE_PHONE
        }
        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            windowType,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = savedX()
            y = savedY()
        }

        return try {
            windowManager.addView(textView, params)
            lyricTextView = textView
            layoutParams = params
            textView
        } catch (_: Exception) {
            lyricTextView = null
            layoutParams = null
            null
        }
    }

    private fun removeOverlay() {
        lyricTextView?.let { view ->
            try {
                windowManager.removeView(view)
            } catch (_: Exception) {
                // The overlay may already have been detached by the system.
            }
        }
        lyricTextView = null
        layoutParams = null
    }

    private fun attachDragListener(view: TextView) {
        var initialX = 0
        var initialY = 0
        var initialTouchX = 0f
        var initialTouchY = 0f

        view.setOnTouchListener { _, event ->
            val params = layoutParams
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    initialX = params?.x ?: savedX()
                    initialY = params?.y ?: savedY()
                    initialTouchX = event.rawX
                    initialTouchY = event.rawY
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    if (params != null) {
                        val maxX = (resources.displayMetrics.widthPixels - view.width).coerceAtLeast(0)
                        val maxY = (resources.displayMetrics.heightPixels - view.height).coerceAtLeast(0)
                        params.x = (initialX + (event.rawX - initialTouchX).toInt()).coerceIn(0, maxX)
                        params.y = (initialY + (event.rawY - initialTouchY).toInt()).coerceIn(0, maxY)
                        try {
                            windowManager.updateViewLayout(view, params)
                        } catch (_: Exception) {
                            // Ignore a race with window removal.
                        }
                    }
                    true
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    if (params != null) {
                        AppPreferences.setOverlayPosition(params.x, params.y)
                    }
                    true
                }
                else -> false
            }
        }
    }

    private fun loadPreferences() {
        fontSizeSp = AppPreferences.overlayFontSize()
        fontStyle = AppPreferences.overlayFontStyle()
        preferredColor = AppPreferences.overlayTextColor()
        animationStyle = AppPreferences.overlayAnimation()
    }

    private fun applyTextAppearance(textView: TextView? = lyricTextView) {
        textView ?: return
        textView.textSize = fontSizeSp
        textView.typeface = when (fontStyle) {
            FONT_REGULAR -> Typeface.create(Typeface.SANS_SERIF, Typeface.NORMAL)
            FONT_SERIF -> Typeface.create(Typeface.SERIF, Typeface.BOLD)
            FONT_MONOSPACE -> Typeface.create(Typeface.MONOSPACE, Typeface.BOLD)
            FONT_HIND_SILIGURI -> bundledTypeface(R.font.hind_siliguri_regular)
            FONT_HIND_SILIGURI_MEDIUM -> bundledTypeface(R.font.hind_siliguri_medium)
            FONT_HIND_SILIGURI_BOLD -> bundledTypeface(R.font.hind_siliguri_bold)
            FONT_ATMA -> bundledTypeface(R.font.atma_regular)
            FONT_ATMA_MEDIUM -> bundledTypeface(R.font.atma_medium)
            else -> Typeface.create(Typeface.SANS_SERIF, Typeface.BOLD)
        }
        textView.setTextColor(preferredColor)
    }

    private fun bundledTypeface(fontResource: Int): Typeface =
        ResourcesCompat.getFont(this, fontResource) ?: Typeface.DEFAULT_BOLD

    private fun applySavedPosition() {
        val view = lyricTextView ?: return
        val params = layoutParams ?: return
        params.x = savedX()
        params.y = savedY()
        try {
            windowManager.updateViewLayout(view, params)
        } catch (_: Exception) {
            // Ignore a race with window removal.
        }
    }

    private fun savedX(): Int = AppPreferences.overlayX() ?: dp(24f)

    private fun savedY(): Int = AppPreferences.overlayY()
        ?: (resources.displayMetrics.heightPixels * 0.68f).toInt()

    private fun colorVariantForLine(baseColor: Int, index: Int): Int {
        val hsv = FloatArray(3)
        Color.colorToHSV(baseColor, hsv)
        if (hsv[1] < 0.08f) {
            hsv[0] = floatArrayOf(260f, 205f, 325f, 155f)[index % 4]
            hsv[1] = 0.12f
            hsv[2] = 1f
        } else {
            hsv[0] = (hsv[0] + floatArrayOf(-7f, 0f, 7f)[index % 3] + 360f) % 360f
            hsv[2] = (hsv[2] * if (index % 2 == 0) 1f else 0.92f).coerceIn(0.55f, 1f)
        }
        return Color.HSVToColor(Color.alpha(baseColor), hsv)
    }

    private fun dp(value: Float): Int = (value * resources.displayMetrics.density).toInt()

    companion object {
        const val FONT_REGULAR = AppPreferences.OVERLAY_FONT_REGULAR
        const val FONT_BOLD = AppPreferences.OVERLAY_FONT_BOLD
        const val FONT_SERIF = AppPreferences.OVERLAY_FONT_SERIF
        const val FONT_MONOSPACE = AppPreferences.OVERLAY_FONT_MONOSPACE
        const val FONT_HIND_SILIGURI = AppPreferences.OVERLAY_FONT_HIND_SILIGURI
        const val FONT_HIND_SILIGURI_MEDIUM = AppPreferences.OVERLAY_FONT_HIND_SILIGURI_MEDIUM
        const val FONT_HIND_SILIGURI_BOLD = AppPreferences.OVERLAY_FONT_HIND_SILIGURI_BOLD
        const val FONT_ATMA = AppPreferences.OVERLAY_FONT_ATMA
        const val FONT_ATMA_MEDIUM = AppPreferences.OVERLAY_FONT_ATMA_MEDIUM

        const val ANIMATION_FADE = AppPreferences.OVERLAY_ANIMATION_FADE
        const val ANIMATION_SCALE = AppPreferences.OVERLAY_ANIMATION_SCALE
        const val ANIMATION_SLIDE = AppPreferences.OVERLAY_ANIMATION_SLIDE
        const val ANIMATION_RISE = AppPreferences.OVERLAY_ANIMATION_RISE
        const val ANIMATION_POP = AppPreferences.OVERLAY_ANIMATION_POP
        const val ANIMATION_FLIP = AppPreferences.OVERLAY_ANIMATION_FLIP
        const val ANIMATION_NONE = AppPreferences.OVERLAY_ANIMATION_NONE

        const val DEFAULT_FONT_SIZE = AppPreferences.DEFAULT_OVERLAY_FONT_SIZE
        const val MIN_FONT_SIZE = AppPreferences.MIN_OVERLAY_FONT_SIZE
        const val MAX_FONT_SIZE = AppPreferences.MAX_OVERLAY_FONT_SIZE
        val DEFAULT_TEXT_COLOR: Int = AppPreferences.DEFAULT_OVERLAY_COLOR
    }
}
