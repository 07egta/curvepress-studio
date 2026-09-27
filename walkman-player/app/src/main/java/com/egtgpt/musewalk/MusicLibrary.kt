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
        val genreColumn = if (android.os.Build.VERSION.SDK_INT >= 30) GENRE_COLUMN else null
        val projection = mutableListOf(
            MediaStore.Audio.Media._ID,
            MediaStore.Audio.Media.TITLE,
            MediaStore.Audio.Media.ARTIST,
            MediaStore.Audio.Media.ALBUM,
            MediaStore.Audio.Media.DURATION,
            MediaStore.Audio.Media.DATE_ADDED,
            pathColumn
        ).apply {
            if (genreColumn != null) add(genreColumn)
        }.toTypedArray()

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
            val genreCol = cursor.getColumnIndex(GENRE_COLUMN)

            while (cursor.moveToNext()) {
                val id = cursor.getLong(idCol)
                val path = if (pathCol >= 0) cursor.getString(pathCol).orEmpty() else ""
                val title = cursor.getString(titleCol).orEmpty().ifBlank { "タイトル不明" }
                val artist = cursor.getString(artistCol).orEmpty()
                    .takeUnless { it == "<unknown>" }.orEmpty().ifBlank { "アーティスト不明" }
                val album = cursor.getString(albumCol).orEmpty().ifBlank { "アルバム不明" }
                val rawGenre = if (genreCol >= 0) cursor.getString(genreCol).orEmpty() else ""

                result += Track(
                    id = id,
                    title = title,
                    artist = artist,
                    album = album,
                    genre = inferGenre(rawGenre, path, title, artist, album),
                    durationMs = cursor.getLong(durationCol),
                    uri = ContentUris.withAppendedId(MediaStore.Audio.Media.EXTERNAL_CONTENT_URI, id),
                    dateAddedSec = cursor.getLong(addedCol)
                )
            }
        }
        result
    }

    private fun inferGenre(
        rawGenre: String,
        path: String,
        title: String,
        artist: String,
        album: String
    ): String {
        normalizeGenreTag(rawGenre)?.let { return it }

        val normalizedPath = path.lowercase()
        if (containsAny(normalizedPath, "要確認", "needs review")) return "ジャンル未設定"
        inferGenreFromPath(path)?.let { return it }

        val details = "$title $artist $album".lowercase()
        return when {
            containsAny(details, "ボカロ", "初音ミク", "鏡音", "巡音", "重音テト", "合成音声") ||
                containsLatinWord(details, "vocaloid") || "synthesizer v" in details -> "ボカロ"
            containsAny(details, "背景音楽", "作業用", "睡眠", "リラックス", "lo-fi", "background music") ||
                listOf("bgm", "relax", "meditation", "study", "sleep", "ambient", "lofi")
                    .any { containsLatinWord(details, it) } -> "BGM"
            containsAny(
                details,
                "アニソン", "アニメ", "ゲーム音楽", "サウンドトラック", "主題歌", "オープニング", "エンディング"
            ) || listOf("anime", "game", "soundtrack", "ost").any { containsLatinWord(details, it) } ->
                "アニメ・ゲーム"
            containsAny(details, "クラシック", "交響曲", "ピアノソナタ") ||
                listOf("classical", "symphony").any { containsLatinWord(details, it) } -> "クラシック"
            containsAny(details, "ジャズ") ||
                listOf("jazz", "swing").any { containsLatinWord(details, it) } -> "ジャズ"
            containsAny(details, "ヒップホップ", "ラップ") ||
                listOf("hip hop", "hip-hop", "hiphop", "rap").any { containsLatinWord(details, it) } ->
                "ヒップホップ"
            containsAny(details, "r&b", "ソウル") ||
                listOf("rnb", "soul").any { containsLatinWord(details, it) } -> "R&B・ソウル"
            containsAny(details, "電子音楽", "ダンスミュージック") ||
                listOf("edm", "electronic").any { containsLatinWord(details, it) } -> "電子音楽"
            containsAny(details, "j-pop", "jpop", "邦楽") -> "J-POP"
            containsAny(details, "ロック", "パンク", "メタル") ||
                listOf("rock", "punk", "metal").any { containsLatinWord(details, it) } -> "ロック"
            containsAny(details, "ポップ", "pop music") || containsLatinWord(details, "pop") -> "ポップ"
            containsAny(details, "ブルース") || containsLatinWord(details, "blues") -> "ブルース"
            containsAny(details, "フォーク", "カントリー") ||
                listOf("folk", "country").any { containsLatinWord(details, it) } -> "フォーク"
            else -> "ジャンル未設定"
        }
    }

    private fun inferGenreFromPath(path: String): String? {
        val normalized = path.lowercase()
        if (containsAny(normalized, "その他", "要確認", "needs review")) return null

        return when {
            containsAny(normalized, "ボカロ", "合成音声") ||
                containsLatinWord(normalized, "vocaloid") -> "ボカロ"
            containsAny(normalized, "j-pop", "邦楽") ||
                containsLatinWord(normalized, "jpop") -> "J-POP"
            "洋楽" in normalized -> "洋楽"
            containsAny(normalized, "アニメ", "映画音楽", "サウンドトラック") ||
                containsLatinWord(normalized, "anime") -> "アニメ・ゲーム"
            "ゲーム" in normalized || containsLatinWord(normalized, "game") -> "アニメ・ゲーム"
            containsAny(normalized, "bgm", "背景音楽") -> "BGM"
            "クラシック" in normalized || containsLatinWord(normalized, "classical") -> "クラシック"
            else -> null
        }
    }

    private fun normalizeGenreTag(rawGenre: String): String? {
        val value = rawGenre.trim()
        if (value.isBlank() || value.equals("<unknown>", ignoreCase = true) ||
            value.equals("unknown", ignoreCase = true) || value.equals("null", ignoreCase = true)
        ) return null

        val primary = value.split(Regex("[;,/]")).firstOrNull { it.isNotBlank() }?.trim()
            ?: return null
        val normalized = primary.lowercase()
        return when {
            normalized in setOf("j-pop", "jpop", "j pop", "邦楽") -> "J-POP"
            normalized in setOf("pop", "ポップ") -> "ポップ"
            normalized in setOf("rock", "ロック") -> "ロック"
            normalized in setOf("classical", "classic", "クラシック") -> "クラシック"
            normalized in setOf("jazz", "ジャズ") -> "ジャズ"
            normalized in setOf("vocaloid", "ボカロ") -> "ボカロ"
            normalized in setOf("hip hop", "hip-hop", "hiphop", "rap", "ヒップホップ") ->
                "ヒップホップ"
            normalized in setOf("r&b", "rnb", "soul", "ソウル") -> "R&B・ソウル"
            normalized in setOf("electronic", "edm", "dance", "電子音楽") -> "電子音楽"
            normalized in setOf("soundtrack", "サウンドトラック", "ost") -> "サウンドトラック"
            normalized in setOf("bgm", "background music", "背景音楽") -> "BGM"
            normalized in setOf("blues", "ブルース") -> "ブルース"
            normalized in setOf("folk", "フォーク", "country", "カントリー") -> "フォーク"
            normalized in setOf("metal", "メタル", "punk", "パンク") -> "ロック"
            else -> primary
        }
    }

    private fun containsAny(text: String, vararg terms: String): Boolean =
        terms.any { it in text }

    private fun containsLatinWord(text: String, word: String): Boolean {
        val pattern = "(^|[^a-z0-9])" + Regex.escape(word) + "([^a-z0-9]|$)"
        return Regex(pattern, RegexOption.IGNORE_CASE).containsMatchIn(text)
    }

    private companion object {
        const val GENRE_COLUMN = "genre"
    }
}
