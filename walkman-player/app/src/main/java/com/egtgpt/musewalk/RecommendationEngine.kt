package com.egtgpt.musewalk

import java.util.Calendar
import kotlin.math.ln

class RecommendationEngine(private val statsStore: StatsStore) {
    fun recommend(tracks: List<Track>, limit: Int = 20): List<RecommendedTrack> {
        val now = System.currentTimeMillis()
        val hour = Calendar.getInstance().get(Calendar.HOUR_OF_DAY)

        return tracks.map { track ->
            val s = statsStore.get(track.id)
            val daysSince = if (s.lastPlayedAt == 0L) 999.0
                else (now - s.lastPlayedAt).coerceAtLeast(0L) / 86_400_000.0

            val familiarity = ln(1.0 + s.playCount) * 1.8
            val completion = s.completionRate * 4.0
            val skipPenalty = s.skipRate * 5.0
            val totalHours = s.hourHistogram.sum().coerceAtLeast(1)
            val timeAffinity = (s.hourHistogram[hour].toDouble() / totalHours) * 4.0
            val rediscovery = when {
                s.playCount == 0 -> 2.8
                daysSince > 30 -> 2.2
                daysSince > 14 -> 1.2
                else -> 0.0
            }
            val overplayPenalty = if (daysSince < 1 && s.playCount > 5) 1.8 else 0.0

            val score = familiarity + completion + timeAffinity + rediscovery - skipPenalty - overplayPenalty
            val reason = when {
                s.playCount == 0 -> "まだあまり聴いていない曲"
                daysSince > 30 -> "久しぶりに聴く曲"
                s.completionRate >= 0.8 && s.playCount >= 3 -> "最後までよく聴いている曲"
                timeAffinity > 0.8 -> "この時間によく聴く曲"
                else -> "あなたの再生履歴から"
            }
            RecommendedTrack(track, score, reason)
        }.sortedByDescending { it.score }.take(limit)
    }
}
