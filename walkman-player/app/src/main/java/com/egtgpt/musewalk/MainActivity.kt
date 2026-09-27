package com.egtgpt.musewalk

import android.Manifest
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.media3.common.Player
import java.util.concurrent.TimeUnit

class MainActivity : ComponentActivity() {
    private val viewModel: MainViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MuseWalkTheme {
                MuseWalkApp(viewModel)
            }
        }
    }
}

@Composable
private fun MuseWalkTheme(content: @Composable () -> Unit) {
    val dark = androidx.compose.foundation.isSystemInDarkTheme()
    val compact = isCompactWalkman()
    val light = lightColorScheme(
        primary = Color(0xFF111111),
        onPrimary = Color.White,
        background = Color(0xFFF7F7F9),
        surface = Color.White,
        surfaceVariant = Color(0xFFF0F0F3),
        onSurface = Color(0xFF111113),
        onSurfaceVariant = Color(0xFF6B6B72)
    )
    val darkScheme = darkColorScheme(
        primary = Color.White,
        onPrimary = Color.Black,
        background = Color(0xFF08080A),
        surface = Color(0xFF141416),
        surfaceVariant = Color(0xFF202024),
        onSurface = Color(0xFFF7F7F8),
        onSurfaceVariant = Color(0xFFA6A6AD)
    )
    MaterialTheme(
        colorScheme = if (dark) darkScheme else light,
        typography = Typography(
            headlineLarge = MaterialTheme.typography.headlineLarge.copy(
                fontSize = if (compact) 29.sp else 34.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = (-0.8).sp
            ),
            titleLarge = MaterialTheme.typography.titleLarge.copy(fontWeight = FontWeight.Bold)
        ),
        content = content
    )
}

private enum class MainTab { Home, Library, Stats }

@Composable
private fun isCompactWalkman(): Boolean {
    val width = androidx.compose.ui.platform.LocalConfiguration.current.screenWidthDp
    return remember(width) {
        WalkmanProfile.detect().isA300 || width <= 380
    }
}

@Composable
private fun isShortScreen(): Boolean =
    androidx.compose.ui.platform.LocalConfiguration.current.screenHeightDp < 480

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MuseWalkApp(vm: MainViewModel) {
    val ui by vm.ui.collectAsStateWithLifecycle()
    var tab by remember { mutableStateOf(MainTab.Home) }
    var showNowPlaying by remember { mutableStateOf(false) }
    var showQueue by remember { mutableStateOf(false) }

    val lifecycleOwner = androidx.lifecycle.compose.LocalLifecycleOwner.current
    var appInForeground by remember {
        mutableStateOf(
            lifecycleOwner.lifecycle.currentState.isAtLeast(androidx.lifecycle.Lifecycle.State.STARTED)
        )
    }
    DisposableEffect(lifecycleOwner) {
        val observer = androidx.lifecycle.LifecycleEventObserver { _, _ ->
            appInForeground = lifecycleOwner.lifecycle.currentState
                .isAtLeast(androidx.lifecycle.Lifecycle.State.STARTED)
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    val permission = if (Build.VERSION.SDK_INT >= 33) {
        Manifest.permission.READ_MEDIA_AUDIO
    } else {
        Manifest.permission.READ_EXTERNAL_STORAGE
    }
    val context = androidx.compose.ui.platform.LocalContext.current
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) vm.loadLibrary()
    }

    LaunchedEffect(Unit) {
        if (ContextCompat.checkSelfPermission(context, permission) == android.content.pm.PackageManager.PERMISSION_GRANTED) {
            vm.loadLibrary()
        } else {
            launcher.launch(permission)
        }
    }

    BackHandler(showQueue) { showQueue = false }

    LaunchedEffect(ui.current?.id, ui.isPlaying, appInForeground, showNowPlaying, tab) {
        if (appInForeground && ui.current != null && (showNowPlaying || tab == MainTab.Home)) {
            vm.updateProgress()
            while (ui.isPlaying && appInForeground) {
                kotlinx.coroutines.delay(1_000)
                vm.updateProgress()
            }
        }
    }

    if (showNowPlaying && !showQueue && ui.current != null) {
        BackHandler { showNowPlaying = false }
        CompositionLocalProvider(LocalContentColor provides MaterialTheme.colorScheme.onSurface) {
            NowPlayingScreen(
                track = ui.current!!,
                isPlaying = ui.isPlaying,
                positionMs = ui.playbackPositionMs,
                durationMs = ui.playbackDurationMs,
                isFavorite = ui.current!!.id in ui.favorites,
                repeatMode = ui.repeatMode,
                shuffleEnabled = ui.shuffleEnabled,
                continuousPlayback = ui.continuousPlayback,
                onBack = { showNowPlaying = false },
                onPrevious = vm::previous,
                onToggle = vm::togglePlayPause,
                onNext = vm::next,
                onFavorite = { vm.toggleFavorite(ui.current!!) },
                onSeek = vm::seekTo,
                onQueue = { showQueue = true },
                onShuffle = vm::toggleShuffle,
                onRepeat = vm::cycleRepeatMode,
                onContinuous = vm::toggleContinuousPlayback
            )
        }
        return
    }

    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        bottomBar = {
            Column {
                if (ui.current != null) {
                    MiniPlayer(
                        track = ui.current,
                        isPlaying = ui.isPlaying,
                        onClick = { showQueue = false; showNowPlaying = true },
                        onPrevious = vm::previous,
                        onToggle = vm::togglePlayPause,
                        onNext = vm::next
                    )
                }
                val compact = isCompactWalkman()
                NavigationBar(
                    modifier = Modifier.height(if (compact) 64.dp else 80.dp),
                    containerColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.96f)
                ) {
                    NavigationBarItem(
                        selected = !showQueue && tab == MainTab.Home,
                        onClick = { showQueue = false; tab = MainTab.Home },
                        icon = { Icon(Icons.Default.Home, null, Modifier.size(if (compact) 22.dp else 24.dp)) },
                        label = { Text("ホーム", fontSize = if (compact) 10.sp else 12.sp) }
                    )
                    NavigationBarItem(
                        selected = !showQueue && tab == MainTab.Library,
                        onClick = { showQueue = false; tab = MainTab.Library },
                        icon = { Icon(Icons.Default.LibraryMusic, null, Modifier.size(if (compact) 22.dp else 24.dp)) },
                        label = { Text("ライブラリ", fontSize = if (compact) 10.sp else 12.sp) }
                    )
                    NavigationBarItem(
                        selected = !showQueue && tab == MainTab.Stats,
                        onClick = { showQueue = false; tab = MainTab.Stats },
                        icon = { Icon(Icons.Default.BarChart, null, Modifier.size(if (compact) 22.dp else 24.dp)) },
                        label = { Text("統計", fontSize = if (compact) 10.sp else 12.sp) }
                    )
                }
            }
        }
    ) { padding ->
        when {
            showQueue -> QueueScreen(
                queue = ui.queue,
                currentIndex = ui.queueIndex,
                repeatMode = ui.repeatMode,
                shuffleEnabled = ui.shuffleEnabled,
                continuousPlayback = ui.continuousPlayback,
                onBack = { showQueue = false },
                onSelect = {
                    vm.playQueueIndex(it)
                    showQueue = false
                },
                onPlayNext = vm::playNextQueueItem,
                onMove = vm::moveQueueItem,
                onRemove = vm::removeQueueItem,
                onShuffle = vm::toggleShuffle,
                onRepeat = vm::cycleRepeatMode,
                onContinuous = vm::toggleContinuousPlayback,
                modifier = Modifier.padding(padding)
            )

            ui.error != null -> PermissionError(
                text = ui.error ?: "読み込みエラー",
                modifier = Modifier.padding(padding),
                onRetry = { launcher.launch(permission) }
            )

            else -> when (tab) {
                MainTab.Home -> HomeScreen(
                    ui = ui,
                    vm = vm,
                    onOpenQueue = { showQueue = true },
                    onSelectGenre = { genre ->
                        vm.search("")
                        vm.selectGenre(genre)
                        tab = MainTab.Library
                    },
                    modifier = Modifier.padding(padding)
                )
                MainTab.Library -> LibraryScreen(ui, vm, Modifier.padding(padding))
                MainTab.Stats -> StatsScreen(ui, vm, Modifier.padding(padding))
            }
        }
    }

}

@Composable
private fun HomeScreen(
    ui: HomeUiState,
    vm: MainViewModel,
    onOpenQueue: () -> Unit,
    onSelectGenre: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    val compact = isCompactWalkman()
    val genres = remember(ui.tracks) { ui.genres }
    val genreCounts = remember(ui.tracks) { ui.tracks.groupingBy { it.genre }.eachCount() }
    val favoriteTracks = remember(ui.tracks, ui.favorites) {
        ui.tracks.filter { it.id in ui.favorites }.take(12)
    }
    val recentFavorites = remember(ui.tracks, ui.recommendations) {
        ui.recommendations.filter { it.reason.contains("最後まで") || it.reason.contains("履歴") }.take(8)
    }
    val rediscovery = remember(ui.recommendations) {
        ui.recommendations.filter { it.reason.contains("久しぶり") || it.reason.contains("あまり") }.take(8)
    }

    LazyColumn(
        modifier = modifier.fillMaxSize(),
        contentPadding = PaddingValues(
            horizontal = if (compact) 14.dp else 20.dp,
            vertical = if (compact) 10.dp else 16.dp
        ),
        verticalArrangement = Arrangement.spacedBy(if (compact) 16.dp else 24.dp)
    ) {
        if (!compact) {
            item {
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text("MuseWalk", style = MaterialTheme.typography.headlineLarge)
                    Text(
                        "聴くほど、あなた向けに。",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = if (compact) 13.sp else 14.sp
                    )
                }
            }
        }

        if (ui.loading) {
            item {
                LinearProgressIndicator(
                    modifier = Modifier.fillMaxWidth().height(2.dp)
                )
            }
        }

        if (genres.isNotEmpty()) {
            item {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    SectionTitle("ジャンル別に聴く")
                    Spacer(Modifier.weight(1f))
                    if (ui.current != null) {
                        IconButton(onClick = onOpenQueue, modifier = Modifier.size(40.dp)) {
                            Icon(Icons.Default.QueueMusic, contentDescription = "再生キュー")
                        }
                    }
                }
                Spacer(Modifier.height(if (compact) 2.dp else 8.dp))
                LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    items(genres) { genre ->
                        AssistChip(
                            onClick = { onSelectGenre(genre) },
                            label = {
                                Text(genre + " · " + (genreCounts[genre] ?: 0))
                            },
                            leadingIcon = { Icon(Icons.Default.GraphicEq, null, Modifier.size(18.dp)) }
                        )
                    }
                }
            }
        }

        item {
            HeroRecommendation(
                item = ui.recommendations.firstOrNull(),
                onPlay = vm::playRecommended
            )
        }

        if (favoriteTracks.isNotEmpty()) {
            item {
                SectionTitle("お気に入り")
                Spacer(Modifier.height(10.dp))
                TrackCarousel(
                    favoriteTracks.map { RecommendedTrack(it, 0.0, "お気に入り") }
                ) { item ->
                    vm.play(item.track, favoriteTracks)
                }
            }
        }

        if (recentFavorites.isNotEmpty()) {
            item {
                SectionTitle("最近ハマってる")
                Spacer(Modifier.height(12.dp))
                TrackCarousel(recentFavorites) { vm.play(it.track, recentFavorites.map { r -> r.track }) }
            }
        }

        if (rediscovery.isNotEmpty()) {
            item {
                SectionTitle("久しぶりに聴く？")
                Spacer(Modifier.height(12.dp))
                TrackCarousel(rediscovery) { vm.play(it.track, rediscovery.map { r -> r.track }) }
            }
        }

        item {
            SectionTitle("最近追加")
            Spacer(Modifier.height(6.dp))
        }

        items(ui.tracks.take(8), key = { it.id }) { track ->
            TrackRow(track = track, subtitle = track.artist, onClick = { vm.play(track, ui.tracks) })
        }

        item { Spacer(Modifier.height(24.dp)) }
    }
}

@Composable
private fun A300AudioCard() {
    val context = androidx.compose.ui.platform.LocalContext.current
    val profile = remember { WalkmanProfile.detect() }
    if (!profile.isA300) return

    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(20.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface
        )
    ) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Default.Headphones, null, Modifier.size(22.dp))
                Spacer(Modifier.width(8.dp))
                Column(Modifier.weight(1f)) {
                    Text("A300 × EarFun Air Pro 4", fontWeight = FontWeight.Bold)
                    Text(
                        "加工しすぎず、自動補完と音量統一を優先",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 11.sp
                    )
                }
            }

            Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                AudioSettingLine("Bluetooth", "LDAC")
                AudioSettingLine("音源補完", "DSEE Ultimate ON")
                AudioSettingLine("曲間音量", "ReplayGain/R128 + Sony補正")
                AudioSettingLine("EQ / ピッチ", "変更しない")
            }

            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilledTonalButton(
                    onClick = { WalkmanProfile.openBluetoothSettings(context) },
                    modifier = Modifier.weight(1f),
                    contentPadding = PaddingValues(horizontal = 8.dp, vertical = 8.dp)
                ) {
                    Icon(Icons.Default.Bluetooth, null, Modifier.size(18.dp))
                    Spacer(Modifier.width(5.dp))
                    Text("LDAC確認", fontSize = 12.sp)
                }
                OutlinedButton(
                    onClick = { WalkmanProfile.openSoundSettings(context) },
                    modifier = Modifier.weight(1f),
                    contentPadding = PaddingValues(horizontal = 8.dp, vertical = 8.dp)
                ) {
                    Icon(Icons.Default.Tune, null, Modifier.size(18.dp))
                    Spacer(Modifier.width(5.dp))
                    Text("音質設定", fontSize = 12.sp)
                }
            }
        }
    }
}

@Composable
private fun AudioSettingLine(label: String, value: String) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(
            label,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            fontSize = 11.sp,
            modifier = Modifier.width(72.dp)
        )
        Text(value, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
private fun HeroRecommendation(item: RecommendedTrack?, onPlay: () -> Unit) {
    val compact = isCompactWalkman()
    val short = isShortScreen()
    val track = item?.track
    if (short) {
        Surface(
            modifier = Modifier.fillMaxWidth(),
            color = MaterialTheme.colorScheme.surfaceVariant,
            shape = RoundedCornerShape(18.dp)
        ) {
            Row(
                Modifier.padding(10.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                if (track != null) {
                    Artwork(track, Modifier.size(48.dp))
                    Spacer(Modifier.width(10.dp))
                }
                Column(Modifier.weight(1f)) {
                    Text("今日のおすすめ", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
                    Text(
                        track?.title ?: "曲を読み込み中",
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        fontSize = 13.sp,
                        fontWeight = FontWeight.SemiBold
                    )
                }
                IconButton(onClick = onPlay, enabled = track != null, modifier = Modifier.size(48.dp)) {
                    Icon(Icons.Default.PlayArrow, contentDescription = "おすすめを再生")
                }
            }
        }
        return
    }
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(if (compact) 24.dp else 30.dp),
        colors = CardDefaults.cardColors(containerColor = Color.Transparent)
    ) {
        Box(
            Modifier
                .fillMaxWidth()
                .height(if (compact) 220.dp else 250.dp)
                .background(
                    Brush.linearGradient(
                        listOf(Color(0xFF232526), Color(0xFF5D5D62), Color(0xFF1B1B1D))
                    )
                )
                .padding(if (compact) 16.dp else 24.dp)
        ) {
            Column(
                Modifier.fillMaxSize(),
                verticalArrangement = Arrangement.SpaceBetween
            ) {
                Surface(
                    color = Color.White.copy(alpha = 0.16f),
                    shape = RoundedCornerShape(20.dp)
                ) {
                    Text(
                        "今日のおすすめ",
                        color = Color.White,
                        modifier = Modifier.padding(
                            horizontal = if (compact) 10.dp else 12.dp,
                            vertical = if (compact) 5.dp else 7.dp
                        ),
                        fontWeight = FontWeight.SemiBold
                    )
                }
                Column {
                    Text(
                        track?.title ?: "曲を読み込むとおすすめが出ます",
                        color = Color.White,
                        fontSize = if (compact) 22.sp else 27.sp,
                        fontWeight = FontWeight.Bold,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis
                    )
                    if (track != null) {
                        Spacer(Modifier.height(4.dp))
                        Text(
                            track.artist,
                            color = Color.White.copy(alpha = 0.72f),
                            fontSize = if (compact) 13.sp else 14.sp,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                        Text(
                            item.reason,
                            color = Color.White.copy(alpha = 0.62f),
                            fontSize = if (compact) 11.sp else 13.sp,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                        Spacer(Modifier.height(if (compact) 9.dp else 18.dp))
                        FilledTonalButton(
                            onClick = onPlay,
                            colors = ButtonDefaults.filledTonalButtonColors(
                                containerColor = Color.White,
                                contentColor = Color.Black
                            )
                        ) {
                            Icon(Icons.Default.PlayArrow, null)
                            Spacer(Modifier.width(6.dp))
                            Text("再生")
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun TrackCarousel(items: List<RecommendedTrack>, onClick: (RecommendedTrack) -> Unit) {
    val compact = isCompactWalkman()
    val itemSize = if (compact) 116.dp else 148.dp
    LazyRow(horizontalArrangement = Arrangement.spacedBy(if (compact) 10.dp else 14.dp)) {
        items(items, key = { it.track.id }) { item ->
            Column(
                Modifier
                    .width(itemSize)
                    .clickable { onClick(item) }
            ) {
                Artwork(item.track, Modifier.size(itemSize))
                Spacer(Modifier.height(if (compact) 6.dp else 9.dp))
                Text(
                    item.track.title,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
                Text(
                    item.track.artist,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = if (compact) 11.sp else 13.sp,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun LibraryScreen(ui: HomeUiState, vm: MainViewModel, modifier: Modifier = Modifier) {
    val compact = isCompactWalkman()
    val short = isShortScreen()
    val genres = remember(ui.tracks) { ui.genres }
    val genreCounts = remember(ui.tracks) { ui.tracks.groupingBy { it.genre }.eachCount() }
    val visibleTracks = remember(ui.tracks, ui.selectedGenre, ui.searchQuery) { ui.visibleTracks }

    LazyColumn(
        modifier = modifier.fillMaxSize(),
        contentPadding = PaddingValues(bottom = 16.dp)
    ) {
        item {
            Column(
                Modifier
                    .fillMaxWidth()
                    .padding(
                        horizontal = if (compact) 14.dp else 20.dp,
                        vertical = if (short) 4.dp else if (compact) 10.dp else 16.dp
                    )
            ) {
                if (short) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("曲", fontSize = 18.sp, fontWeight = FontWeight.Bold)
                        Spacer(Modifier.width(10.dp))
                        OutlinedTextField(
                            value = ui.searchQuery,
                            onValueChange = vm::search,
                            modifier = Modifier.weight(1f).height(48.dp),
                            singleLine = true,
                            shape = RoundedCornerShape(16.dp),
                            textStyle = androidx.compose.ui.text.TextStyle(fontSize = 13.sp),
                            placeholder = { Text("曲やアーティストを検索", fontSize = 12.sp) },
                            leadingIcon = { Icon(Icons.Default.Search, null, Modifier.size(19.dp)) }
                        )
                    }
                } else {
                    Text(
                        "ライブラリ",
                        style = MaterialTheme.typography.headlineLarge,
                        fontSize = if (compact) 25.sp else MaterialTheme.typography.headlineLarge.fontSize
                    )
                    Spacer(Modifier.height(if (compact) 8.dp else 14.dp))
                    OutlinedTextField(
                        value = ui.searchQuery,
                        onValueChange = vm::search,
                        modifier = Modifier.fillMaxWidth().height(if (compact) 56.dp else 64.dp),
                        singleLine = true,
                        shape = RoundedCornerShape(18.dp),
                        textStyle = androidx.compose.ui.text.TextStyle(fontSize = if (compact) 14.sp else 16.sp),
                        placeholder = {
                            Text(
                                "曲やアーティストを検索",
                                fontSize = if (compact) 13.sp else 15.sp,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis
                            )
                        },
                        leadingIcon = { Icon(Icons.Default.Search, null) }
                    )
                }
                Spacer(Modifier.height(if (short) 2.dp else if (compact) 8.dp else 12.dp))
                LazyRow(horizontalArrangement = Arrangement.spacedBy(if (compact) 6.dp else 8.dp)) {
                    item {
                        FilterChip(
                            selected = ui.selectedGenre == null,
                            onClick = { vm.selectGenre(null) },
                            label = { Text("すべて") }
                        )
                    }
                    items(genres) { genre ->
                        FilterChip(
                            selected = ui.selectedGenre == genre,
                            onClick = { vm.selectGenre(genre) },
                            label = { Text(genre + " · " + (genreCounts[genre] ?: 0)) }
                        )
                    }
                }
                if (!short) {
                    Spacer(Modifier.height(8.dp))
                    Text(
                        (ui.selectedGenre ?: "すべて") + " ・ " + visibleTracks.size + "曲",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = if (compact) 12.sp else 13.sp
                    )
                }
            }
        }

        item {
            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.45f))
        }

        if (visibleTracks.isEmpty()) {
            item {
                Text(
                    "この条件に合う曲がありません。",
                    modifier = Modifier.padding(horizontal = if (compact) 14.dp else 20.dp, vertical = 24.dp),
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }

        items(visibleTracks, key = { it.id }) { track ->
            TrackRow(
                track = track,
                subtitle = track.artist + "  ·  " + track.genre,
                onClick = { vm.play(track, visibleTracks) }
            )
        }

        item { Spacer(Modifier.height(24.dp)) }
    }
}
@Composable
private fun StatsScreen(ui: HomeUiState, vm: MainViewModel, modifier: Modifier = Modifier) {
    val compact = isCompactWalkman()
    val ranked = remember(ui.tracks, ui.recommendations) {
        ui.tracks.map { it to vm.statsFor(it) }.sortedByDescending { it.second.playCount }
    }
    val totalPlays = ranked.sumOf { it.second.playCount }
    val totalMs = ranked.sumOf { it.second.totalListenMs }

    LazyColumn(
        modifier.fillMaxSize(),
        contentPadding = PaddingValues(
            horizontal = if (compact) 14.dp else 20.dp,
            vertical = if (compact) 10.dp else 16.dp
        ),
        verticalArrangement = Arrangement.spacedBy(if (compact) 12.dp else 18.dp)
    ) {
        item { Text("統計", style = MaterialTheme.typography.headlineLarge) }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                MetricCard("再生", totalPlays.toString(), Modifier.weight(1f))
                MetricCard("再生時間", formatLongDuration(totalMs), Modifier.weight(1f))
            }
        }
        item {
            Text(
                "再生履歴はこの端末内だけに保存されます。",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 13.sp
            )
        }
        item {
            A300AudioCard()
        }
        item {
            BatteryPolicyCard()
        }
        item { SectionTitle("よく聴く曲") }
        items(ranked.filter { it.second.playCount > 0 }.take(20), key = { it.first.id }) { (track, stats) ->
            TrackRow(
                track = track,
                subtitle = "${stats.playCount}回 · 完走 ${(stats.completionRate * 100).toInt()}%",
                onClick = { vm.play(track, ui.tracks) }
            )
        }
        if (totalPlays == 0) {
            item {
                Text(
                    "まだ履歴がありません。何曲か聴くと、ここにランキングが育っていきます。",
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

@Composable
private fun MetricCard(label: String, value: String, modifier: Modifier = Modifier) {
    val compact = isCompactWalkman()
    Card(
        modifier = modifier,
        shape = RoundedCornerShape(if (compact) 18.dp else 24.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
    ) {
        Column(Modifier.padding(if (compact) 13.dp else 18.dp)) {
            Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
            Spacer(Modifier.height(8.dp))
            Text(value, fontSize = if (compact) 20.sp else 24.sp, fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
private fun TrackRow(track: Track, subtitle: String, onClick: () -> Unit) {
    val compact = isCompactWalkman()
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(if (compact) 14.dp else 18.dp))
            .clickable(onClick = onClick)
            .padding(if (compact) 5.dp else 8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Artwork(track, Modifier.size(if (compact) 50.dp else 58.dp))
        Spacer(Modifier.width(if (compact) 9.dp else 12.dp))
        Column(Modifier.weight(1f)) {
            Text(track.title, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(
                subtitle,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = if (compact) 11.5.sp else 13.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
        }
        Text(
            formatDuration(track.durationMs),
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            fontSize = 12.sp
        )
    }
}

@Composable
private fun Artwork(track: Track, modifier: Modifier = Modifier) {
    val color = remember(track.genre) {
        when (track.genre) {
            "ボカロ" -> Color(0xFF2F8F88)
            "アニメ・ゲーム" -> Color(0xFF66519C)
            "洋楽" -> Color(0xFF3D5FA8)
            "J-POP" -> Color(0xFFB54E70)
            "ポップ" -> Color(0xFFB54E70)
            "ロック" -> Color(0xFFB14D4D)
            "ジャズ" -> Color(0xFF397B86)
            "ヒップホップ", "R&B・ソウル" -> Color(0xFF6A558D)
            "クラシック" -> Color(0xFF97764B)
            "BGM" -> Color(0xFF4D5DA7)
            "ジャンル未設定" -> Color(0xFF686D78)
            else -> Color(0xFF4D5361)
        }
    }
    Box(
        modifier
            .clip(RoundedCornerShape(15.dp))
            .background(color),
        contentAlignment = Alignment.Center
    ) {
        Text(
            track.title.take(1).uppercase(),
            color = Color.White.copy(alpha = 0.92f),
            fontSize = 25.sp,
            fontWeight = FontWeight.Bold
        )
    }
}

@Composable
private fun MiniPlayer(
    track: Track?,
    isPlaying: Boolean,
    onClick: () -> Unit,
    onPrevious: () -> Unit,
    onToggle: () -> Unit,
    onNext: () -> Unit
) {
    if (track == null) return
    val compact = isCompactWalkman()
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = if (compact) 6.dp else 10.dp, vertical = 3.dp),
        shape = RoundedCornerShape(if (compact) 16.dp else 20.dp),
        color = MaterialTheme.colorScheme.surfaceVariant,
        contentColor = MaterialTheme.colorScheme.onSurface,
        tonalElevation = 2.dp
    ) {
        Row(
            Modifier.padding(horizontal = 5.dp, vertical = 3.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Row(
                modifier = Modifier
                    .weight(1f)
                    .heightIn(min = 48.dp)
                    .clip(RoundedCornerShape(12.dp))
                    .clickable(onClick = onClick),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Artwork(track, Modifier.size(if (compact) 38.dp else 42.dp))
                Spacer(Modifier.width(8.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        track.title,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        fontSize = if (compact) 12.sp else 14.sp,
                        fontWeight = FontWeight.SemiBold
                    )
                    Text(
                        track.artist,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = if (compact) 10.sp else 12.sp
                    )
                }
            }
            IconButton(onClick = onPrevious, modifier = Modifier.size(48.dp)) {
                Icon(Icons.Default.SkipPrevious, contentDescription = "前の曲", modifier = Modifier.size(24.dp))
            }
            FilledIconButton(
                onClick = onToggle,
                modifier = Modifier.size(48.dp),
                shape = CircleShape
            ) {
                Icon(
                    if (isPlaying) Icons.Default.Pause else Icons.Default.PlayArrow,
                    contentDescription = if (isPlaying) "一時停止" else "再生",
                    modifier = Modifier.size(24.dp)
                )
            }
            IconButton(onClick = onNext, modifier = Modifier.size(48.dp)) {
                Icon(Icons.Default.SkipNext, contentDescription = "次の曲", modifier = Modifier.size(24.dp))
            }
        }
    }
}

@Composable
private fun NowPlayingScreen(
    track: Track,
    isPlaying: Boolean,
    positionMs: Long,
    durationMs: Long,
    isFavorite: Boolean,
    repeatMode: Int,
    shuffleEnabled: Boolean,
    continuousPlayback: Boolean,
    onBack: () -> Unit,
    onPrevious: () -> Unit,
    onToggle: () -> Unit,
    onNext: () -> Unit,
    onFavorite: () -> Unit,
    onSeek: (Long) -> Unit,
    onQueue: () -> Unit,
    onShuffle: () -> Unit,
    onRepeat: () -> Unit,
    onContinuous: () -> Unit
) {
    val compact = isCompactWalkman()
    var dragging by remember(track.id) { mutableStateOf(false) }
    var dragPosition by remember(track.id) { mutableFloatStateOf(positionMs.toFloat()) }

    LaunchedEffect(positionMs, dragging) {
        if (!dragging) dragPosition = positionMs.toFloat()
    }

    if (isShortScreen()) {
        ShortNowPlayingScreen(
            track = track,
            isPlaying = isPlaying,
            positionMs = positionMs,
            durationMs = durationMs,
            isFavorite = isFavorite,
            repeatMode = repeatMode,
            shuffleEnabled = shuffleEnabled,
            continuousPlayback = continuousPlayback,
            onBack = onBack,
            onPrevious = onPrevious,
            onToggle = onToggle,
            onNext = onNext,
            onFavorite = onFavorite,
            onSeek = onSeek,
            onQueue = onQueue,
            onShuffle = onShuffle,
            onRepeat = onRepeat,
            onContinuous = onContinuous
        )
        return
    }

    BoxWithConstraints(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .statusBarsPadding()
            .navigationBarsPadding()
    ) {
        val artworkSize = if (compact) {
            minOf(maxWidth * 0.72f, maxHeight * 0.34f)
        } else {
            minOf(maxWidth * 0.70f, maxHeight * 0.34f)
        }

        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(horizontal = if (compact) 16.dp else 28.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(if (compact) 46.dp else 56.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                IconButton(onClick = onBack, modifier = Modifier.size(48.dp)) {
                    Icon(
                        Icons.Default.KeyboardArrowDown,
                        contentDescription = "閉じる",
                        modifier = Modifier.size(30.dp)
                    )
                }
                Spacer(Modifier.weight(1f))
                Text(
                    "再生中",
                    fontSize = if (compact) 12.sp else 14.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontWeight = FontWeight.SemiBold
                )
                Spacer(Modifier.weight(1f))
                IconButton(onClick = onQueue, modifier = Modifier.size(48.dp)) {
                    Icon(
                        Icons.Default.QueueMusic,
                        contentDescription = "再生キュー",
                        modifier = Modifier.size(24.dp)
                    )
                }
            }

            Spacer(Modifier.height(if (compact) 2.dp else 12.dp))

            Artwork(
                track,
                Modifier
                    .size(artworkSize)
                    .clip(RoundedCornerShape(if (compact) 20.dp else 30.dp))
            )

            Spacer(Modifier.height(if (compact) 9.dp else 24.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(Modifier.weight(1f)) {
                    Text(
                        text = track.title,
                        fontSize = if (compact) 17.sp else 24.sp,
                        lineHeight = if (compact) 20.sp else 29.sp,
                        fontWeight = FontWeight.Bold,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis
                    )
                    Spacer(Modifier.height(2.dp))
                    Text(
                        text = track.artist,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = if (compact) 12.sp else 15.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                }
                IconButton(onClick = onFavorite, modifier = Modifier.size(48.dp)) {
                    Icon(
                        if (isFavorite) Icons.Default.Favorite else Icons.Default.FavoriteBorder,
                        contentDescription = if (isFavorite) "お気に入り解除" else "お気に入り",
                        modifier = Modifier.size(24.dp)
                    )
                }
            }

            Spacer(Modifier.height(if (compact) 2.dp else 10.dp))

            val safeDuration = durationMs.coerceAtLeast(1L)
            Slider(
                value = if (dragging) {
                    dragPosition
                } else {
                    positionMs.coerceIn(0L, safeDuration).toFloat()
                },
                onValueChange = {
                    dragging = true
                    dragPosition = it
                },
                onValueChangeFinished = {
                    onSeek(dragPosition.toLong())
                    dragging = false
                },
                valueRange = 0f..safeDuration.toFloat(),
                modifier = Modifier
                    .fillMaxWidth()
                    .height(if (compact) 32.dp else 42.dp)
            )

            Row(Modifier.fillMaxWidth()) {
                Text(
                    formatDuration(
                        (if (dragging) dragPosition.toLong() else positionMs).coerceAtLeast(0L)
                    ),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 10.sp
                )
                Spacer(Modifier.weight(1f))
                Text(
                    formatDuration(durationMs),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 10.sp
                )
            }

            Spacer(Modifier.weight(1f))

            PlayerTransport(
                isPlaying = isPlaying,
                repeatMode = repeatMode,
                shuffleEnabled = shuffleEnabled,
                onPrevious = onPrevious,
                onToggle = onToggle,
                onNext = onNext,
                onShuffle = onShuffle,
                onRepeat = onRepeat,
                compact = compact
            )

            FilterChip(
                selected = continuousPlayback,
                onClick = onContinuous,
                label = { Text("連続再生") },
                leadingIcon = {
                    Icon(Icons.Default.PlaylistPlay, contentDescription = null, Modifier.size(18.dp))
                }
            )

            Text(
                text = track.genre,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = if (compact) 10.sp else 12.sp,
                maxLines = 1
            )

            Spacer(Modifier.height(if (compact) 5.dp else 14.dp))
        }
    }
}

@Composable
private fun PlayerTransport(
    isPlaying: Boolean,
    repeatMode: Int,
    shuffleEnabled: Boolean,
    onPrevious: () -> Unit,
    onToggle: () -> Unit,
    onNext: () -> Unit,
    onShuffle: () -> Unit,
    onRepeat: () -> Unit,
    compact: Boolean
) {
    Row(
        modifier = Modifier.fillMaxWidth().height(if (compact) 62.dp else 78.dp),
        horizontalArrangement = Arrangement.SpaceEvenly,
        verticalAlignment = Alignment.CenterVertically
    ) {
        TransportModeButton(
            icon = Icons.Default.Shuffle,
            label = if (shuffleEnabled) "シャッフルを解除" else "シャッフルを有効にする",
            active = shuffleEnabled,
            onClick = onShuffle
        )
        IconButton(onClick = onPrevious, modifier = Modifier.size(48.dp)) {
            Icon(Icons.Default.SkipPrevious, contentDescription = "前の曲", modifier = Modifier.size(28.dp))
        }
        FilledIconButton(
            onClick = onToggle,
            modifier = Modifier.size(if (compact) 58.dp else 68.dp),
            shape = CircleShape
        ) {
            Icon(
                if (isPlaying) Icons.Default.Pause else Icons.Default.PlayArrow,
                contentDescription = if (isPlaying) "一時停止" else "再生",
                modifier = Modifier.size(if (compact) 30.dp else 36.dp)
            )
        }
        IconButton(onClick = onNext, modifier = Modifier.size(48.dp)) {
            Icon(Icons.Default.SkipNext, contentDescription = "次の曲", modifier = Modifier.size(28.dp))
        }
        TransportModeButton(
            icon = if (repeatMode == Player.REPEAT_MODE_ONE) Icons.Default.RepeatOne else Icons.Default.Repeat,
            label = when (repeatMode) {
                Player.REPEAT_MODE_ALL -> "全曲リピート、次は1曲リピート"
                Player.REPEAT_MODE_ONE -> "1曲リピート、次はオフ"
                else -> "リピートを有効にする"
            },
            active = repeatMode != Player.REPEAT_MODE_OFF,
            onClick = onRepeat
        )
    }
}

@Composable
private fun TransportModeButton(
    icon: ImageVector,
    label: String,
    active: Boolean,
    onClick: () -> Unit
) {
    IconButton(
        onClick = onClick,
        modifier = Modifier
            .size(48.dp)
            .clip(CircleShape)
            .background(
                if (active) MaterialTheme.colorScheme.primary.copy(alpha = 0.14f) else Color.Transparent
            )
    ) {
        Icon(
            icon,
            contentDescription = label,
            tint = if (active) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.size(24.dp)
        )
    }
}

@Composable
private fun ShortNowPlayingScreen(
    track: Track,
    isPlaying: Boolean,
    positionMs: Long,
    durationMs: Long,
    isFavorite: Boolean,
    repeatMode: Int,
    shuffleEnabled: Boolean,
    continuousPlayback: Boolean,
    onBack: () -> Unit,
    onPrevious: () -> Unit,
    onToggle: () -> Unit,
    onNext: () -> Unit,
    onFavorite: () -> Unit,
    onSeek: (Long) -> Unit,
    onQueue: () -> Unit,
    onShuffle: () -> Unit,
    onRepeat: () -> Unit,
    onContinuous: () -> Unit
) {
    var dragging by remember(track.id) { mutableStateOf(false) }
    var dragPosition by remember(track.id) { mutableFloatStateOf(positionMs.toFloat()) }
    LaunchedEffect(positionMs, dragging) {
        if (!dragging) dragPosition = positionMs.toFloat()
    }

    Column(
        Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .statusBarsPadding()
            .navigationBarsPadding()
            .padding(horizontal = 12.dp)
    ) {
        Row(
            Modifier.fillMaxWidth().height(44.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            IconButton(onClick = onBack, modifier = Modifier.size(44.dp)) {
                Icon(Icons.Default.KeyboardArrowDown, contentDescription = "閉じる")
            }
            Text("再生中", fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.weight(1f))
            IconButton(onClick = onFavorite, modifier = Modifier.size(44.dp)) {
                Icon(
                    if (isFavorite) Icons.Default.Favorite else Icons.Default.FavoriteBorder,
                    contentDescription = if (isFavorite) "お気に入り解除" else "お気に入り"
                )
            }
            IconButton(onClick = onQueue, modifier = Modifier.size(44.dp)) {
                Icon(Icons.Default.QueueMusic, contentDescription = "再生キュー")
            }
        }

        Row(
            Modifier.fillMaxWidth().weight(1f),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Artwork(track, Modifier.size(92.dp))
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    track.title,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                    fontSize = 16.sp,
                    fontWeight = FontWeight.Bold
                )
                Text(
                    track.artist,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 12.sp
                )
                val safeDuration = durationMs.coerceAtLeast(1L)
                Slider(
                    enabled = durationMs > 0L,
                    value = if (dragging) dragPosition else positionMs.coerceIn(0L, safeDuration).toFloat(),
                    onValueChange = { dragging = true; dragPosition = it },
                    onValueChangeFinished = {
                        if (durationMs > 0L) onSeek(dragPosition.toLong())
                        dragging = false
                    },
                    valueRange = 0f..safeDuration.toFloat(),
                    modifier = Modifier.fillMaxWidth().height(34.dp)
                )
                Row(Modifier.fillMaxWidth()) {
                    Text(formatDuration(if (dragging) dragPosition.toLong() else positionMs), fontSize = 10.sp)
                    Spacer(Modifier.weight(1f))
                    Text(formatDuration(durationMs), fontSize = 10.sp)
                }
            }
        }

        PlayerTransport(
            isPlaying = isPlaying,
            repeatMode = repeatMode,
            shuffleEnabled = shuffleEnabled,
            onPrevious = onPrevious,
            onToggle = onToggle,
            onNext = onNext,
            onShuffle = onShuffle,
            onRepeat = onRepeat,
            compact = true
        )

        Row(Modifier.fillMaxWidth().height(44.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(
                track.genre,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 11.sp,
                maxLines = 1,
                modifier = Modifier.weight(1f)
            )
            TextButton(onClick = onContinuous) {
                Icon(
                    Icons.Default.PlaylistPlay,
                    contentDescription = null,
                    tint = if (continuousPlayback) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.size(18.dp)
                )
                Spacer(Modifier.width(4.dp))
                Text(if (continuousPlayback) "連続再生 ON" else "連続再生 OFF", fontSize = 11.sp)
            }
        }
    }
}

@Composable
private fun PlaybackModeButton(
    icon: ImageVector,
    label: String,
    active: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    val color = if (active) {
        MaterialTheme.colorScheme.primary
    } else {
        MaterialTheme.colorScheme.onSurfaceVariant
    }
    val shape = RoundedCornerShape(14.dp)

    Column(
        modifier = modifier
            .heightIn(min = 52.dp)
            .clip(shape)
            .background(
                if (active) MaterialTheme.colorScheme.primary.copy(alpha = 0.10f) else Color.Transparent,
                shape
            )
            .clickable(onClick = onClick)
            .padding(horizontal = 2.dp, vertical = 5.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Icon(
            icon,
            contentDescription = label,
            tint = color,
            modifier = Modifier.size(21.dp)
        )
        Text(
            label,
            color = color,
            fontSize = 10.sp,
            maxLines = 1
        )
    }
}

@Composable
private fun QueueScreen(
    queue: List<Track>,
    currentIndex: Int,
    repeatMode: Int,
    shuffleEnabled: Boolean,
    continuousPlayback: Boolean,
    onBack: () -> Unit,
    onSelect: (Int) -> Unit,
    onPlayNext: (Int) -> Unit,
    onMove: (Int, Int) -> Unit,
    onRemove: (Int) -> Unit,
    onShuffle: () -> Unit,
    onRepeat: () -> Unit,
    onContinuous: () -> Unit,
    modifier: Modifier = Modifier
) {
    val compact = isCompactWalkman()

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .height(if (compact) 50.dp else 58.dp)
                .padding(horizontal = 6.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            IconButton(onClick = onBack, modifier = Modifier.size(48.dp)) {
                Icon(Icons.Default.ArrowBack, contentDescription = "戻る")
            }
            Text(
                "再生キュー",
                style = MaterialTheme.typography.titleLarge,
                fontSize = if (compact) 19.sp else 22.sp
            )
            Spacer(Modifier.weight(1f))
            Text(
                queue.size.toString() + "曲",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 11.sp
            )
            Spacer(Modifier.width(8.dp))
        }

        HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.45f))

        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 8.dp, vertical = 4.dp),
            horizontalArrangement = Arrangement.spacedBy(4.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            PlaybackModeButton(
                icon = Icons.Default.Shuffle,
                label = "シャッフル",
                active = shuffleEnabled,
                modifier = Modifier.weight(1f),
                onClick = onShuffle
            )
            PlaybackModeButton(
                icon = if (repeatMode == Player.REPEAT_MODE_ONE) {
                    Icons.Default.RepeatOne
                } else {
                    Icons.Default.Repeat
                },
                label = when (repeatMode) {
                    Player.REPEAT_MODE_ALL -> "全曲"
                    Player.REPEAT_MODE_ONE -> "1曲"
                    else -> "リピート"
                },
                active = repeatMode != Player.REPEAT_MODE_OFF,
                modifier = Modifier.weight(1f),
                onClick = onRepeat
            )
            PlaybackModeButton(
                icon = Icons.Default.PlaylistPlay,
                label = "連続",
                active = continuousPlayback,
                modifier = Modifier.weight(1f),
                onClick = onContinuous
            )
        }

        if (shuffleEnabled) {
            Text(
                "手動で順番を変えるとシャッフルはOFFになります",
                modifier = Modifier.padding(horizontal = 14.dp, vertical = 2.dp),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 9.5.sp
            )
        }

        if (queue.isEmpty()) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text("キューは空です", color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        } else {
            LazyColumn(
                contentPadding = PaddingValues(
                    horizontal = if (compact) 8.dp else 14.dp,
                    vertical = 4.dp
                )
            ) {
                itemsIndexed(queue, key = { _, track -> track.id }) { index, track ->
                    val active = index == currentIndex
                    val next = !shuffleEnabled && index == currentIndex + 1
                    var menuOpen by remember(track.id, index) { mutableStateOf(false) }

                    Surface(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(14.dp))
                            .clickable { onSelect(index) },
                        color = if (active) {
                            MaterialTheme.colorScheme.surfaceVariant
                        } else {
                            MaterialTheme.colorScheme.background
                        },
                        contentColor = MaterialTheme.colorScheme.onSurface
                    ) {
                        Row(
                            Modifier.padding(horizontal = 5.dp, vertical = 4.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Box(
                                Modifier.width(30.dp),
                                contentAlignment = Alignment.Center
                            ) {
                                when {
                                    active -> Icon(
                                        Icons.Default.GraphicEq,
                                        contentDescription = null,
                                        modifier = Modifier.size(17.dp)
                                    )
                                    next -> Text(
                                        "NEXT",
                                        color = MaterialTheme.colorScheme.primary,
                                        fontSize = 7.5.sp,
                                        fontWeight = FontWeight.Bold
                                    )
                                    else -> Text(
                                        (index + 1).toString(),
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                        fontSize = 10.sp
                                    )
                                }
                            }

                            Artwork(track, Modifier.size(if (compact) 42.dp else 50.dp))
                            Spacer(Modifier.width(8.dp))

                            Column(Modifier.weight(1f)) {
                                Text(
                                    track.title,
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis,
                                    fontWeight = if (active) FontWeight.Bold else FontWeight.Medium
                                )
                                Text(
                                    track.artist,
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    fontSize = 10.5.sp
                                )
                            }

                            Box {
                                IconButton(
                                    onClick = { menuOpen = true },
                                    modifier = Modifier.size(44.dp)
                                ) {
                                    Icon(
                                        Icons.Default.MoreVert,
                                        contentDescription = "キュー操作",
                                        modifier = Modifier.size(21.dp)
                                    )
                                }

                                DropdownMenu(
                                    expanded = menuOpen,
                                    onDismissRequest = { menuOpen = false }
                                ) {
                                    DropdownMenuItem(
                                        text = { Text("次に再生") },
                                        leadingIcon = {
                                            Icon(Icons.Default.SkipNext, contentDescription = null)
                                        },
                                        enabled = !active,
                                        onClick = {
                                            menuOpen = false
                                            onPlayNext(index)
                                        }
                                    )
                                    DropdownMenuItem(
                                        text = { Text("1つ上へ") },
                                        leadingIcon = {
                                            Icon(Icons.Default.KeyboardArrowUp, contentDescription = null)
                                        },
                                        enabled = index > 0,
                                        onClick = {
                                            menuOpen = false
                                            onMove(index, index - 1)
                                        }
                                    )
                                    DropdownMenuItem(
                                        text = { Text("1つ下へ") },
                                        leadingIcon = {
                                            Icon(Icons.Default.KeyboardArrowDown, contentDescription = null)
                                        },
                                        enabled = index < queue.lastIndex,
                                        onClick = {
                                            menuOpen = false
                                            onMove(index, index + 1)
                                        }
                                    )
                                    DropdownMenuItem(
                                        text = { Text("キューから削除") },
                                        leadingIcon = {
                                            Icon(Icons.Default.DeleteOutline, contentDescription = null)
                                        },
                                        enabled = !active,
                                        onClick = {
                                            menuOpen = false
                                            onRemove(index)
                                        }
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun BatteryPolicyCard() {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(18.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
    ) {
        Row(
            Modifier.padding(13.dp),
            verticalAlignment = Alignment.Top
        ) {
            Icon(Icons.Default.Bolt, contentDescription = null, Modifier.size(21.dp))
            Spacer(Modifier.width(9.dp))
            Column {
                Text("A300 省電力モード", fontWeight = FontWeight.Bold, fontSize = 13.sp)
                Spacer(Modifier.height(3.dp))
                Text(
                    "再生位置更新は再生画面だけ・おすすめは曲ごとに再計算しない・音量情報は一度だけ読み取りキャッシュ・キューは最大60曲。",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 10.5.sp,
                    lineHeight = 14.sp
                )
            }
        }
    }
}

@Composable
private fun PermissionError(text: String, modifier: Modifier = Modifier, onRetry: () -> Unit) {
    Box(modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier.padding(32.dp)
        ) {
            Icon(Icons.Default.LibraryMusic, null, Modifier.size(54.dp))
            Spacer(Modifier.height(18.dp))
            Text("音楽へのアクセスが必要です", style = MaterialTheme.typography.titleLarge)
            Spacer(Modifier.height(8.dp))
            Text(text, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(18.dp))
            Button(onClick = onRetry) { Text("アクセスを許可") }
        }
    }
}

@Composable
private fun SectionTitle(text: String) {
    val compact = isCompactWalkman()
    Text(
        text,
        style = MaterialTheme.typography.titleLarge,
        fontSize = if (compact) 20.sp else MaterialTheme.typography.titleLarge.fontSize
    )
}

private fun formatDuration(ms: Long): String {
    if (ms <= 0) return ""
    val min = TimeUnit.MILLISECONDS.toMinutes(ms)
    val sec = TimeUnit.MILLISECONDS.toSeconds(ms) % 60
    return "$min:" + sec.toString().padStart(2, '0')
}

private fun formatLongDuration(ms: Long): String {
    val h = TimeUnit.MILLISECONDS.toHours(ms)
    val m = TimeUnit.MILLISECONDS.toMinutes(ms) % 60
    return if (h > 0) "${h}時間${m}分" else "${m}分"
}
