package com.egtgpt.musewalk

import android.content.Context
import androidx.media3.common.Player

class PlaybackPrefsStore(context: Context) {
    private val prefs = context.getSharedPreferences("musewalk_playback", Context.MODE_PRIVATE)

    var repeatMode: Int
        get() = prefs.getInt(KEY_REPEAT, Player.REPEAT_MODE_OFF)
        set(value) {
            prefs.edit().putInt(KEY_REPEAT, value).apply()
        }

    var shuffleEnabled: Boolean
        get() = prefs.getBoolean(KEY_SHUFFLE, false)
        set(value) {
            prefs.edit().putBoolean(KEY_SHUFFLE, value).apply()
        }

    var continuousPlayback: Boolean
        get() = prefs.getBoolean(KEY_CONTINUOUS, true)
        set(value) {
            prefs.edit().putBoolean(KEY_CONTINUOUS, value).apply()
        }

    private companion object {
        const val KEY_REPEAT = "repeat_mode"
        const val KEY_SHUFFLE = "shuffle"
        const val KEY_CONTINUOUS = "continuous"
    }
}
