package com.egtgpt.musewalk

import java.util.Calendar
import kotlin.math.ln

class RecommendationEngine(private val statsStore: StatsStore) {
    fun recommend(
        tracks: List<Track>,
        favorites: Set<Long> = emptySet(),
        limit: Int = 20
    ): List<RecommendedTrack> {
        val now = System.currentTimeMillis()
        val hour = Calendar.getInstance().get(Calendar.HOUR_OF_DAY)

        val scored = tracks.map { track ->
            val s = statsStore.get(track.id)
            val daysSince = if (s.lastPlayedAt == 0L) {
                999.0
            } else {
                (now - s.lastPlayedAt).coerceAtLeast(0L) / 86_400_000.0
            }

            val familiarity = ln(1.0 + s.playCount) * 1.65
            val completion = s.completionRate * 4.2
            val skipPenalty = s.skipRate * 5.2
            val favoriteBonus = if (track.id in favorites) 5.5 else 0.0
            val totalHours = s.hourHistogram.sum().coerceAtLeast(1)
            val timeAffinity = (s.hourHistogram[hour].toDouble() / totalHours) * 3.5
            val rediscovery = when {
                s.playCount == 0 -> 2.6
                daysSince > 45 -> 2.4
                daysSince > 21 -> 1.5
                else -> 0.0
            }
            val recentMomentum = when {
                daysSince <= 2 && s.playCount >= 3 -> 1.4
                daysSince <= 7 && s.playCount >= 2 -> 0.7
                else -> 0.0
            }
            val overplayPenalty = when {
                daysSince < 0.35 && s.playCount >= 8 -> 2.8
                daysSince < 1.0 && s.playCount >= 5 -> 1.7
                else -> 0.0
            }

            val score = familiarity +
                completion +
                favoriteBonus +
                timeAffinity +
                rediscovery +
                recentMomentum -
                skipPenalty -
                overplayPenalty

            val reason = when {
                track.id in favorites -> "お気に入り"
                s.playCount == 0 -> "まだあまり聴いていない曲"
                daysSince > 30 -> "久しぶりに聴く曲"
                s.completionRate >= 0.8 && s.playCount >= 3 -> "最後までよく聴いている曲"
                timeAffinity > 0.8 -> "この時間によく聴く曲"
                recentMomentum > 0.0 -> "最近よく聴いている曲"
                else -> "あなたの再生履歴から"
            }
            RecommendedTrack(track, score, reason)
        }.sortedByDescending { it.score }

        return diversify(scored, limit)
    }

    /**
     * A300 is often used in one long listening session. Avoid obvious runs of the
     * same artist / genre without doing any expensive ML or background work.
     */
    private fun diversify(
        scored: List<RecommendedTrack>,
        limit: Int
    ): List<RecommendedTrack> {
        if (scored.size <= 1) return scored.take(limit)

        val remaining = scored.toMutableList()
        val out = ArrayList<RecommendedTrack>(minOf(limit, scored.size))
        var lastArtist: String? = null
        var lastGenre: String? = null
        var sameGenreRun = 0

        while (remaining.isNotEmpty() && out.size < limit) {
            val window = remaining.take(minOf(10, remaining.size))
            val chosen = window.firstOrNull { candidate ->
                val artistOk = candidate.track.artist != lastArtist
                val genreOk = candidate.track.genre != lastGenre || sameGenreRun < 2
                artistOk && genreOk
            } ?: remaining.first()

            remaining.remove(chosen)
            out += chosen

            sameGenreRun = if (chosen.track.genre == lastGenre) sameGenreRun + 1 else 1
            lastArtist = chosen.track.artist
            lastGenre = chosen.track.genre
        }
        return out
    }
}
