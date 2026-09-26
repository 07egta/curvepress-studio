package com.egtgpt.musewalk

import android.content.Context
import android.content.Intent
import android.os.Build
import android.provider.Settings

data class WalkmanAudioProfile(
    val isA300: Boolean,
    val modelName: String,
    val preferredCodec: String,
    val enhancement: String,
    val normalization: String
)

object WalkmanProfile {
    fun detect(): WalkmanAudioProfile {
        val model = Build.MODEL.orEmpty()
        val normalized = model.uppercase()
        val isA300 = normalized.contains("NW-A306") ||
            normalized.contains("NW-A307") ||
            normalized.contains("A306") ||
            normalized.contains("A307")
        return WalkmanAudioProfile(
            isA300 = isA300,
            modelName = model.ifBlank { "Android device" },
            preferredCodec = if (isA300) "LDAC" else "端末の高音質コーデック",
            enhancement = if (isA300) "DSEE Ultimate" else "端末の音質補完",
            normalization = if (isA300) "ダイナミックノーマライザー" else "音量ノーマライズ"
        )
    }

    fun openBluetoothSettings(context: Context) {
        context.startActivity(
            Intent(Settings.ACTION_BLUETOOTH_SETTINGS)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        )
    }

    fun openSoundSettings(context: Context) {
        context.startActivity(
            Intent(Settings.ACTION_SOUND_SETTINGS)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        )
    }
}
