package com.egtgpt.musewalk

import android.content.Context

class FavoritesStore(context: Context) {
    private val prefs = context.getSharedPreferences("musewalk_favorites", Context.MODE_PRIVATE)
    private val ids = prefs.getStringSet("ids", emptySet())
        .orEmpty()
        .mapNotNull { it.toLongOrNull() }
        .toMutableSet()

    @Synchronized
    fun all(): Set<Long> = ids.toSet()

    @Synchronized
    fun isFavorite(trackId: Long): Boolean = trackId in ids

    @Synchronized
    fun toggle(trackId: Long): Boolean {
        val nowFavorite = if (trackId in ids) {
            ids.remove(trackId)
            false
        } else {
            ids.add(trackId)
            true
        }
        prefs.edit().putStringSet("ids", ids.map(Long::toString).toSet()).apply()
        return nowFavorite
    }
}
