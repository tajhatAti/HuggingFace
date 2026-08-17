package com.ahad.lyricsoverlay

import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.Typeface
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.TextView
import androidx.core.content.ContextCompat
import androidx.core.graphics.ColorUtils
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.card.MaterialCardView
import com.google.android.material.color.MaterialColors

class QueueSongAdapter(
    private val onSongClicked: (Int) -> Unit
) : ListAdapter<Song, QueueSongAdapter.QueueViewHolder>(SONG_DIFF) {

    private var currentIndex = RecyclerView.NO_POSITION
    private var customization = AppPreferences.snapshot()

    init {
        setHasStableIds(true)
    }

    fun updateQueue(songs: List<Song>, playingIndex: Int) {
        val previousIndex = currentIndex
        currentIndex = playingIndex
        submitList(songs.toList()) {
            notifySelectionChange(previousIndex, currentIndex)
        }
    }

    fun setCurrentIndex(index: Int) {
        if (index == currentIndex) return
        val previous = currentIndex
        currentIndex = index
        notifySelectionChange(previous, index)
    }

    fun updateConfiguration(snapshot: CustomizationSnapshot) {
        if (snapshot == customization) return
        customization = snapshot
        if (itemCount > 0) notifyItemRangeChanged(0, itemCount, PAYLOAD_APPEARANCE)
    }

    override fun getItemId(position: Int): Long = getItem(position).id

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): QueueViewHolder {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_queue_song, parent, false) as MaterialCardView
        return QueueViewHolder(view)
    }

    override fun onBindViewHolder(holder: QueueViewHolder, position: Int) {
        holder.bind(getItem(position), position)
    }

    override fun onBindViewHolder(
        holder: QueueViewHolder,
        position: Int,
        payloads: MutableList<Any>
    ) {
        holder.bind(getItem(position), position)
    }

    private fun notifySelectionChange(previous: Int, current: Int) {
        if (previous in 0 until itemCount) notifyItemChanged(previous, PAYLOAD_SELECTION)
        if (current in 0 until itemCount) notifyItemChanged(current, PAYLOAD_SELECTION)
    }

    inner class QueueViewHolder(
        private val card: MaterialCardView
    ) : RecyclerView.ViewHolder(card) {
        private val number: TextView = card.findViewById(R.id.queueSongNumber)
        private val playingIcon: ImageView = card.findViewById(R.id.queuePlayingIcon)
        private val title: TextView = card.findViewById(R.id.queueSongTitle)
        private val artist: TextView = card.findViewById(R.id.queueSongArtist)
        private val duration: TextView = card.findViewById(R.id.queueSongDuration)

        fun bind(song: Song, position: Int) {
            val isCurrent = position == currentIndex
            val typeface = AppUi.typeface(card, customization.appFont)
            number.text = (position + 1).toString()
            number.visibility = if (isCurrent) View.GONE else View.VISIBLE
            playingIcon.visibility = if (isCurrent) View.VISIBLE else View.GONE
            playingIcon.imageTintList = ColorStateList.valueOf(customization.accentColor)
            title.text = song.title
            artist.text = song.artist
            duration.text = MusicScannerUtil.formatDuration(song.durationMs)
            title.setTypeface(typeface, Typeface.BOLD)
            artist.setTypeface(typeface, Typeface.NORMAL)
            duration.setTypeface(typeface, Typeface.NORMAL)
            number.setTypeface(typeface, Typeface.BOLD)
            applyAppearance(isCurrent)

            card.contentDescription = card.context.getString(
                if (isCurrent) R.string.queue_current_song_description
                else R.string.queue_song_description,
                song.title,
                song.artist
            )
            card.setOnClickListener {
                val adapterPosition = bindingAdapterPosition
                if (adapterPosition != RecyclerView.NO_POSITION) onSongClicked(adapterPosition)
            }
        }

        private fun applyAppearance(isCurrent: Boolean) {
            val surface = MaterialColors.getColor(
                card,
                com.google.android.material.R.attr.colorSurface,
                Color.TRANSPARENT
            )
            card.setCardBackgroundColor(
                if (isCurrent) ColorUtils.blendARGB(surface, customization.accentColor, 0.16f)
                else Color.TRANSPARENT
            )
            card.setStrokeColor(
                if (isCurrent) ColorUtils.setAlphaComponent(customization.accentColor, 170)
                else Color.TRANSPARENT
            )
            card.strokeWidth = if (isCurrent) dp(1f) else 0
            card.rippleColor = ColorStateList.valueOf(
                ColorUtils.setAlphaComponent(customization.accentColor, 45)
            )
            title.setTextColor(
                if (isCurrent) customization.accentColor
                else ContextCompat.getColor(card.context, R.color.text_primary)
            )
        }

        private fun dp(value: Float): Int =
            (value * card.resources.displayMetrics.density).toInt().coerceAtLeast(1)
    }

    companion object {
        private const val PAYLOAD_SELECTION = "selection"
        private const val PAYLOAD_APPEARANCE = "appearance"

        private val SONG_DIFF = object : DiffUtil.ItemCallback<Song>() {
            override fun areItemsTheSame(oldItem: Song, newItem: Song): Boolean =
                oldItem.id == newItem.id

            override fun areContentsTheSame(oldItem: Song, newItem: Song): Boolean =
                oldItem == newItem
        }
    }
}
