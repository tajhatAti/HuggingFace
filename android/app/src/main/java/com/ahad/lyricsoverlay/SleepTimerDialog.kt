package com.ahad.lyricsoverlay

import android.content.res.ColorStateList
import android.os.Handler
import android.os.Looper
import android.view.LayoutInflater
import android.view.View
import android.widget.ImageView
import android.widget.TextView
import android.widget.Toast
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.android.material.textfield.TextInputEditText
import com.google.android.material.textfield.TextInputLayout

/** Shared, fully functional sleep-timer picker used by the player and Lyrics Center. */
object SleepTimerDialog {

    fun show(activity: androidx.appcompat.app.AppCompatActivity, service: PlayerService?) {
        if (service == null) {
            Toast.makeText(activity, R.string.no_song_for_lyrics, Toast.LENGTH_SHORT).show()
            return
        }
        val view = LayoutInflater.from(activity).inflate(R.layout.dialog_sleep_timer, null, false)
        val status: TextView = view.findViewById(R.id.sleepTimerDialogStatus)
        val icon: ImageView = view.findViewById(R.id.sleepTimerDialogIcon)
        val customLayout: TextInputLayout = view.findViewById(R.id.customSleepInputLayout)
        val customMinutes: TextInputEditText = view.findViewById(R.id.customSleepMinutes)
        val cancelButton: View = view.findViewById(R.id.cancelSleepTimerButton)
        val customization = AppPreferences.snapshot()
        val accent = customization.accentColor
        AppUi.applyTypeface(view, customization.appFont)
        icon.imageTintList = ColorStateList.valueOf(accent)
        view.findViewById<com.google.android.material.button.MaterialButton>(R.id.setCustomSleepButton).apply {
            backgroundTintList = ColorStateList.valueOf(accent)
            setTextColor(AppUi.contrastTextColor(accent))
            iconTint = ColorStateList.valueOf(AppUi.contrastTextColor(accent))
        }
        listOf(
            R.id.sleep15Button,
            R.id.sleep30Button,
            R.id.sleep45Button,
            R.id.sleep60Button,
            R.id.sleepAfterSongButton,
            R.id.cancelSleepTimerButton
        ).forEach { id ->
            view.findViewById<com.google.android.material.button.MaterialButton>(id).apply {
                setTextColor(accent)
                iconTint = ColorStateList.valueOf(accent)
            }
        }

        val dialog = MaterialAlertDialogBuilder(activity)
            .setView(view)
            .setNegativeButton(R.string.close, null)
            .create()
        val handler = Handler(Looper.getMainLooper())

        fun updateStatus() {
            val afterSong = service.sleepsAfterCurrentSong()
            val endAt = service.sleepTimerEndAtMs()
            status.text = when {
                afterSong -> activity.getString(R.string.sleep_end_of_song)
                endAt > System.currentTimeMillis() -> activity.getString(
                    R.string.sleep_timer_remaining,
                    MusicScannerUtil.formatDuration(endAt - System.currentTimeMillis())
                )
                else -> activity.getString(R.string.sleep_timer_off)
            }
            cancelButton.visibility = if (afterSong || endAt > 0L) View.VISIBLE else View.GONE
        }

        fun setMinutes(minutes: Int) {
            if (!service.setSleepTimerMinutes(minutes)) return
            customLayout.error = null
            updateStatus()
            icon.animate().cancel()
            icon.rotation = -16f
            icon.animate().rotation(0f).scaleX(1.12f).scaleY(1.12f).setDuration(180L)
                .withEndAction {
                    icon.animate().scaleX(1f).scaleY(1f).setDuration(140L).start()
                }.start()
            Toast.makeText(
                activity,
                activity.getString(R.string.sleep_timer_set, minutes),
                Toast.LENGTH_SHORT
            ).show()
        }

        view.findViewById<View>(R.id.sleep15Button).setOnClickListener { setMinutes(15) }
        view.findViewById<View>(R.id.sleep30Button).setOnClickListener { setMinutes(30) }
        view.findViewById<View>(R.id.sleep45Button).setOnClickListener { setMinutes(45) }
        view.findViewById<View>(R.id.sleep60Button).setOnClickListener { setMinutes(60) }
        view.findViewById<View>(R.id.setCustomSleepButton).setOnClickListener {
            val minutes = customMinutes.text?.toString()?.trim()?.toIntOrNull()
            if (minutes == null || minutes !in 1..720) {
                customLayout.error = activity.getString(R.string.invalid_sleep_minutes)
            } else {
                setMinutes(minutes)
            }
        }
        view.findViewById<View>(R.id.sleepAfterSongButton).setOnClickListener {
            if (service.setSleepAfterCurrentSong()) {
                updateStatus()
                Toast.makeText(activity, R.string.sleep_timer_end_song_set, Toast.LENGTH_SHORT).show()
            } else {
                Toast.makeText(activity, R.string.no_song_for_lyrics, Toast.LENGTH_SHORT).show()
            }
        }
        cancelButton.setOnClickListener {
            service.cancelSleepTimer()
            updateStatus()
            Toast.makeText(activity, R.string.sleep_timer_cancelled, Toast.LENGTH_SHORT).show()
        }

        val ticker = object : Runnable {
            override fun run() {
                if (!dialog.isShowing) return
                updateStatus()
                handler.postDelayed(this, 1_000L)
            }
        }
        dialog.setOnShowListener {
            updateStatus()
            handler.post(ticker)
        }
        dialog.setOnDismissListener { handler.removeCallbacks(ticker) }
        dialog.show()
    }
}
