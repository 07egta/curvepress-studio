package com.egtgpt.musewalk

import android.content.Context
import android.util.Xml
import org.json.JSONArray
import org.json.JSONObject
import org.xmlpull.v1.XmlPullParser
import java.util.concurrent.ConcurrentHashMap

class StatsStore(context: Context) {
    private val prefs = context.getSharedPreferences("musewalk_stats", Context.MODE_PRIVATE)
    private val cache = ConcurrentHashMap<Long, TrackStats>()

    init {
        importLegacyStatsIfAvailable(context)
    }

    private fun importLegacyStatsIfAvailable(context: Context) {
        if (prefs.all.isNotEmpty()) return
        val backup = context.getExternalFilesDir(null)?.resolve("musewalk_stats.xml") ?: return
        if (!backup.isFile) return

        val values = runCatching {
            val parser = Xml.newPullParser()
            backup.inputStream().buffered().use { input ->
                parser.setInput(input, "UTF-8")
                parser.nextTag()
                parser.require(XmlPullParser.START_TAG, null, "map")
                val imported = mutableMapOf<String, String>()
                while (parser.next() != XmlPullParser.END_TAG) {
                    if (parser.eventType == XmlPullParser.START_TAG) {
                        if (parser.name == "string") {
                            val key = parser.getAttributeValue(null, "name")
                            val value = parser.nextText()
                            if (key?.toLongOrNull() != null) imported[key] = value
                        } else {
                            skipSubtree(parser)
                        }
                    }
                }
                imported
            }
        }.getOrElse { return }

        if (values.isEmpty()) return
        val editor = prefs.edit()
        values.forEach { (key, value) -> editor.putString(key, value) }
        editor.putBoolean("_legacyStatsImported", true).apply()
    }

    private fun skipSubtree(parser: XmlPullParser) {
        var depth = 1
        while (depth > 0) {
            when (parser.next()) {
                XmlPullParser.START_TAG -> depth++
                XmlPullParser.END_TAG -> depth--
            }
        }
    }

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
