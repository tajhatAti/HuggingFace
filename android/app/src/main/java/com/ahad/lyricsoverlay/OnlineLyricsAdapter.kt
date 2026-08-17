package com.ahad.lyricsoverlay

import android.content.res.ColorStateList
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.TextView
import androidx.core.content.res.ResourcesCompat
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.button.MaterialButton
import kotlin.math.roundToLong

class OnlineLyricsAdapter(
    private val onUseClicked: (OnlineLyricsCandidate) -> Unit
) : ListAdapter<OnlineLyricsCandidate, OnlineLyricsAdapter.ResultViewHolder>(DIFF_CALLBACK) {

    private var customization = AppPreferences.snapshot()

    init {
        setHasStableIds(true)
    }

    fun updateConfiguration(snapshot: CustomizationSnapshot) {
        customization = snapshot
        notifyItemRangeChanged(0, itemCount)
    }

    override fun getItemId(position: Int): Long = getItem(position).id

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ResultViewHolder {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_online_lyrics, parent, false)
        return ResultViewHolder(view)
    }

    override fun onBindViewHolder(holder: ResultViewHolder, position: Int) {
        holder.bind(getItem(position))
    }

    inner class ResultViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
        private val icon: ImageView = itemView.findViewById(R.id.onlineLyricsIcon)
        private val title: TextView = itemView.findViewById(R.id.onlineLyricsTitle)
        private val artist: TextView = itemView.findViewById(R.id.onlineLyricsArtist)
        private val details: TextView = itemView.findViewById(R.id.onlineLyricsDetails)
        private val useButton: MaterialButton = itemView.findViewById(R.id.useOnlineLyricsButton)

        fun bind(candidate: OnlineLyricsCandidate) {
            val context = itemView.context
            title.text = candidate.trackName
            artist.text = candidate.artistName
            details.text = context.getString(
                R.string.online_lyrics_result_details,
                candidate.albumName.ifBlank { context.getString(R.string.unknown_album) },
                MusicScannerUtil.formatDuration(candidate.durationSeconds.roundToLong() * 1_000L)
            )
            val typeface = ResourcesCompat.getFont(context, customization.appFont.resourceId)
            title.typeface = typeface
            artist.typeface = typeface
            details.typeface = typeface
            useButton.typeface = typeface
            icon.imageTintList = ColorStateList.valueOf(customization.accentColor)
            useButton.setTextColor(customization.accentColor)
            useButton.iconTint = ColorStateList.valueOf(customization.accentColor)
            itemView.setOnClickListener { onUseClicked(candidate) }
            useButton.setOnClickListener { onUseClicked(candidate) }
        }
    }

    companion object {
        private val DIFF_CALLBACK = object : DiffUtil.ItemCallback<OnlineLyricsCandidate>() {
            override fun areItemsTheSame(oldItem: OnlineLyricsCandidate, newItem: OnlineLyricsCandidate): Boolean =
                oldItem.id == newItem.id

            override fun areContentsTheSame(oldItem: OnlineLyricsCandidate, newItem: OnlineLyricsCandidate): Boolean =
                oldItem == newItem
        }
    }
}
