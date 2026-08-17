package com.ahad.lyricsoverlay

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat

/**
 * Keeps a user-started online lookup/upload eligible to continue when its Activity closes and
 * exposes cancellable progress through Android's required foreground data-sync notification.
 */
class OnDeviceAiService : Service(), OnDeviceAiLyricsManager.Listener {

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        startForeground(NOTIFICATION_ID, buildNotification(OnDeviceAiLyricsManager.currentState()))
        OnDeviceAiLyricsManager.addListener(this)
        OnDeviceAiLyricsManager.restorePending(applicationContext)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_CANCEL) {
            OnDeviceAiLyricsManager.cancel()
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
            return START_NOT_STICKY
        }
        val current = OnDeviceAiLyricsManager.currentState()
        if (!current.isRunning) {
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
            return START_NOT_STICKY
        }
        updateNotification(current)
        return START_STICKY
    }

    override fun onDestroy() {
        OnDeviceAiLyricsManager.removeListener(this)
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onAiLyricsJobChanged(state: AiLyricsJobState) {
        if (state.isRunning) {
            updateNotification(state)
        } else {
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
        }
    }

    private fun updateNotification(state: AiLyricsJobState) {
        getSystemService(NotificationManager::class.java)
            .notify(NOTIFICATION_ID, buildNotification(state))
    }

    private fun buildNotification(state: AiLyricsJobState) =
        NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_ai_mic)
            .setContentTitle(getString(R.string.ai_background_notification_title))
            .setContentText(state.message ?: getString(R.string.ai_background_notification_text))
            .setContentIntent(
                PendingIntent.getActivity(
                    this,
                    0,
                    Intent(this, LyricsActivity::class.java)
                        .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP),
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
                )
            )
            .addAction(
                android.R.drawable.ic_menu_close_clear_cancel,
                getString(android.R.string.cancel),
                PendingIntent.getService(
                    this,
                    1,
                    Intent(this, OnDeviceAiService::class.java).setAction(ACTION_CANCEL),
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
                )
            )
            .setOnlyAlertOnce(true)
            .setOngoing(true)
            .setCategory(NotificationCompat.CATEGORY_PROGRESS)
            .setProgress(100, state.progress.coerceIn(0, 100), false)
            .build()

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val channel = NotificationChannel(
            CHANNEL_ID,
            getString(R.string.ai_background_channel_name),
            NotificationManager.IMPORTANCE_LOW
        ).apply {
            description = getString(R.string.ai_background_channel_description)
            setShowBadge(false)
        }
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    companion object {
        private const val ACTION_MONITOR = "com.ahad.lyricsoverlay.ai.MONITOR"
        private const val ACTION_CANCEL = "com.ahad.lyricsoverlay.ai.CANCEL"
        private const val CHANNEL_ID = "on_device_lyrics"
        private const val NOTIFICATION_ID = 4110

        fun ensureRunning(context: Context) {
            val intent = Intent(context, OnDeviceAiService::class.java).setAction(ACTION_MONITOR)
            try {
                ContextCompat.startForegroundService(context, intent)
            } catch (_: Exception) {
                // The in-process request can still finish if this Android build blocks FGS start.
            }
        }
    }
}
