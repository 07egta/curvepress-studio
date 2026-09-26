package com.egtgpt.musewalk

import android.net.Uri

data class Track(
    val id: Long,
    val title: String,
    val artist: String,
    val album: String,
    val genre: String,
    val durationMs: Long,
    val uri: Uri,
    val dateAddedSec: Long
)

data class TrackStats(
    val playCount: Int = 0,
    val completedCount: Int = 0,
    val skipCount: Int = 0,
    val totalListenMs: Long = 0L,
    val lastPlayedAt: Long = 0L,
    val lastStartedAt: Long = 0L,
    val hourHistogram: IntArray = IntArray(24)
) {
    val completionRate: Double
        get() = if (playCount == 0) 0.0 else completedCount.toDouble() / playCount
    val skipRate: Double
        get() = if (playCount == 0) 0.0 else skipCount.toDouble() / playCount
}

data class RecommendedTrack(
    val track: Track,
    val score: Double,
    val reason: String
)
