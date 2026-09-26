package com.egtgpt.musewalk

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import kotlinx.coroutines.Dispatchers
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

    private var attachedPlayer: ExoPlayer? = null
    private var activeTrackId: Long? = null
    private var activeStartedAt: Long = 0L
    private var countedAsFinished = false

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

    fun loadLibrary() {
        viewModelScope.launch {
            _ui.value = _ui.value.copy(loading = true, error = null)

            runCatching { library.scan() }
                .onSuccess { tracks ->
                    val instantRecommendations = tracks.take(20).mapIndexed { index, track ->
                        RecommendedTrack(
                            track = track,
                            score = (20 - index).toDouble(),
                            reason = "最近追加"
                        )
                    }

                    _ui.value = _ui.value.copy(
                        loading = false,
                        tracks = tracks,
                        recommendations = instantRecommendations,
                        error = null
                    )

                    PlayerManager.peek()?.let { attachPlayer(it) }
                    updatePlaybackState()

                    val calculated = withContext(Dispatchers.Default) {
                        engine.recommend(tracks)
                    }

                    if (_ui.value.tracks === tracks || _ui.value.tracks == tracks) {
                        _ui.value = _ui.value.copy(recommendations = calculated)
                    }
                }
                .onFailure { e ->
                    _ui.value = _ui.value.copy(
                        loading = false,
                        error = e.message ?: "曲を読み込めませんでした"
                    )
                }
        }
    }

    private fun attachPlayer(player: ExoPlayer) {
        if (attachedPlayer === player) return
        attachedPlayer?.removeListener(listener)
        attachedPlayer = player
        player.addListener(listener)
    }

    private fun ensurePlayer(): ExoPlayer {
        val existing = attachedPlayer ?: PlayerManager.peek()
        if (existing != null) {
            attachPlayer(existing)
            return existing
        }

        return PlayerManager.get(getApplication<Application>()).also {
            attachPlayer(it)
        }
    }

    fun play(track: Track, source: List<Track> = _ui.value.visibleTracks) {
        ensurePlayer()
        val list = if (source.any { it.id == track.id }) source else _ui.value.tracks
        val index = list.indexOfFirst { it.id == track.id }.coerceAtLeast(0)
        PlayerManager.play(getApplication(), list, index)
    }

    fun playRecommended() {
        val tracks = _ui.value.tracks
        if (tracks.isEmpty()) return

        val ranked = _ui.value.recommendations.map { it.track }
        val unseen = tracks.filter { stats.get(it.id).playCount == 0 }.shuffled()
        val rediscovery = tracks.filter {
            val last = stats.get(it.id).lastPlayedAt
            last > 0L && System.currentTimeMillis() - last > 14L * 86_400_000L
        }.shuffled()

        val smartQueue = buildList {
            addAll(ranked.take(12))
            addAll(unseen.take(4))
            addAll(rediscovery.take(3))
            addAll(ranked.drop(12))
        }.distinctBy { it.id }

        val first = smartQueue.firstOrNull() ?: return
        play(first, smartQueue)
    }

    fun togglePlayPause() {
        val player = attachedPlayer ?: PlayerManager.peek() ?: return
        attachPlayer(player)
        if (player.isPlaying) player.pause() else player.play()
    }

    fun next() {
        val player = attachedPlayer ?: PlayerManager.peek() ?: return
        attachPlayer(player)

        val listened = System.currentTimeMillis() - activeStartedAt
        if (activeTrackId != null && listened in 0 until 45_000) {
            stats.markSkipped(activeTrackId!!, listened)
        }

        player.seekToNextMediaItem()
        player.play()
        refreshRecommendations()
    }

    fun previous() {
        val player = attachedPlayer ?: PlayerManager.peek() ?: return
        attachPlayer(player)
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

        viewModelScope.launch(Dispatchers.Default) {
            val recommendations = engine.recommend(tracks)
            withContext(Dispatchers.Main) {
                _ui.value = _ui.value.copy(recommendations = recommendations)
            }
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
        val player = attachedPlayer ?: PlayerManager.peek()
        val currentId = player?.currentMediaItem?.mediaId?.toLongOrNull()
        val current = _ui.value.tracks.firstOrNull { it.id == currentId }

        _ui.value = _ui.value.copy(
            current = current,
            isPlaying = player?.isPlaying == true
        )
    }

    override fun onCleared() {
        attachedPlayer?.removeListener(listener)
        attachedPlayer = null
        super.onCleared()
    }
}
