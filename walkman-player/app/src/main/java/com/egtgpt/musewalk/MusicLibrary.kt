package com.egtgpt.musewalk

import android.content.ContentUris
import android.content.Context
import android.provider.MediaStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

class MusicLibrary(private val context: Context) {
    suspend fun scan(): List<Track> = withContext(Dispatchers.IO) {
        val result = mutableListOf<Track>()
        val pathColumn = if (android.os.Build.VERSION.SDK_INT >= 29) {
            MediaStore.Audio.Media.RELATIVE_PATH
        } else {
            MediaStore.Audio.Media.DATA
        }
        val projection = arrayOf(
            MediaStore.Audio.Media._ID,
            MediaStore.Audio.Media.TITLE,
            MediaStore.Audio.Media.ARTIST,
            MediaStore.Audio.Media.ALBUM,
            MediaStore.Audio.Media.DURATION,
            MediaStore.Audio.Media.DATE_ADDED,
            pathColumn
        )

        context.contentResolver.query(
            MediaStore.Audio.Media.EXTERNAL_CONTENT_URI,
            projection,
            MediaStore.Audio.Media.IS_MUSIC + " != 0",
            null,
            MediaStore.Audio.Media.DATE_ADDED + " DESC"
        )?.use { cursor ->
            val idCol = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media._ID)
            val titleCol = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.TITLE)
            val artistCol = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.ARTIST)
            val albumCol = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.ALBUM)
            val durationCol = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.DURATION)
            val addedCol = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.DATE_ADDED)
            val pathCol = cursor.getColumnIndex(pathColumn)

            while (cursor.moveToNext()) {
                val id = cursor.getLong(idCol)
                val path = if (pathCol >= 0) cursor.getString(pathCol).orEmpty() else ""
                result += Track(
                    id = id,
                    title = cursor.getString(titleCol).orEmpty().ifBlank { "タイトル不明" },
                    artist = cursor.getString(artistCol).orEmpty()
                        .takeUnless { it == "<unknown>" }.orEmpty().ifBlank { "アーティスト不明" },
                    album = cursor.getString(albumCol).orEmpty().ifBlank { "アルバム不明" },
                    genre = inferGenre(path),
                    durationMs = cursor.getLong(durationCol),
                    uri = ContentUris.withAppendedId(MediaStore.Audio.Media.EXTERNAL_CONTENT_URI, id),
                    dateAddedSec = cursor.getLong(addedCol)
                )
            }
        }
        result
    }

    private fun inferGenre(path: String): String {
        val normalized = path.lowercase()
        return when {
            "ボカロ" in path || "vocaloid" in normalized -> "ボカロ"
            "アニメ" in path || "ゲーム" in path || "anime" in normalized || "game" in normalized -> "アニメ・ゲーム"
            "洋楽" in path || "western" in normalized -> "洋楽"
            "j-pop" in normalized || "邦楽" in path -> "J-POP"
            "bgm" in normalized || "睡眠" in path -> "BGM"
            "クラシック" in path || "classic" in normalized -> "クラシック"
            else -> path.trim('/').substringBefore('/').ifBlank { "その他" }
        }
    }
}
