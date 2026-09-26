package com.egtgpt.musewalk

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.ConcurrentHashMap

class StatsStore(context: Context) {
    private val prefs = context.getSharedPreferences("musewalk_stats", Context.MODE_PRIVATE)
    private val cache = ConcurrentHashMap<Long, TrackStats>()

    fun get(trackId: Long): TrackStats {
        cache[trackId]?.let { return it }

        val raw = prefs.getString(trackId.toString(), null)
        if (raw == null) {
            val empty = TrackStats()
            cache[trackId] = empty
            return empty
        }

        val parsed = runCatching {
            val json = JSONObject(raw)
            val hours = IntArray(24)
            val arr = json.optJSONArray("hours") ?: JSONArray()
            for (i in 0 until minOf(24, arr.length())) hours[i] = arr.optInt(i)
            TrackStats(
                playCount = json.optInt("playCount"),
                completedCount = json.optInt("completedCount"),
                skipCount = json.optInt("skipCount"),
                totalListenMs = json.optLong("totalListenMs"),
                lastPlayedAt = json.optLong("lastPlayedAt"),
                lastStartedAt = json.optLong("lastStartedAt"),
                hourHistogram = hours
            )
        }.getOrDefault(TrackStats())

        cache[trackId] = parsed
        return parsed
    }

    fun save(trackId: Long, stats: TrackStats) {
        cache[trackId] = stats
        val json = JSONObject()
            .put("playCount", stats.playCount)
            .put("completedCount", stats.completedCount)
            .put("skipCount", stats.skipCount)
            .put("totalListenMs", stats.totalListenMs)
            .put("lastPlayedAt", stats.lastPlayedAt)
            .put("lastStartedAt", stats.lastStartedAt)
            .put("hours", JSONArray(stats.hourHistogram.toList()))
        prefs.edit().putString(trackId.toString(), json.toString()).apply()
    }

    fun markStarted(trackId: Long, now: Long, hour: Int) {
        val old = get(trackId)
        val hours = old.hourHistogram.copyOf()
        if (hour in 0..23) hours[hour]++
        save(
            trackId,
            old.copy(
                playCount = old.playCount + 1,
                lastStartedAt = now,
                lastPlayedAt = now,
                hourHistogram = hours
            )
        )
    }

    fun markFinished(trackId: Long, listenedMs: Long) {
        val old = get(trackId)
        save(
            trackId,
            old.copy(
                completedCount = old.completedCount + 1,
                totalListenMs = old.totalListenMs + listenedMs,
                lastPlayedAt = System.currentTimeMillis()
            )
        )
    }

    fun markSkipped(trackId: Long, listenedMs: Long) {
        val old = get(trackId)
        save(
            trackId,
            old.copy(
                skipCount = old.skipCount + 1,
                totalListenMs = old.totalListenMs + listenedMs,
                lastPlayedAt = System.currentTimeMillis()
            )
        )
    }
}
