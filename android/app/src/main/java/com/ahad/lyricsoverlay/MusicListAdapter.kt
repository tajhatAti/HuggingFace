package com.ahad.lyricsoverlay

import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.graphics.Typeface
import android.media.MediaMetadataRetriever
import android.os.Handler
import android.os.Looper
import android.util.LruCache
import android.view.LayoutInflater
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.TextView
import androidx.core.graphics.ColorUtils
import androidx.recyclerview.widget.AsyncListDiffer
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.card.MaterialCardView
import com.google.android.material.color.MaterialColors
import java.util.concurrent.Executors

class MusicListAdapter(
    private val context: Context,
    private val onSongClicked: (Song) -> Unit,
    private val onSongLongClicked: (Song) -> Unit
) : RecyclerView.Adapter<MusicListAdapter.SongViewHolder>() {

    private val differ = AsyncListDiffer(this, SONG_DIFF)
    private val songs: List<Song>
        get() = differ.currentList
    private val artworkExecutor = Executors.newFixedThreadPool(2)
    private val mainHandler = Handler(Looper.getMainLooper())
    private var playingSongId: Long? = null
    private var configuration = AppPreferences.snapshot()
    private var selectedTypeface: Typeface = AppUi.typeface(
        android.view.View(context),
        configuration.appFont
    )

    private val artworkCache = object : LruCache<Long, Bitmap>(cacheSizeKb()) {
        override fun sizeOf(key: Long, value: Bitmap): Int = value.byteCount / 1024
    }

    init {
        setHasStableIds(true)
    }

    fun submitList(newSongs: List<Song>, onCommitted: (() -> Unit)? = null) {
        differ.submitList(newSongs.toList()) { onCommitted?.invoke() }
    }

    fun updateConfiguration(snapshot: CustomizationSnapshot) {
        if (configuration == snapshot) return
        val structureChanged = configuration.layoutMode != snapshot.layoutMode ||
            configuration.itemStyle != snapshot.itemStyle
        val appearanceChanged = configuration.accentColor != snapshot.accentColor ||
            configuration.appFont != snapshot.appFont
        configuration = snapshot
        selectedTypeface = AppUi.typeface(android.view.View(context), snapshot.appFont)
        when {
            structureChanged -> notifyDataSetChanged()
            appearanceChanged && itemCount > 0 -> notifyItemRangeChanged(0, itemCount, PAYLOAD_APPEARANCE)
        }
    }

    fun songIdAt(position: Int): Long? = songs.getOrNull(position)?.id

    fun setPlayingSong(songId: Long?) {
        val previousId = playingSongId
        playingSongId = songId
        if (previousId == songId) return
        songs.indexOfFirst { it.id == previousId }
            .takeIf { it >= 0 }
            ?.let { notifyItemChanged(it, PAYLOAD_SELECTION) }
        songs.indexOfFirst { it.id == songId }
            .takeIf { it >= 0 }
            ?.let { notifyItemChanged(it, PAYLOAD_SELECTION) }
    }

    fun loadArtworkInto(
        imageView: ImageView,
        song: Song,
        placeholderPaddingDp: Float? = null
    ) {
        imageView.tag = song.id
        artworkCache.get(song.id)?.let { bitmap ->
            showBitmap(imageView, bitmap)
            return
        }

        showPlaceholder(imageView, placeholderPaddingDp)
        artworkExecutor.execute {
            val bitmap = loadArtwork(song)
            if (bitmap != null) artworkCache.put(song.id, bitmap)
            mainHandler.post {
                if (imageView.tag == song.id) {
                    if (bitmap != null) {
                        showBitmap(imageView, bitmap)
                    } else {
                        showPlaceholder(imageView, placeholderPaddingDp)
                    }
                }
            }
        }
    }

    fun release() {
        artworkExecutor.shutdownNow()
        artworkCache.evictAll()
        mainHandler.removeCallbacksAndMessages(null)
    }

    override fun getItemId(position: Int): Long = songs[position].id

    override fun getItemViewType(position: Int): Int {
        val modeOffset = if (configuration.layoutMode == LibraryLayoutMode.GRID) 3 else 0
        return modeOffset + configuration.itemStyle.ordinal
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): SongViewHolder {
        val layout = when (viewType) {
            VIEW_LIST_FLAT -> R.layout.item_song_list_flat
            VIEW_LIST_ROUNDED -> R.layout.item_song_list_card
            VIEW_LIST_COMPACT -> R.layout.item_song_list_compact
            VIEW_GRID_FLAT -> R.layout.item_song_grid_flat
            VIEW_GRID_ROUNDED -> R.layout.item_song_grid_card
            VIEW_GRID_COMPACT -> R.layout.item_song_grid_compact
            else -> error("Unsupported song view type: $viewType")
        }
        val view = LayoutInflater.from(parent.context).inflate(layout, parent, false)
        return SongViewHolder(view as MaterialCardView)
    }

    override fun onBindViewHolder(holder: SongViewHolder, position: Int) {
        holder.bind(songs[position], loadArtwork = true)
    }

    override fun onBindViewHolder(
        holder: SongViewHolder,
        position: Int,
        payloads: MutableList<Any>
    ) {
        if (payloads.isEmpty()) {
            onBindViewHolder(holder, position)
        } else {
            holder.bind(songs[position], loadArtwork = false)
        }
    }

    override fun getItemCount(): Int = songs.size

    inner class SongViewHolder(private val card: MaterialCardView) : RecyclerView.ViewHolder(card) {
        private val albumArt: ImageView = card.findViewById(R.id.albumArt)
        private val title: TextView = card.findViewById(R.id.songTitle)
        private val artist: TextView = card.findViewById(R.id.songArtist)
        private val duration: TextView? = card.findViewById(R.id.songDuration)

        fun bind(song: Song, loadArtwork: Boolean) {
            title.text = song.title
            artist.text = song.artist
            duration?.text = MusicScannerUtil.formatDuration(song.durationMs)
            title.setTypeface(selectedTypeface, Typeface.BOLD)
            artist.setTypeface(selectedTypeface, Typeface.NORMAL)
            duration?.setTypeface(selectedTypeface, Typeface.NORMAL)
            if (loadArtwork || albumArt.tag != song.id) loadArtworkInto(albumArt, song)

            if (configuration.layoutMode == LibraryLayoutMode.GRID) {
                albumArt.post {
                    if (albumArt.width > 0 && albumArt.layoutParams.height != albumArt.width) {
                        albumArt.layoutParams = albumArt.layoutParams.apply { height = albumArt.width }
                    }
                }
            }

            applyCardAppearance(song.id == playingSongId)
            card.contentDescription = context.getString(
                R.string.song_item_description,
                song.title,
                song.artist
            )
            card.setOnClickListener {
                val position = bindingAdapterPosition
                if (position != RecyclerView.NO_POSITION) onSongClicked(songs[position])
            }
            card.setOnLongClickListener {
                val position = bindingAdapterPosition
                if (position == RecyclerView.NO_POSITION) {
                    false
                } else {
                    onSongLongClicked(songs[position])
                    true
                }
            }
        }

        private fun applyCardAppearance(selected: Boolean) {
            val accent = configuration.accentColor
            val surface = MaterialColors.getColor(
                card,
                com.google.android.material.R.attr.colorSurface,
                Color.TRANSPARENT
            )
            val normalBackground = if (configuration.itemStyle == LibraryItemStyle.FLAT) {
                Color.TRANSPARENT
            } else {
                surface
            }
            val selectedBackground = ColorUtils.blendARGB(surface, accent, 0.18f)
            card.setCardBackgroundColor(if (selected) selectedBackground else normalBackground)
            card.setStrokeColor(
                if (selected) accent else MaterialColors.getColor(
                    card,
                    com.google.android.material.R.attr.colorOutline,
                    ColorUtils.setAlphaComponent(accent, 45)
                )
            )
            card.strokeWidth = when {
                selected -> dp(2f)
                configuration.itemStyle == LibraryItemStyle.FLAT -> 0
                else -> dp(1f)
            }
            card.cardElevation = when (configuration.itemStyle) {
                LibraryItemStyle.FLAT -> 0f
                LibraryItemStyle.ROUNDED -> dpFloat(5f)
                LibraryItemStyle.COMPACT -> dpFloat(1f)
            }
            card.radius = when (configuration.itemStyle) {
                LibraryItemStyle.FLAT -> dpFloat(10f)
                LibraryItemStyle.ROUNDED -> dpFloat(18f)
                LibraryItemStyle.COMPACT -> dpFloat(8f)
            }
            card.rippleColor = ColorStateList.valueOf(ColorUtils.setAlphaComponent(accent, 55))
        }
    }

    private fun loadArtwork(song: Song): Bitmap? {
        song.albumArtUri?.let { uri ->
            decodeUri(uri.toString())?.let { return it }
        }

        return try {
            val retriever = MediaMetadataRetriever()
            try {
                retriever.setDataSource(context, song.contentUri)
                retriever.embeddedPicture?.let(::decodeByteArray)
            } finally {
                retriever.release()
            }
        } catch (_: Exception) {
            null
        }
    }

    private fun decodeUri(uriString: String): Bitmap? {
        val uri = android.net.Uri.parse(uriString)
        return try {
            val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            context.contentResolver.openInputStream(uri)?.use {
                BitmapFactory.decodeStream(it, null, bounds)
            }
            val options = BitmapFactory.Options().apply {
                inSampleSize = calculateSampleSize(bounds.outWidth, bounds.outHeight, 360)
            }
            context.contentResolver.openInputStream(uri)?.use {
                BitmapFactory.decodeStream(it, null, options)
            }
        } catch (_: Exception) {
            null
        }
    }

    private fun decodeByteArray(bytes: ByteArray): Bitmap? {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
        val options = BitmapFactory.Options().apply {
            inSampleSize = calculateSampleSize(bounds.outWidth, bounds.outHeight, 360)
        }
        return BitmapFactory.decodeByteArray(bytes, 0, bytes.size, options)
    }

    private fun calculateSampleSize(width: Int, height: Int, target: Int): Int {
        var sample = 1
        val halfWidth = width / 2
        val halfHeight = height / 2
        while (halfWidth / sample >= target && halfHeight / sample >= target) {
            sample *= 2
        }
        return sample.coerceAtLeast(1)
    }

    private fun showBitmap(imageView: ImageView, bitmap: Bitmap) {
        imageView.imageTintList = null
        imageView.setPadding(0, 0, 0, 0)
        imageView.scaleType = ImageView.ScaleType.CENTER_CROP
        imageView.setImageBitmap(bitmap)
    }

    private fun showPlaceholder(imageView: ImageView, paddingDp: Float? = null) {
        val padding = paddingDp?.let(::dp)
            ?: if (configuration.layoutMode == LibraryLayoutMode.GRID) dp(28f) else dp(11f)
        imageView.setPadding(padding, padding, padding, padding)
        imageView.scaleType = ImageView.ScaleType.CENTER_INSIDE
        imageView.imageTintList = ColorStateList.valueOf(configuration.accentColor)
        imageView.setImageResource(R.drawable.ic_album)
    }

    private fun dp(value: Float): Int =
        (value * context.resources.displayMetrics.density).toInt().coerceAtLeast(1)

    private fun dpFloat(value: Float): Float = value * context.resources.displayMetrics.density

    companion object {
        private const val VIEW_LIST_FLAT = 0
        private const val VIEW_LIST_ROUNDED = 1
        private const val VIEW_LIST_COMPACT = 2
        private const val VIEW_GRID_FLAT = 3
        private const val VIEW_GRID_ROUNDED = 4
        private const val VIEW_GRID_COMPACT = 5
        private const val PAYLOAD_SELECTION = "selection"
        private const val PAYLOAD_APPEARANCE = "appearance"

        private val SONG_DIFF = object : DiffUtil.ItemCallback<Song>() {
            override fun areItemsTheSame(oldItem: Song, newItem: Song): Boolean =
                oldItem.id == newItem.id

            override fun areContentsTheSame(oldItem: Song, newItem: Song): Boolean =
                oldItem == newItem
        }

        private fun cacheSizeKb(): Int {
            val maxMemoryKb = (Runtime.getRuntime().maxMemory() / 1024L).toInt()
            return (maxMemoryKb / 16).coerceAtLeast(4 * 1024)
        }
    }
}
