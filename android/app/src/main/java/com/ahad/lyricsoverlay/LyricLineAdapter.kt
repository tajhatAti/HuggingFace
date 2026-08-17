package com.ahad.lyricsoverlay

import android.content.res.ColorStateList
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.core.content.ContextCompat
import androidx.core.content.res.ResourcesCompat
import androidx.recyclerview.widget.RecyclerView

class LyricLineAdapter(
    private val onLineClicked: (LrcLine) -> Unit
) : RecyclerView.Adapter<LyricLineAdapter.LineViewHolder>() {

    private var lines: List<LrcLine> = emptyList()
    private var activeIndex = -1
    private var accentColor = AppPreferences.DEFAULT_ACCENT_COLOR
    private var appFont = AppFont.ROBOTO

    init {
        setHasStableIds(true)
    }

    fun updateLines(newLines: List<LrcLine>) {
        lines = newLines
        activeIndex = -1
        notifyDataSetChanged()
    }

    fun setActiveIndex(newIndex: Int): Boolean {
        val safeIndex = newIndex.takeIf { it in lines.indices } ?: -1
        if (safeIndex == activeIndex) return false
        val oldIndex = activeIndex
        activeIndex = safeIndex
        if (oldIndex in lines.indices) notifyItemChanged(oldIndex, ACTIVE_PAYLOAD)
        if (safeIndex in lines.indices) notifyItemChanged(safeIndex, ACTIVE_PAYLOAD)
        return true
    }

    fun updateConfiguration(snapshot: CustomizationSnapshot) {
        accentColor = snapshot.accentColor
        appFont = snapshot.appFont
        notifyItemRangeChanged(0, itemCount, STYLE_PAYLOAD)
    }

    override fun getItemId(position: Int): Long =
        lines[position].timestampMs * 31L + lines[position].text.hashCode()

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): LineViewHolder {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_lyric_line, parent, false)
        return LineViewHolder(view)
    }

    override fun onBindViewHolder(holder: LineViewHolder, position: Int) {
        holder.bind(lines[position], position == activeIndex, animate = false)
    }

    override fun onBindViewHolder(holder: LineViewHolder, position: Int, payloads: MutableList<Any>) {
        if (payloads.isEmpty()) {
            onBindViewHolder(holder, position)
        } else {
            holder.bind(lines[position], position == activeIndex, animate = ACTIVE_PAYLOAD in payloads)
        }
    }

    override fun getItemCount(): Int = lines.size

    inner class LineViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
        private val timestamp: TextView = itemView.findViewById(R.id.lyricTimestamp)
        private val text: TextView = itemView.findViewById(R.id.lyricLineText)

        fun bind(line: LrcLine, active: Boolean, animate: Boolean) {
            timestamp.text = MusicScannerUtil.formatDuration(line.timestampMs)
            text.text = line.text
            val typeface = ResourcesCompat.getFont(itemView.context, appFont.resourceId)
            timestamp.typeface = typeface
            text.typeface = typeface
            text.setTextColor(
                if (active) accentColor
                else ContextCompat.getColor(itemView.context, R.color.text_secondary)
            )
            timestamp.setTextColor(
                if (active) accentColor
                else ContextCompat.getColor(itemView.context, R.color.text_muted)
            )
            itemView.backgroundTintList = if (active) {
                ColorStateList.valueOf((accentColor and 0x00ffffff) or 0x18000000)
            } else {
                null
            }
            itemView.animate().cancel()
            if (animate) {
                itemView.animate()
                    .alpha(if (active) 1f else 0.55f)
                    .scaleX(if (active) 1f else 0.96f)
                    .scaleY(if (active) 1f else 0.96f)
                    .setDuration(220L)
                    .start()
            } else {
                itemView.alpha = if (active) 1f else 0.55f
                itemView.scaleX = if (active) 1f else 0.96f
                itemView.scaleY = if (active) 1f else 0.96f
            }
            text.textSize = if (active) 24f else 18f
            itemView.setOnClickListener { onLineClicked(line) }
        }
    }

    companion object {
        private const val ACTIVE_PAYLOAD = "active"
        private const val STYLE_PAYLOAD = "style"
    }
}
