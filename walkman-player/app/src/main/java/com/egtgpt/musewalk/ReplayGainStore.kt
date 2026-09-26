package com.egtgpt.musewalk

import android.content.Context
import android.net.Uri
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.nio.charset.StandardCharsets
import java.util.concurrent.ConcurrentHashMap
import kotlin.math.pow

/**
 * Battery-friendly, non-destructive loudness normalization.
 *
 * We never decode the full song in the background. Only the first metadata-sized
 * chunk is inspected for ReplayGain / R128 tags and the result is cached.
 */
class ReplayGainStore(private val context: Context) {
    private val prefs = context.getSharedPreferences("musewalk_replaygain", Context.MODE_PRIVATE)
    private val memory = ConcurrentHashMap<Long, Float>()

    suspend fun volumeFor(track: Track): Float = withContext(Dispatchers.IO) {
        memory[track.id]?.let { return@withContext it }

        val key = "v2_" + track.id
        if (prefs.contains(key)) {
            val cached = prefs.getFloat(key, 1f)
            memory[track.id] = cached
            return@withContext cached
        }

        val info = readTags(track.uri)
        val volume = info.volume
        memory[track.id] = volume
        prefs.edit().putFloat(key, volume).apply()
        volume
    }

    private data class GainInfo(
        val gainDb: Float? = null,
        val peak: Float? = null
    ) {
        val volume: Float
            get() {
                val gain = gainDb ?: return 1f
                val requested = 10f.pow(gain / 20f)
                // Never boost without measured headroom. This keeps normalization
                // non-destructive and avoids clipping on unknown files.
                val peakCeiling = peak?.takeIf { it > 0f }?.let { 1f / it } ?: 1f
                return minOf(requested, peakCeiling, 1f).coerceIn(0.08f, 1f)
            }
    }

    private fun readTags(uri: Uri): GainInfo {
        val maxBytes = 512 * 1024
        val bytes = runCatching {
            context.contentResolver.openInputStream(uri)?.buffered()?.use { input ->
                val buffer = ByteArray(maxBytes)
                var total = 0
                while (total < maxBytes) {
                    val read = input.read(buffer, total, maxBytes - total)
                    if (read <= 0) break
                    total += read
                }
                buffer.copyOf(total)
            }
        }.getOrNull() ?: return GainInfo()

        if (bytes.isEmpty()) return GainInfo()

        // ReplayGain and Vorbis-comment keys are ASCII even when the surrounding
        // container is binary. Removing NULs also catches common UTF-16 ID3 TXXX.
        val raw = String(bytes, StandardCharsets.ISO_8859_1)
        val searchable = raw.replace("\u0000", "")

        val gain = findNumber(searchable, "REPLAYGAIN_TRACK_GAIN")
            ?: findNumber(searchable, "REPLAYGAIN_ALBUM_GAIN")

        val r128Raw = findInteger(searchable, "R128_TRACK_GAIN")
            ?: findInteger(searchable, "R128_ALBUM_GAIN")

        val r128Db = r128Raw?.let { it / 256f + 5f }
        val peak = findNumber(searchable, "REPLAYGAIN_TRACK_PEAK")
            ?: findNumber(searchable, "REPLAYGAIN_ALBUM_PEAK")

        return GainInfo(
            gainDb = gain ?: r128Db,
            peak = peak?.takeIf { it > 0f && it <= 8f }
        )
    }

    private fun findNumber(text: String, key: String): Float? {
        val index = text.indexOf(key, ignoreCase = true)
        if (index < 0) return null
        val tail = text.substring(index + key.length, minOf(text.length, index + key.length + 96))
        return NUMBER.find(tail)?.value?.toFloatOrNull()?.takeIf { it in -60f..60f }
    }

    private fun findInteger(text: String, key: String): Int? {
        val index = text.indexOf(key, ignoreCase = true)
        if (index < 0) return null
        val tail = text.substring(index + key.length, minOf(text.length, index + key.length + 64))
        return INTEGER.find(tail)?.value?.toIntOrNull()
    }

    private companion object {
        val NUMBER = Regex("[+-]?\\d+(?:\\.\\d+)?")
        val INTEGER = Regex("[+-]?\\d+")
    }
}
