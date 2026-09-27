package com.egtgpt.musewalk

import android.app.Application
import androidx.annotation.OptIn
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.media3.common.Player
import androidx.media3.common.Timeline
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.ExoPlayer
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
    val favorites: Set<Long> = emptySet(),
    val queue: List<Track> = emptyList(),
    val queueIndex: Int = -1,
    val playbackPositionMs: Long = 0L,
    val playbackDurationMs: Long = 0L,
    val repeatMode: Int = Player.REPEAT_MODE_OFF,
    val shuffleEnabled: Boolean = false,
    val continuousPlayback: Boolean = true,
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

@OptIn(UnstableApi::class)
class MainViewModel(app: Application) : AndroidViewModel(app) {
    private val library = MusicLibrary(app)
    private val stats = StatsStore(app)
    private val favoritesStore = FavoritesStore(app)
    private val replayGain = ReplayGainStore(app)
    private val playbackPrefs = PlaybackPrefsStore(app)
    private val engine = RecommendationEngine(stats)

    private val _ui = MutableStateFlow(
        HomeUiState(
            favorites = favoritesStore.all(),
            repeatMode = playbackPrefs.repeatMode,
            shuffleEnabled = playbackPrefs.shuffleEnabled,
            continuousPlayback = playbackPrefs.continuousPlayback
        )
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

        override fun onTimelineChanged(timeline: Timeline, reason: Int) {
            updatePlaybackState(includeQueue = true)
        }

        override fun onRepeatModeChanged(repeatMode: Int) {
            _ui.value = _ui.value.copy(repeatMode = repeatMode)
        }

        override fun onShuffleModeEnabledChanged(shuffleModeEnabled: Boolean) {
            _ui.value = _ui.value.copy(shuffleEnabled = shuffleModeEnabled)
        }
    }

    private fun ensurePlayer(): ExoPlayer {
        val player = PlayerManager.get(getApplication())
        if (!listenerAttached) {
            player.addListener(listener)
            listenerAttached = true
        }
        applyPlaybackPrefs(player)
        return player
    }

    private fun applyPlaybackPrefs(player: ExoPlayer) {
        player.repeatMode = playbackPrefs.repeatMode
        player.shuffleModeEnabled = playbackPrefs.shuffleEnabled
        player.setPauseAtEndOfMediaItems(!playbackPrefs.continuousPlayback)
    }

    fun loadLibrary() {
        viewModelScope.launch {
            _ui.value = _ui.value.copy(loading = true, error = null)

            val result = runCatching { library.scan() }
            result.onSuccess { tracks ->
                trackById = tracks.associateBy { it.id }

                val instant = tracks.take(20).map {
                    RecommendedTrack(it, 0.0, "最近追加した曲")
                }

                _ui.value = _ui.value.copy(
                    loading = false,
                    tracks = tracks,
                    recommendations = instant,
                    favorites = favoritesStore.all(),
                    repeatMode = playbackPrefs.repeatMode,
                    shuffleEnabled = playbackPrefs.shuffleEnabled,
                    continuousPlayback = playbackPrefs.continuousPlayback,
                    error = null
                )

                PlayerManager.peek()?.let {
                    if (!listenerAttached) {
                        it.addListener(listener)
                        listenerAttached = true
                    }
                    applyPlaybackPrefs(it)
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

        // A300: cap the prepared queue to reduce allocation and MediaItem overhead.
        val before = 12
        val maxQueue = 60
        val start = (originalIndex - before).coerceAtLeast(0)
        val end = (start + maxQueue).coerceAtMost(list.size)
        val queue = list.subList(start, end)
        val queueIndex = originalIndex - start

        viewModelScope.launch {
            val initialVolume = replayGain.volumeFor(track)
            ensurePlayer()
            PlayerManager.play(
                context = getApplication(),
                tracks = queue,
                startIndex = queueIndex,
                initialVolume = initialVolume
            )
            updatePlaybackState(includeQueue = true)
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
        player.seekToNextMediaItem()
        player.play()
    }

    fun previous() {
        val player = PlayerManager.peek() ?: return
        if (player.currentPosition > 5_000L) {
            player.seekTo(0L)
        } else {
            player.seekToPreviousMediaItem()
        }
        player.play()
    }

    fun playQueueIndex(index: Int) {
        val player = PlayerManager.peek() ?: return
        if (index !in 0 until player.mediaItemCount) return
        player.seekTo(index, 0L)
        player.play()
    }

    /**
     * Move a queue item directly after the currently playing track.
     * Manual queue editing disables shuffle so "next" stays deterministic.
     */
    fun playNextQueueItem(index: Int) {
        val player = PlayerManager.peek() ?: return
        if (index !in 0 until player.mediaItemCount) return
        val current = player.currentMediaItemIndex
        if (index == current) return

        disableShuffleForQueueEdit(player)

        val item = player.getMediaItemAt(index)
        player.removeMediaItem(index)
        val updatedCurrent = player.currentMediaItemIndex
        val insertAt = (updatedCurrent + 1).coerceIn(0, player.mediaItemCount)
        player.addMediaItem(insertAt, item)
        updatePlaybackState(includeQueue = true)
    }

    fun moveQueueItem(from: Int, to: Int) {
        val player = PlayerManager.peek() ?: return
        if (from !in 0 until player.mediaItemCount) return
        if (to !in 0 until player.mediaItemCount) return
        if (from == to) return

        disableShuffleForQueueEdit(player)
        player.moveMediaItem(from, to)
        updatePlaybackState(includeQueue = true)
    }

    fun removeQueueItem(index: Int) {
        val player = PlayerManager.peek() ?: return
        if (index !in 0 until player.mediaItemCount) return
        // Keep the currently playing item stable. Users can skip it instead.
        if (index == player.currentMediaItemIndex) return

        disableShuffleForQueueEdit(player)
        player.removeMediaItem(index)
        updatePlaybackState(includeQueue = true)
    }

    private fun disableShuffleForQueueEdit(player: ExoPlayer) {
        if (!player.shuffleModeEnabled) return
        player.shuffleModeEnabled = false
        playbackPrefs.shuffleEnabled = false
        _ui.value = _ui.value.copy(shuffleEnabled = false)
    }

    fun seekTo(positionMs: Long) {
        val player = PlayerManager.peek() ?: return
        val duration = player.duration.takeIf { it > 0L } ?: _ui.value.playbackDurationMs
        player.seekTo(positionMs.coerceIn(0L, duration.coerceAtLeast(0L)))
        updateProgress()
    }

    /**
     * Called only while the full-screen player is visible.
     * 1 Hz is deliberate: smooth enough for a music seekbar, much cheaper on A300.
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

    fun toggleShuffle() {
        val player = ensurePlayer()
        val enabled = !player.shuffleModeEnabled
        player.shuffleModeEnabled = enabled
        playbackPrefs.shuffleEnabled = enabled
        _ui.value = _ui.value.copy(shuffleEnabled = enabled)
    }

    fun cycleRepeatMode() {
        val player = ensurePlayer()
        val next = when (player.repeatMode) {
            Player.REPEAT_MODE_OFF -> Player.REPEAT_MODE_ALL
            Player.REPEAT_MODE_ALL -> Player.REPEAT_MODE_ONE
            else -> Player.REPEAT_MODE_OFF
        }

        if (next != Player.REPEAT_MODE_OFF && !_ui.value.continuousPlayback) {
            setContinuousPlaybackInternal(player, true)
        }

        player.repeatMode = next
        playbackPrefs.repeatMode = next
        _ui.value = _ui.value.copy(repeatMode = next)
    }

    fun toggleContinuousPlayback() {
        val player = ensurePlayer()
        val enabled = !_ui.value.continuousPlayback

        // A paused-at-end player cannot meaningfully repeat automatically.
        if (!enabled && player.repeatMode != Player.REPEAT_MODE_OFF) {
            player.repeatMode = Player.REPEAT_MODE_OFF
            playbackPrefs.repeatMode = Player.REPEAT_MODE_OFF
        }

        setContinuousPlaybackInternal(player, enabled)
        _ui.value = _ui.value.copy(
            continuousPlayback = enabled,
            repeatMode = player.repeatMode
        )
    }

    private fun setContinuousPlaybackInternal(player: ExoPlayer, enabled: Boolean) {
        player.setPauseAtEndOfMediaItems(!enabled)
        playbackPrefs.continuousPlayback = enabled
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
            playbackDurationMs = duration.coerceAtLeast(0L),
            repeatMode = player.repeatMode,
            shuffleEnabled = player.shuffleModeEnabled,
            continuousPlayback = playbackPrefs.continuousPlayback
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
