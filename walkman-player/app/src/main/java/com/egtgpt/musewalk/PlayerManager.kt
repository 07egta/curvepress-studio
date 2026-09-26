package com.egtgpt.musewalk

import android.content.Context
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata
import androidx.media3.exoplayer.ExoPlayer

object PlayerManager {
    @Volatile private var player: ExoPlayer? = null

    fun get(context: Context): ExoPlayer =
        player ?: synchronized(this) {
            player ?: ExoPlayer.Builder(context.applicationContext).build().also { player = it }
        }

    fun play(context: Context, tracks: List<Track>, startIndex: Int) {
        val p = get(context)
        val items = tracks.map { track ->
            MediaItem.Builder()
                .setUri(track.uri)
                .setMediaId(track.id.toString())
                .setMediaMetadata(
                    MediaMetadata.Builder()
                        .setTitle(track.title)
                        .setArtist(track.artist)
                        .setAlbumTitle(track.album)
                        .build()
                )
                .build()
        }
        p.setMediaItems(items, startIndex.coerceIn(items.indices), 0L)
        p.prepare()
        p.play()
    }

    fun release() {
        player?.release()
        player = null
    }
}
