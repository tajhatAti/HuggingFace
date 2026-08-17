package com.ahad.lyricsoverlay

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import android.view.View
import android.view.ViewGroup
import android.view.animation.DecelerateInterpolator
import android.view.animation.OvershootInterpolator
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.SeekBar
import android.widget.Spinner
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.content.res.ResourcesCompat
import com.google.android.material.card.MaterialCardView

class SettingsActivity : AppCompatActivity(), AppPreferenceListener {

    private lateinit var settingsRoot: View
    private lateinit var themeModeSpinner: Spinner
    private lateinit var gridColumnsSpinner: Spinner
    private lateinit var itemStyleSpinner: Spinner
    private lateinit var sortOrderSpinner: Spinner
    private lateinit var appFontSpinner: Spinner
    private lateinit var customColorPicker: ColorPickerView
    private lateinit var customColorHex: TextView
    private lateinit var applyCustomColorButton: Button
    private lateinit var accentCard: MaterialCardView

    private lateinit var permissionStatus: TextView
    private lateinit var permissionButton: Button
    private lateinit var previewText: TextView
    private lateinit var fontSizeValue: TextView
    private lateinit var fontSizeSeekBar: SeekBar
    private lateinit var fontStyleSpinner: Spinner
    private lateinit var animationSpinner: Spinner

    private var customization = AppPreferences.snapshot()
    private var selectedCustomColor = customization.accentColor
    private var selectedOverlayColor = AppPreferences.overlayTextColor()
    private val accentViews = linkedMapOf<Int, View>()
    private val overlayColorViews = linkedMapOf<Int, View>()
    private val spinnerAdapters = mutableListOf<ThemedSpinnerAdapter>()
    private val overlayFontValues = listOf(
        AppPreferences.OVERLAY_FONT_BOLD,
        AppPreferences.OVERLAY_FONT_REGULAR,
        AppPreferences.OVERLAY_FONT_SERIF,
        AppPreferences.OVERLAY_FONT_MONOSPACE,
        AppPreferences.OVERLAY_FONT_HIND_SILIGURI,
        AppPreferences.OVERLAY_FONT_HIND_SILIGURI_MEDIUM,
        AppPreferences.OVERLAY_FONT_HIND_SILIGURI_BOLD,
        AppPreferences.OVERLAY_FONT_ATMA,
        AppPreferences.OVERLAY_FONT_ATMA_MEDIUM
    )
    private val overlayAnimationValues = listOf(
        AppPreferences.OVERLAY_ANIMATION_FADE,
        AppPreferences.OVERLAY_ANIMATION_SCALE,
        AppPreferences.OVERLAY_ANIMATION_SLIDE,
        AppPreferences.OVERLAY_ANIMATION_RISE,
        AppPreferences.OVERLAY_ANIMATION_POP,
        AppPreferences.OVERLAY_ANIMATION_FLIP,
        AppPreferences.OVERLAY_ANIMATION_NONE
    )

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_settings)

        customization = AppPreferences.snapshot()
        bindViews()
        setupLibraryCustomization()
        setupAccentColors()
        setupPermissionControls()
        setupOverlayFontSize()
        setupOverlayFontStyle()
        setupOverlayColorPalette()
        setupOverlayAnimationStyle()
        setupResetPosition()
        refreshAllControls()
        AppUi.apply(this, settingsRoot, customization)
        AppPreferences.registerListener(this)
    }

    override fun onResume() {
        super.onResume()
        refreshPermissionState()
        AppUi.apply(this, settingsRoot, AppPreferences.snapshot())
    }

    override fun onDestroy() {
        AppPreferences.unregisterListener(this)
        super.onDestroy()
    }

    override fun onAppPreferenceChanged(snapshot: CustomizationSnapshot, changedKey: String) {
        runOnUiThread {
            if (isFinishing || isDestroyed) return@runOnUiThread
            val oldTheme = customization.themeMode
            customization = snapshot
            if (changedKey == AppPreferences.KEY_THEME_MODE && oldTheme != snapshot.themeMode) {
                LyrApplication.applyThemeMode(snapshot.themeMode)
                return@runOnUiThread
            }

            if (changedKey.startsWith("overlay_")) {
                refreshOverlayControls(changedKey)
            } else {
                refreshLibraryControls()
                AppUi.apply(this, settingsRoot, snapshot)
                spinnerAdapters.forEach { adapter -> adapter.notifyDataSetChanged() }
            }
        }
    }

    private fun bindViews() {
        settingsRoot = findViewById(R.id.settingsRoot)
        findViewById<View>(R.id.backButton).setOnClickListener { finish() }
        themeModeSpinner = findViewById(R.id.themeModeSpinner)
        gridColumnsSpinner = findViewById(R.id.gridColumnsSpinner)
        itemStyleSpinner = findViewById(R.id.itemStyleSpinner)
        sortOrderSpinner = findViewById(R.id.sortOrderSpinner)
        appFontSpinner = findViewById(R.id.appFontSpinner)
        customColorPicker = findViewById(R.id.customColorPicker)
        customColorHex = findViewById(R.id.customColorHex)
        applyCustomColorButton = findViewById(R.id.applyCustomColorButton)
        accentCard = findViewById(R.id.accentCard)

        permissionStatus = findViewById(R.id.overlayPermissionStatus)
        permissionButton = findViewById(R.id.overlayPermissionButton)
        previewText = findViewById(R.id.previewText)
        fontSizeValue = findViewById(R.id.fontSizeValue)
        fontSizeSeekBar = findViewById(R.id.fontSizeSeekBar)
        fontStyleSpinner = findViewById(R.id.fontStyleSpinner)
        animationSpinner = findViewById(R.id.animationSpinner)
    }

    private fun setupLibraryCustomization() {
        val themeValues = listOf(AppThemeMode.SYSTEM, AppThemeMode.LIGHT, AppThemeMode.DARK)
        setSpinner(
            themeModeSpinner,
            listOf(getString(R.string.theme_system), getString(R.string.theme_light), getString(R.string.theme_dark)),
            themeValues.indexOf(customization.themeMode)
        ) { position -> AppPreferences.setThemeMode(themeValues[position]) }

        val columnValues = listOf(2, 3)
        setSpinner(
            gridColumnsSpinner,
            listOf(getString(R.string.two_columns), getString(R.string.three_columns)),
            columnValues.indexOf(customization.gridColumns)
        ) { position -> AppPreferences.setGridColumns(columnValues[position]) }

        val styleValues = listOf(
            LibraryItemStyle.FLAT,
            LibraryItemStyle.ROUNDED,
            LibraryItemStyle.COMPACT
        )
        setSpinner(
            itemStyleSpinner,
            listOf(
                getString(R.string.style_flat),
                getString(R.string.style_rounded),
                getString(R.string.style_compact)
            ),
            styleValues.indexOf(customization.itemStyle)
        ) { position -> AppPreferences.setItemStyle(styleValues[position]) }

        val sortValues = listOf(
            LibrarySortOrder.TITLE,
            LibrarySortOrder.ARTIST,
            LibrarySortOrder.DATE_ADDED,
            LibrarySortOrder.DURATION
        )
        setSpinner(
            sortOrderSpinner,
            listOf(
                getString(R.string.sort_title),
                getString(R.string.sort_artist),
                getString(R.string.sort_date_added),
                getString(R.string.sort_duration)
            ),
            sortValues.indexOf(customization.sortOrder)
        ) { position -> AppPreferences.setSortOrder(sortValues[position]) }

        val fonts = AppFont.entries
        setSpinner(
            appFontSpinner,
            fonts.map(AppFont::displayName),
            fonts.indexOf(customization.appFont)
        ) { position -> AppPreferences.setAppFont(fonts[position]) }
    }

    private fun setupAccentColors() {
        accentViews[Color.rgb(124, 77, 255)] = findViewById(R.id.accentPurple)
        accentViews[Color.rgb(63, 81, 181)] = findViewById(R.id.accentIndigo)
        accentViews[Color.rgb(30, 112, 230)] = findViewById(R.id.accentBlue)
        accentViews[Color.rgb(0, 151, 190)] = findViewById(R.id.accentCyan)
        accentViews[Color.rgb(22, 148, 93)] = findViewById(R.id.accentGreen)
        accentViews[Color.rgb(230, 109, 0)] = findViewById(R.id.accentOrange)
        accentViews[Color.rgb(215, 56, 122)] = findViewById(R.id.accentPink)
        accentViews[Color.rgb(211, 54, 54)] = findViewById(R.id.accentRed)

        accentViews.forEach { (color, view) ->
            view.isClickable = true
            view.isFocusable = true
            view.setOnClickListener { AppPreferences.setAccentColor(color) }
        }

        selectedCustomColor = customization.accentColor
        customColorPicker.setColor(selectedCustomColor)
        updateCustomColorReadout(selectedCustomColor)
        customColorPicker.setOnColorChangedListener { color ->
            selectedCustomColor = color
            updateCustomColorReadout(color)
        }
        applyCustomColorButton.setOnClickListener {
            AppPreferences.setAccentColor(selectedCustomColor)
        }
    }

    private fun setupPermissionControls() {
        permissionButton.setOnClickListener {
            if (Settings.canDrawOverlays(this)) {
                Toast.makeText(this, R.string.overlay_permission_granted, Toast.LENGTH_SHORT).show()
            } else {
                val intent = Intent(
                    Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                    Uri.parse("package:$packageName")
                )
                try {
                    startActivity(intent)
                } catch (_: ActivityNotFoundException) {
                    startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION))
                }
            }
        }
    }

    private fun setupOverlayFontSize() {
        val initialSize = AppPreferences.overlayFontSize()
        fontSizeSeekBar.max = (
            AppPreferences.MAX_OVERLAY_FONT_SIZE - AppPreferences.MIN_OVERLAY_FONT_SIZE
        ).toInt()
        fontSizeSeekBar.progress = (initialSize - AppPreferences.MIN_OVERLAY_FONT_SIZE).toInt()
        fontSizeValue.text = getString(R.string.font_size_value, initialSize.toInt())

        fontSizeSeekBar.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                val size = AppPreferences.MIN_OVERLAY_FONT_SIZE + progress
                fontSizeValue.text = getString(R.string.font_size_value, size.toInt())
                previewText.textSize = size
                if (fromUser) AppPreferences.setOverlayFontSize(size)
            }

            override fun onStartTrackingTouch(seekBar: SeekBar?) = Unit
            override fun onStopTrackingTouch(seekBar: SeekBar?) = Unit
        })
    }

    private fun setupOverlayFontStyle() {
        setSpinner(
            fontStyleSpinner,
            listOf(
                "Bold Sans",
                "Regular Sans",
                "Serif",
                "Monospace",
                "Hind Siliguri · বাংলা",
                "Hind Siliguri Medium · বাংলা",
                "Hind Siliguri Bold · বাংলা",
                "Atma · বাংলা",
                "Atma Medium · বাংলা"
            ),
            overlayFontValues.indexOf(AppPreferences.overlayFontStyle()).coerceAtLeast(0)
        ) { position -> AppPreferences.setOverlayFontStyle(overlayFontValues[position]) }
    }

    private fun setupOverlayColorPalette() {
        overlayColorViews[Color.WHITE] = findViewById(R.id.colorWhite)
        overlayColorViews[Color.rgb(190, 167, 255)] = findViewById(R.id.colorPurple)
        overlayColorViews[Color.rgb(112, 216, 255)] = findViewById(R.id.colorBlue)
        overlayColorViews[Color.rgb(255, 145, 199)] = findViewById(R.id.colorPink)
        overlayColorViews[Color.rgb(111, 227, 180)] = findViewById(R.id.colorGreen)

        selectedOverlayColor = AppPreferences.overlayTextColor()
        overlayColorViews.forEach { (color, view) ->
            view.isClickable = true
            view.isFocusable = true
            view.setOnClickListener { AppPreferences.setOverlayTextColor(color) }
        }
        updateOverlayColorPalette()
    }

    private fun setupOverlayAnimationStyle() {
        setSpinner(
            animationSpinner,
            listOf("Soft fade", "Focus zoom", "Side glide", "Gentle rise", "Elastic pop", "3D flip", "Instant"),
            overlayAnimationValues.indexOf(AppPreferences.overlayAnimation()).coerceAtLeast(0)
        ) { position ->
            AppPreferences.setOverlayAnimation(overlayAnimationValues[position])
            animateOverlayPreview(overlayAnimationValues[position])
        }
    }

    private fun setupResetPosition() {
        findViewById<View>(R.id.resetPositionButton).setOnClickListener {
            AppPreferences.resetOverlayPosition()
            Toast.makeText(this, R.string.overlay_position_reset, Toast.LENGTH_SHORT).show()
        }
    }

    private fun setSpinner(
        spinner: Spinner,
        labels: List<String>,
        selectedPosition: Int,
        onSelected: (Int) -> Unit
    ) {
        val adapter = ThemedSpinnerAdapter(this, labels)
        spinnerAdapters += adapter
        spinner.adapter = adapter
        spinner.setSelection(selectedPosition.coerceAtLeast(0), false)
        spinner.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                onSelected(position)
            }

            override fun onNothingSelected(parent: AdapterView<*>?) = Unit
        }
    }

    private fun refreshAllControls() {
        refreshLibraryControls()
        refreshOverlayControls("initial")
        refreshPermissionState()
    }

    private fun refreshLibraryControls() {
        themeModeSpinner.setSelection(
            listOf(AppThemeMode.SYSTEM, AppThemeMode.LIGHT, AppThemeMode.DARK)
                .indexOf(customization.themeMode),
            false
        )
        gridColumnsSpinner.setSelection(if (customization.gridColumns == 3) 1 else 0, false)
        itemStyleSpinner.setSelection(customization.itemStyle.ordinal, false)
        sortOrderSpinner.setSelection(customization.sortOrder.ordinal, false)
        appFontSpinner.setSelection(AppFont.entries.indexOf(customization.appFont), false)
        updateAccentPalette()
        if (customColorPicker.selectedColor() != customization.accentColor &&
            customization.accentColor in accentViews.keys
        ) {
            selectedCustomColor = customization.accentColor
            customColorPicker.setColor(selectedCustomColor)
            updateCustomColorReadout(selectedCustomColor)
        }
        accentCard.setStrokeColor(customization.accentColor)
    }

    private fun refreshOverlayControls(changedKey: String) {
        val size = AppPreferences.overlayFontSize()
        if (!fontSizeSeekBar.isPressed) {
            fontSizeSeekBar.progress = (size - AppPreferences.MIN_OVERLAY_FONT_SIZE).toInt()
        }
        fontSizeValue.text = getString(R.string.font_size_value, size.toInt())
        fontStyleSpinner.setSelection(
            overlayFontValues.indexOf(AppPreferences.overlayFontStyle()).coerceAtLeast(0),
            false
        )
        animationSpinner.setSelection(
            overlayAnimationValues.indexOf(AppPreferences.overlayAnimation()).coerceAtLeast(0),
            false
        )
        selectedOverlayColor = AppPreferences.overlayTextColor()
        updateOverlayColorPalette()
        applyOverlayPreview()
        if (changedKey == AppPreferences.KEY_OVERLAY_ANIMATION) {
            animateOverlayPreview(AppPreferences.overlayAnimation())
        }
    }

    private fun updateAccentPalette() {
        val selectedStroke = customization.accentColor
        accentViews.forEach { (color, view) ->
            view.background = circleDrawable(
                color,
                if (color == customization.accentColor) 4 else 1,
                if (color == customization.accentColor) selectedStroke else Color.GRAY
            )
            view.alpha = if (color == customization.accentColor) 1f else 0.72f
            view.scaleX = if (color == customization.accentColor) 1.1f else 1f
            view.scaleY = if (color == customization.accentColor) 1.1f else 1f
        }
    }

    private fun updateOverlayColorPalette() {
        overlayColorViews.forEach { (color, view) ->
            view.background = circleDrawable(
                color,
                if (color == selectedOverlayColor) 3 else 1,
                if (color == selectedOverlayColor) customization.accentColor else Color.DKGRAY
            )
            view.alpha = if (color == selectedOverlayColor) 1f else 0.68f
            view.scaleX = if (color == selectedOverlayColor) 1.08f else 1f
            view.scaleY = if (color == selectedOverlayColor) 1.08f else 1f
        }
    }

    private fun updateCustomColorReadout(color: Int) {
        customColorHex.text = String.format(
            LocaleHolder.LOCALE,
            "#%02X%02X%02X",
            Color.red(color),
            Color.green(color),
            Color.blue(color)
        )
        applyCustomColorButton.backgroundTintList = android.content.res.ColorStateList.valueOf(color)
        applyCustomColorButton.setTextColor(AppUi.contrastTextColor(color))
    }

    private fun applyOverlayPreview() {
        previewText.textSize = AppPreferences.overlayFontSize()
        previewText.setTextColor(AppPreferences.overlayTextColor())
        previewText.typeface = when (AppPreferences.overlayFontStyle()) {
            AppPreferences.OVERLAY_FONT_REGULAR -> Typeface.create(Typeface.SANS_SERIF, Typeface.NORMAL)
            AppPreferences.OVERLAY_FONT_SERIF -> Typeface.create(Typeface.SERIF, Typeface.BOLD)
            AppPreferences.OVERLAY_FONT_MONOSPACE -> Typeface.create(Typeface.MONOSPACE, Typeface.BOLD)
            AppPreferences.OVERLAY_FONT_HIND_SILIGURI -> previewTypeface(R.font.hind_siliguri_regular)
            AppPreferences.OVERLAY_FONT_HIND_SILIGURI_MEDIUM -> previewTypeface(R.font.hind_siliguri_medium)
            AppPreferences.OVERLAY_FONT_HIND_SILIGURI_BOLD -> previewTypeface(R.font.hind_siliguri_bold)
            AppPreferences.OVERLAY_FONT_ATMA -> previewTypeface(R.font.atma_regular)
            AppPreferences.OVERLAY_FONT_ATMA_MEDIUM -> previewTypeface(R.font.atma_medium)
            else -> Typeface.create(Typeface.SANS_SERIF, Typeface.BOLD)
        }
    }

    private fun previewTypeface(fontResource: Int): Typeface =
        ResourcesCompat.getFont(this, fontResource) ?: Typeface.DEFAULT_BOLD

    private fun animateOverlayPreview(style: String) {
        previewText.animate().cancel()
        previewText.translationX = 0f
        previewText.translationY = 0f
        previewText.rotationX = 0f
        previewText.scaleX = 1f
        previewText.scaleY = 1f
        if (style == AppPreferences.OVERLAY_ANIMATION_NONE) {
            previewText.alpha = 1f
            return
        }

        previewText.alpha = 0.18f
        when (style) {
            AppPreferences.OVERLAY_ANIMATION_SLIDE -> previewText.translationX = dp(28).toFloat()
            AppPreferences.OVERLAY_ANIMATION_RISE -> previewText.translationY = dp(18).toFloat()
            AppPreferences.OVERLAY_ANIMATION_POP -> {
                previewText.scaleX = 0.58f
                previewText.scaleY = 0.58f
            }
            AppPreferences.OVERLAY_ANIMATION_FLIP -> {
                previewText.rotationX = 72f
                previewText.scaleY = 0.9f
            }
            AppPreferences.OVERLAY_ANIMATION_SCALE -> {
                previewText.scaleX = 0.82f
                previewText.scaleY = 0.82f
            }
            AppPreferences.OVERLAY_ANIMATION_FADE -> {
                previewText.scaleX = 0.98f
                previewText.scaleY = 0.98f
            }
        }
        previewText.animate()
            .alpha(1f)
            .translationX(0f)
            .translationY(0f)
            .rotationX(0f)
            .scaleX(1f)
            .scaleY(1f)
            .setDuration(if (style == AppPreferences.OVERLAY_ANIMATION_POP) 420L else 340L)
            .setInterpolator(
                if (style == AppPreferences.OVERLAY_ANIMATION_POP) {
                    OvershootInterpolator(1.3f)
                } else {
                    DecelerateInterpolator(1.5f)
                }
            )
            .start()
    }

    private fun refreshPermissionState() {
        val granted = Settings.canDrawOverlays(this)
        permissionStatus.setText(
            if (granted) R.string.overlay_permission_granted
            else R.string.overlay_permission_description
        )
        permissionStatus.setTextColor(
            ContextCompat.getColor(this, if (granted) R.color.success else R.color.text_secondary)
        )
        permissionButton.setText(
            if (granted) R.string.overlay_permission_granted
            else R.string.open_overlay_permission
        )
        permissionButton.alpha = if (granted) 0.82f else 1f
    }

    private fun circleDrawable(color: Int, strokeDp: Int, strokeColor: Int): GradientDrawable =
        GradientDrawable().apply {
            shape = GradientDrawable.OVAL
            setColor(color)
            setStroke(dp(strokeDp), strokeColor)
        }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    private inner class ThemedSpinnerAdapter(
        context: Context,
        labels: List<String>
    ) : ArrayAdapter<String>(context, android.R.layout.simple_spinner_item, labels) {
        init {
            setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        }

        override fun getView(position: Int, convertView: View?, parent: ViewGroup): View =
            style(super.getView(position, convertView, parent))

        override fun getDropDownView(position: Int, convertView: View?, parent: ViewGroup): View =
            style(super.getDropDownView(position, convertView, parent))

        private fun style(view: View): View {
            if (view is TextView) {
                view.setTypeface(AppUi.typeface(view, customization.appFont), Typeface.NORMAL)
                view.setTextColor(ContextCompat.getColor(this@SettingsActivity, R.color.text_primary))
            }
            return view
        }
    }

    private object LocaleHolder {
        val LOCALE: java.util.Locale = java.util.Locale.US
    }
}
