package com.egtgpt.musewalk

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.media3.common.Player
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.Dispatchers
import java.util.Calendar

data class HomeUiState(
    val loading: Boolean = true,
    val tracks: List<Track> = emptyList(),
    val recommendations: List<RecommendedTrack> = emptyList(),
    val current: Track? = null,
    val isPlaying: Boolean = false,
    val selectedGenre: String? = null,
    val searchQuery: String = "",
    val favorites: Set<Long> = emptySet(),
    val queue: List<Track> = emptyList(),
    val queueIndex: Int = -1,
    val playbackPositionMs: Long = 0L,
    val playbackDurationMs: Long = 0L,
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
    private val favoritesStore = FavoritesStore(app)
    private val replayGain = ReplayGainStore(app)
    private val engine = RecommendationEngine(stats)

    private val _ui = MutableStateFlow(
        HomeUiState(favorites = favoritesStore.all())
    )
    val ui: StateFlow<HomeUiState> = _ui.asStateFlow()

    private var trackById: Map<Long, Track> = emptyMap()
    private var activeTrackId: Long? = null
    private var activeStartedAt: Long = 0L
    private var countedAsFinished = false
    private var listenerAttached = false
    private var recommendationJob: Job? = null
    private var normalizationJob: Job? = null

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
                applyReplayGain(id)
            }
            updatePlaybackState(includeQueue = true)
        }

        override fun onIsPlayingChanged(isPlaying: Boolean) {
            updatePlaybackState(includeQueue = false)
        }

        override fun onPlaybackStateChanged(playbackState: Int) {
            if (playbackState == Player.STATE_ENDED && !countedAsFinished) {
                finishPreviousIfNeeded(skipped = false)
                countedAsFinished = true
            }
            updatePlaybackState(includeQueue = false)
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

                // First paint immediately. Heavy recommendation scoring comes later.
                val instant = tracks.take(20).map {
                    RecommendedTrack(it, 0.0, "最近追加した曲")
                }

                _ui.value = _ui.value.copy(
                    loading = false,
                    tracks = tracks,
                    recommendations = instant,
                    favorites = favoritesStore.all(),
                    error = null
                )

                PlayerManager.peek()?.let {
                    if (!listenerAttached) {
                        it.addListener(listener)
                        listenerAttached = true
                    }
                    updatePlaybackState(includeQueue = true)
                }

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

        // Keep the media queue bounded on the low-power A300.
        val before = 12
        val maxQueue = 60
        val start = (originalIndex - before).coerceAtLeast(0)
        val end = (start + maxQueue).coerceAtMost(list.size)
        val queue = list.subList(start, end)
        val queueIndex = originalIndex - start

        viewModelScope.launch {
            // Only inspect this track's metadata on demand; never full-scan audio in background.
            val initialVolume = replayGain.volumeFor(track)
            ensurePlayer()
            PlayerManager.play(
                context = getApplication(),
                tracks = queue,
                startIndex = queueIndex,
                initialVolume = initialVolume
            )
        }
    }

    fun playRecommended() {
        val tracks = _ui.value.tracks
        if (tracks.isEmpty()) return

        viewModelScope.launch {
            val smartQueue = withContext(Dispatchers.Default) {
                val ranked = _ui.value.recommendations.map { it.track }
                val unseen = tracks.asSequence()
                    .filter { stats.get(it.id).playCount == 0 }
                    .take(20)
                    .toList()
                    .shuffled()

                val now = System.currentTimeMillis()
                val rediscovery = tracks.asSequence()
                    .filter {
                        val last = stats.get(it.id).lastPlayedAt
                        last > 0L && now - last > 14L * 86_400_000L
                    }
                    .take(20)
                    .toList()
                    .shuffled()

                buildList {
                    addAll(ranked.take(14))
                    addAll(unseen.take(4))
                    addAll(rediscovery.take(3))
                    addAll(ranked.drop(14))
                }.distinctBy { it.id }.take(60)
            }

            val first = smartQueue.firstOrNull() ?: return@launch
            play(first, smartQueue)
        }
    }

    fun togglePlayPause() {
        val player = PlayerManager.peek() ?: return
        if (player.isPlaying) player.pause() else player.play()
    }

    fun next() {
        val player = PlayerManager.peek() ?: return
        // The media-item transition listener records the skip exactly once.
        player.seekToNextMediaItem()
        player.play()
        // Do not recalculate recommendations here: this may happen with screen off.
    }

    fun previous() {
        val player = PlayerManager.peek() ?: return
        player.seekToPreviousMediaItem()
        player.play()
    }

    fun playQueueIndex(index: Int) {
        val player = PlayerManager.peek() ?: return
        if (index !in 0 until player.mediaItemCount) return
        player.seekTo(index, 0L)
        player.play()
    }

    fun seekTo(positionMs: Long) {
        val player = PlayerManager.peek() ?: return
        val duration = player.duration.takeIf { it > 0L } ?: _ui.value.playbackDurationMs
        player.seekTo(positionMs.coerceIn(0L, duration.coerceAtLeast(0L)))
        updateProgress()
    }

    /**
     * Called only while the full-screen player is visible.
     * No permanent ticker is kept in the ViewModel.
     */
    fun updateProgress() {
        val player = PlayerManager.peek() ?: return
        val duration = player.duration.takeIf { it > 0L }
            ?: _ui.value.current?.durationMs
            ?: 0L
        _ui.value = _ui.value.copy(
            playbackPositionMs = player.currentPosition.coerceAtLeast(0L),
            playbackDurationMs = duration.coerceAtLeast(0L)
        )
    }

    fun toggleFavorite(track: Track) {
        favoritesStore.toggle(track.id)
        _ui.value = _ui.value.copy(favorites = favoritesStore.all())
        refreshRecommendations()
    }

    fun isFavorite(track: Track): Boolean = track.id in _ui.value.favorites

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
        val favoriteIds = _ui.value.favorites
        recommendationJob = viewModelScope.launch {
            val recommendations = withContext(Dispatchers.Default) {
                engine.recommend(tracks, favoriteIds)
            }
            _ui.value = _ui.value.copy(recommendations = recommendations)
        }
    }

    fun statsFor(track: Track): TrackStats = stats.get(track.id)

    private fun applyReplayGain(trackId: Long) {
        val track = trackById[trackId] ?: return
        normalizationJob?.cancel()
        normalizationJob = viewModelScope.launch {
            val volume = replayGain.volumeFor(track)
            val player = PlayerManager.peek() ?: return@launch
            if (player.currentMediaItem?.mediaId == trackId.toString()) {
                player.volume = volume
            }
        }
    }

    private fun finishPreviousIfNeeded(skipped: Boolean) {
        val id = activeTrackId ?: return
        val listened = (System.currentTimeMillis() - activeStartedAt).coerceAtLeast(0L)
        if (skipped && listened < 45_000L) {
            stats.markSkipped(id, listened)
        } else if (!skipped && !countedAsFinished) {
            stats.markFinished(id, listened)
        }
        // Battery policy: recommendations update on launch/favorite changes, not every song.
    }

    private fun updatePlaybackState(includeQueue: Boolean) {
        val player = PlayerManager.peek() ?: return
        val currentId = player.currentMediaItem?.mediaId?.toLongOrNull()
        val current = currentId?.let(trackById::get)

        val queue = if (includeQueue) {
            buildList {
                for (i in 0 until player.mediaItemCount) {
                    val id = player.getMediaItemAt(i).mediaId.toLongOrNull()
                    id?.let(trackById::get)?.let(::add)
                }
            }
        } else {
            _ui.value.queue
        }

        val duration = player.duration.takeIf { it > 0L } ?: current?.durationMs ?: 0L
        _ui.value = _ui.value.copy(
            current = current,
            isPlaying = player.isPlaying,
            queue = queue,
            queueIndex = player.currentMediaItemIndex,
            playbackPositionMs = player.currentPosition.coerceAtLeast(0L),
            playbackDurationMs = duration.coerceAtLeast(0L)
        )
    }

    override fun onCleared() {
        recommendationJob?.cancel()
        normalizationJob?.cancel()
        PlayerManager.peek()?.let { player ->
            if (listenerAttached) player.removeListener(listener)
        }
        super.onCleared()
    }
}
