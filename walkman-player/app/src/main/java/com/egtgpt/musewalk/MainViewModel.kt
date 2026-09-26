package com.egtgpt.musewalk

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.media3.common.Player
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.Calendar

data class HomeUiState(
    val loading: Boolean = true,
    val tracks: List<Track> = emptyList(),
    val recommendations: List<RecommendedTrack> = emptyList(),
    val current: Track? = null,
    val isPlaying: Boolean = false,
    val selectedGenre: String? = null,
    val searchQuery: String = "",
    val error: String? = null
) {
    val genres: List<String>
        get() = tracks.groupingBy { it.genre }.eachCount()
            .entries.sortedByDescending { it.value }.map { it.key }

    val visibleTracks: List<Track>
        get() {
            val byGenre = selectedGenre?.let { g -> tracks.filter { it.genre == g } } ?: tracks
            if (searchQuery.isBlank()) return byGenre
            val q = searchQuery.trim().lowercase()
            return byGenre.filter {
                it.title.lowercase().contains(q) ||
                    it.artist.lowercase().contains(q) ||
                    it.album.lowercase().contains(q)
            }
        }
}

class MainViewModel(app: Application) : AndroidViewModel(app) {
    private val library = MusicLibrary(app)
    private val stats = StatsStore(app)
    private val engine = RecommendationEngine(stats)

    private val _ui = MutableStateFlow(HomeUiState())
    val ui: StateFlow<HomeUiState> = _ui.asStateFlow()

    private var trackById: Map<Long, Track> = emptyMap()
    private var activeTrackId: Long? = null
    private var activeStartedAt: Long = 0L
    private var countedAsFinished = false
    private var listenerAttached = false
    private var recommendationJob: Job? = null

    private val listener = object : Player.Listener {
        override fun onMediaItemTransition(
            mediaItem: androidx.media3.common.MediaItem?,
            reason: Int
        ) {
            finishPreviousIfNeeded(skipped = reason == Player.MEDIA_ITEM_TRANSITION_REASON_SEEK)
            val id = mediaItem?.mediaId?.toLongOrNull()
            activeTrackId = id
            activeStartedAt = System.currentTimeMillis()
            countedAsFinished = false

            if (id != null) {
                stats.markStarted(
                    id,
                    activeStartedAt,
                    Calendar.getInstance().get(Calendar.HOUR_OF_DAY)
                )
            }
            updatePlaybackState()
        }

        override fun onIsPlayingChanged(isPlaying: Boolean) {
            updatePlaybackState()
        }

        override fun onPlaybackStateChanged(playbackState: Int) {
            if (playbackState == Player.STATE_ENDED && !countedAsFinished) {
                finishPreviousIfNeeded(skipped = false)
                countedAsFinished = true
            }
            updatePlaybackState()
        }
    }

    private fun ensurePlayer(): Player {
        val player = PlayerManager.get(getApplication())
        if (!listenerAttached) {
            player.addListener(listener)
            listenerAttached = true
        }
        return player
    }

    fun loadLibrary() {
        viewModelScope.launch {
            _ui.value = _ui.value.copy(loading = true, error = null)

            val result = runCatching { library.scan() }
            result.onSuccess { tracks ->
                trackById = tracks.associateBy { it.id }

                // First paint: show the library immediately. Do not block on stats/recommendations.
                val instant = tracks.take(20).map {
                    RecommendedTrack(it, 0.0, "最近追加した曲")
                }
                _ui.value = _ui.value.copy(
                    loading = false,
                    tracks = tracks,
                    recommendations = instant,
                    error = null
                )

                refreshRecommendations()
            }.onFailure { e ->
                _ui.value = _ui.value.copy(
                    loading = false,
                    error = e.message ?: "曲を読み込めませんでした"
                )
            }
        }
    }

    fun play(track: Track, source: List<Track> = _ui.value.visibleTracks) {
        val list = if (source.any { it.id == track.id }) source else _ui.value.tracks
        val originalIndex = list.indexOfFirst { it.id == track.id }.coerceAtLeast(0)

        // A300 optimization: don't build hundreds of MediaItems for every tap.
        val before = 16
        val maxQueue = 80
        val start = (originalIndex - before).coerceAtLeast(0)
        val end = (start + maxQueue).coerceAtMost(list.size)
        val queue = list.subList(start, end)
        val queueIndex = originalIndex - start

        ensurePlayer()
        PlayerManager.play(getApplication(), queue, queueIndex)
    }

    fun playRecommended() {
        val tracks = _ui.value.tracks
        if (tracks.isEmpty()) return

        viewModelScope.launch {
            val smartQueue = withContext(Dispatchers.Default) {
                val ranked = _ui.value.recommendations.map { it.track }
                val unseen = tracks.asSequence()
                    .filter { stats.get(it.id).playCount == 0 }
                    .take(24)
                    .toList()
                    .shuffled()

                val now = System.currentTimeMillis()
                val rediscovery = tracks.asSequence()
                    .filter {
                        val last = stats.get(it.id).lastPlayedAt
                        last > 0L && now - last > 14L * 86_400_000L
                    }
                    .take(24)
                    .toList()
                    .shuffled()

                buildList {
                    addAll(ranked.take(12))
                    addAll(unseen.take(4))
                    addAll(rediscovery.take(3))
                    addAll(ranked.drop(12))
                }.distinctBy { it.id }.take(80)
            }

            val first = smartQueue.firstOrNull() ?: return@launch
            play(first, smartQueue)
        }
    }

    fun togglePlayPause() {
        val player = ensurePlayer()
        if (player.isPlaying) player.pause() else player.play()
    }

    fun next() {
        val player = ensurePlayer()
        val listened = System.currentTimeMillis() - activeStartedAt
        if (activeTrackId != null && listened >= 0L && listened < 45_000L) {
            stats.markSkipped(activeTrackId!!, listened)
        }
        player.seekToNextMediaItem()
        player.play()
        refreshRecommendations()
    }

    fun previous() {
        val player = ensurePlayer()
        player.seekToPreviousMediaItem()
        player.play()
    }

    fun selectGenre(genre: String?) {
        _ui.value = _ui.value.copy(selectedGenre = genre)
    }

    fun search(query: String) {
        _ui.value = _ui.value.copy(searchQuery = query)
    }

    fun refreshRecommendations() {
        val tracks = _ui.value.tracks
        if (tracks.isEmpty()) return

        recommendationJob?.cancel()
        recommendationJob = viewModelScope.launch {
            val recommendations = withContext(Dispatchers.Default) {
                engine.recommend(tracks)
            }
            _ui.value = _ui.value.copy(recommendations = recommendations)
        }
    }

    fun statsFor(track: Track): TrackStats = stats.get(track.id)

    private fun finishPreviousIfNeeded(skipped: Boolean) {
        val id = activeTrackId ?: return
        val listened = (System.currentTimeMillis() - activeStartedAt).coerceAtLeast(0L)
        if (skipped) {
            stats.markSkipped(id, listened)
        } else if (!countedAsFinished) {
            stats.markFinished(id, listened)
        }
        refreshRecommendations()
    }

    private fun updatePlaybackState() {
        val player = PlayerManager.peek() ?: return
        val currentId = player.currentMediaItem?.mediaId?.toLongOrNull()
        val current = currentId?.let(trackById::get)
        _ui.value = _ui.value.copy(
            current = current,
            isPlaying = player.isPlaying
        )
    }

    override fun onCleared() {
        recommendationJob?.cancel()
        PlayerManager.peek()?.let { player ->
            if (listenerAttached) player.removeListener(listener)
        }
        super.onCleared()
    }
}
