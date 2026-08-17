package com.ahad.lyricsoverlay

import android.app.Activity
import android.content.res.ColorStateList
import android.content.res.Configuration
import android.graphics.Color
import android.graphics.Typeface
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.ImageButton
import android.widget.ProgressBar
import android.widget.SeekBar
import android.widget.TextView
import androidx.core.content.ContextCompat
import androidx.core.content.res.ResourcesCompat
import androidx.core.graphics.ColorUtils
import androidx.core.view.WindowInsetsControllerCompat
import com.google.android.material.button.MaterialButton
import com.google.android.material.card.MaterialCardView

object AppUi {

    fun apply(activity: Activity, root: View, snapshot: CustomizationSnapshot) {
        applySystemBars(activity)
        applyTypeface(root, snapshot.appFont)
        applyAccent(root, snapshot.accentColor)
    }

    fun typeface(view: View, appFont: AppFont): Typeface =
        ResourcesCompat.getFont(view.context, appFont.resourceId) ?: Typeface.DEFAULT

    fun applyTypeface(root: View, appFont: AppFont) {
        val selectedTypeface = typeface(root, appFont)
        walk(root) { view ->
            if (view is TextView) {
                val existingStyle = view.typeface?.style ?: Typeface.NORMAL
                view.setTypeface(selectedTypeface, existingStyle)
            }
        }
    }

    fun applyAccent(root: View, accentColor: Int) {
        val accent = ColorStateList.valueOf(accentColor)
        val onAccent = ColorStateList.valueOf(contrastTextColor(accentColor))
        walk(root) { view ->
            when (view) {
                is SeekBar -> {
                    view.progressTintList = accent
                    view.thumbTintList = accent
                }
                is ProgressBar -> view.progressTintList = accent
                is MaterialButton -> {
                    view.backgroundTintList = accent
                    view.setTextColor(onAccent)
                    view.iconTint = onAccent
                    view.rippleColor = ColorStateList.valueOf(
                        ColorUtils.setAlphaComponent(contrastTextColor(accentColor), 55)
                    )
                }
                is Button -> {
                    view.backgroundTintList = accent
                    view.setTextColor(onAccent)
                }
                is ImageButton -> {
                    view.imageTintList = accent
                    if (view.id == R.id.playPauseButton) {
                        view.backgroundTintList = accent
                        view.imageTintList = onAccent
                    }
                }
            }

            if (view is MaterialCardView && view.id == R.id.miniPlayer) {
                view.strokeWidth = dp(view, 1f)
                view.setStrokeColor(ColorUtils.setAlphaComponent(accentColor, 150))
            }
        }
    }

    fun applySystemBars(activity: Activity) {
        val background = ContextCompat.getColor(activity, R.color.background)
        activity.window.statusBarColor = background
        activity.window.navigationBarColor = background
        val isNight = activity.resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK ==
            Configuration.UI_MODE_NIGHT_YES
        WindowInsetsControllerCompat(activity.window, activity.window.decorView).apply {
            isAppearanceLightStatusBars = !isNight
            isAppearanceLightNavigationBars = !isNight
        }
    }

    fun contrastTextColor(backgroundColor: Int): Int =
        if (ColorUtils.calculateLuminance(backgroundColor) > 0.48) Color.BLACK else Color.WHITE

    private fun walk(root: View, action: (View) -> Unit) {
        action(root)
        if (root is ViewGroup) {
            for (index in 0 until root.childCount) {
                walk(root.getChildAt(index), action)
            }
        }
    }

    private fun dp(view: View, value: Float): Int =
        (value * view.resources.displayMetrics.density).toInt().coerceAtLeast(1)
}
