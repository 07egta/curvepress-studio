package com.egtgpt.musewalk

import android.Manifest
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
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
                fontSize = 34.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = (-0.8).sp
            ),
            titleLarge = MaterialTheme.typography.titleLarge.copy(fontWeight = FontWeight.Bold)
        ),
        content = content
    )
}

private enum class MainTab { Home, Library, Stats }

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MuseWalkApp(vm: MainViewModel) {
    val ui by vm.ui.collectAsStateWithLifecycle()
    var tab by remember { mutableStateOf(MainTab.Home) }
    var showNowPlaying by remember { mutableStateOf(false) }

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

    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        bottomBar = {
            Column {
                AnimatedVisibility(ui.current != null) {
                    MiniPlayer(
                        track = ui.current,
                        isPlaying = ui.isPlaying,
                        onClick = { showNowPlaying = true },
                        onToggle = vm::togglePlayPause,
                        onNext = vm::next
                    )
                }
                NavigationBar(containerColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.96f)) {
                    NavigationBarItem(
                        selected = tab == MainTab.Home,
                        onClick = { tab = MainTab.Home },
                        icon = { Icon(Icons.Default.Home, null) },
                        label = { Text("ホーム") }
                    )
                    NavigationBarItem(
                        selected = tab == MainTab.Library,
                        onClick = { tab = MainTab.Library },
                        icon = { Icon(Icons.Default.LibraryMusic, null) },
                        label = { Text("ライブラリ") }
                    )
                    NavigationBarItem(
                        selected = tab == MainTab.Stats,
                        onClick = { tab = MainTab.Stats },
                        icon = { Icon(Icons.Default.BarChart, null) },
                        label = { Text("統計") }
                    )
                }
            }
        }
    ) { padding ->
        when {
            ui.loading -> Box(
                Modifier.fillMaxSize().padding(padding),
                contentAlignment = Alignment.Center
            ) { CircularProgressIndicator() }

            ui.error != null -> PermissionError(
                text = ui.error ?: "読み込みエラー",
                modifier = Modifier.padding(padding),
                onRetry = { launcher.launch(permission) }
            )

            else -> when (tab) {
                MainTab.Home -> HomeScreen(ui, vm, Modifier.padding(padding))
                MainTab.Library -> LibraryScreen(ui, vm, Modifier.padding(padding))
                MainTab.Stats -> StatsScreen(ui, vm, Modifier.padding(padding))
            }
        }
    }

    if (showNowPlaying && ui.current != null) {
        ModalBottomSheet(
            onDismissRequest = { showNowPlaying = false },
            dragHandle = { BottomSheetDefaults.DragHandle() }
        ) {
            NowPlayingSheet(
                track = ui.current!!,
                isPlaying = ui.isPlaying,
                stats = vm.statsFor(ui.current!!),
                onPrevious = vm::previous,
                onToggle = vm::togglePlayPause,
                onNext = vm::next
            )
        }
    }
}

@Composable
private fun HomeScreen(ui: HomeUiState, vm: MainViewModel, modifier: Modifier = Modifier) {
    val recentFavorites = remember(ui.tracks, ui.recommendations) {
        ui.recommendations.filter { it.reason.contains("最後まで") || it.reason.contains("履歴") }.take(8)
    }
    val rediscovery = remember(ui.recommendations) {
        ui.recommendations.filter { it.reason.contains("久しぶり") || it.reason.contains("あまり") }.take(8)
    }

    LazyColumn(
        modifier = modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = 20.dp, vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(24.dp)
    ) {
        item {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("MuseWalk", style = MaterialTheme.typography.headlineLarge)
                Text(
                    "聴くほど、あなた向けに。",
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }

        item {
            HeroRecommendation(
                item = ui.recommendations.firstOrNull(),
                onPlay = vm::playRecommended
            )
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
            SectionTitle("ジャンル")
            Spacer(Modifier.height(12.dp))
            LazyRow(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                items(ui.genres) { genre ->
                    AssistChip(
                        onClick = { vm.selectGenre(genre) },
                        label = { Text(genre) },
                        leadingIcon = { Icon(Icons.Default.GraphicEq, null, Modifier.size(18.dp)) }
                    )
                }
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
private fun HeroRecommendation(item: RecommendedTrack?, onPlay: () -> Unit) {
    val track = item?.track
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(30.dp),
        colors = CardDefaults.cardColors(containerColor = Color.Transparent)
    ) {
        Box(
            Modifier
                .fillMaxWidth()
                .height(250.dp)
                .background(
                    Brush.linearGradient(
                        listOf(Color(0xFF232526), Color(0xFF5D5D62), Color(0xFF1B1B1D))
                    )
                )
                .padding(24.dp)
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
                        "今の俺向け",
                        color = Color.White,
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 7.dp),
                        fontWeight = FontWeight.SemiBold
                    )
                }
                Column {
                    Text(
                        track?.title ?: "曲を読み込むとおすすめが出ます",
                        color = Color.White,
                        fontSize = 27.sp,
                        fontWeight = FontWeight.Bold,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis
                    )
                    if (track != null) {
                        Spacer(Modifier.height(4.dp))
                        Text(track.artist, color = Color.White.copy(alpha = 0.72f))
                        Text(item.reason, color = Color.White.copy(alpha = 0.62f), fontSize = 13.sp)
                        Spacer(Modifier.height(18.dp))
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
    LazyRow(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
        items(items, key = { it.track.id }) { item ->
            Column(
                Modifier
                    .width(148.dp)
                    .clickable { onClick(item) }
            ) {
                Artwork(item.track, Modifier.size(148.dp))
                Spacer(Modifier.height(9.dp))
                Text(
                    item.track.title,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
                Text(
                    item.track.artist,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 13.sp,
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
    Column(modifier.fillMaxSize()) {
        Column(Modifier.padding(horizontal = 20.dp, vertical = 16.dp)) {
            Text("ライブラリ", style = MaterialTheme.typography.headlineLarge)
            Spacer(Modifier.height(14.dp))
            SearchBar(
                inputField = {
                    SearchBarDefaults.InputField(
                        query = ui.searchQuery,
                        onQueryChange = vm::search,
                        onSearch = {},
                        expanded = false,
                        onExpandedChange = {},
                        placeholder = { Text("曲、アーティスト、アルバムを検索") },
                        leadingIcon = { Icon(Icons.Default.Search, null) }
                    )
                },
                expanded = false,
                onExpandedChange = {}
            ) {}
            Spacer(Modifier.height(12.dp))
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                item {
                    FilterChip(
                        selected = ui.selectedGenre == null,
                        onClick = { vm.selectGenre(null) },
                        label = { Text("すべて") }
                    )
                }
                items(ui.genres) { genre ->
                    FilterChip(
                        selected = ui.selectedGenre == genre,
                        onClick = { vm.selectGenre(genre) },
                        label = { Text(genre) }
                    )
                }
            }
        }

        HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.45f))

        LazyColumn(
            contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp)
        ) {
            items(ui.visibleTracks, key = { it.id }) { track ->
                TrackRow(
                    track = track,
                    subtitle = track.artist + "  ·  " + track.genre,
                    onClick = { vm.play(track, ui.visibleTracks) }
                )
            }
            item { Spacer(Modifier.height(24.dp)) }
        }
    }
}

@Composable
private fun StatsScreen(ui: HomeUiState, vm: MainViewModel, modifier: Modifier = Modifier) {
    val ranked = remember(ui.tracks, ui.recommendations) {
        ui.tracks.map { it to vm.statsFor(it) }.sortedByDescending { it.second.playCount }
    }
    val totalPlays = ranked.sumOf { it.second.playCount }
    val totalMs = ranked.sumOf { it.second.totalListenMs }

    LazyColumn(
        modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = 20.dp, vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp)
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
    Card(
        modifier = modifier,
        shape = RoundedCornerShape(24.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
    ) {
        Column(Modifier.padding(18.dp)) {
            Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
            Spacer(Modifier.height(8.dp))
            Text(value, fontSize = 24.sp, fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
private fun TrackRow(track: Track, subtitle: String, onClick: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(18.dp))
            .clickable(onClick = onClick)
            .padding(8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Artwork(track, Modifier.size(58.dp))
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(track.title, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(
                subtitle,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 13.sp,
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
    val palette = when (track.genre) {
        "ボカロ" -> listOf(Color(0xFF45C3B8), Color(0xFF236C73))
        "アニメ・ゲーム" -> listOf(Color(0xFF8D6BD8), Color(0xFF3F315F))
        "洋楽" -> listOf(Color(0xFF4776E6), Color(0xFF31416B))
        "J-POP" -> listOf(Color(0xFFF2709C), Color(0xFF8C385A))
        "BGM" -> listOf(Color(0xFF667EEA), Color(0xFF39456F))
        else -> listOf(Color(0xFF606C88), Color(0xFF30343F))
    }
    Box(
        modifier
            .clip(RoundedCornerShape(18.dp))
            .background(Brush.linearGradient(palette)),
        contentAlignment = Alignment.Center
    ) {
        Text(
            track.title.take(1).uppercase(),
            color = Color.White.copy(alpha = 0.88f),
            fontSize = 28.sp,
            fontWeight = FontWeight.Bold
        )
    }
}

@Composable
private fun MiniPlayer(
    track: Track?,
    isPlaying: Boolean,
    onClick: () -> Unit,
    onToggle: () -> Unit,
    onNext: () -> Unit
) {
    if (track == null) return
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 8.dp)
            .clip(RoundedCornerShape(18.dp))
            .clickable(onClick = onClick),
        tonalElevation = 6.dp,
        shadowElevation = 10.dp
    ) {
        Row(
            Modifier.padding(8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Artwork(track, Modifier.size(48.dp))
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Text(track.title, maxLines = 1, overflow = TextOverflow.Ellipsis, fontWeight = FontWeight.SemiBold)
                Text(track.artist, maxLines = 1, overflow = TextOverflow.Ellipsis, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
            }
            IconButton(onClick = onToggle) {
                Icon(if (isPlaying) Icons.Default.Pause else Icons.Default.PlayArrow, null)
            }
            IconButton(onClick = onNext) { Icon(Icons.Default.SkipNext, null) }
        }
    }
}

@Composable
private fun NowPlayingSheet(
    track: Track,
    isPlaying: Boolean,
    stats: TrackStats,
    onPrevious: () -> Unit,
    onToggle: () -> Unit,
    onNext: () -> Unit
) {
    Column(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 28.dp, vertical = 10.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Artwork(track, Modifier.fillMaxWidth().aspectRatio(1f))
        Spacer(Modifier.height(28.dp))
        Text(track.title, style = MaterialTheme.typography.titleLarge, maxLines = 2, overflow = TextOverflow.Ellipsis)
        Text(track.artist, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.height(26.dp))
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceEvenly,
            verticalAlignment = Alignment.CenterVertically
        ) {
            IconButton(onClick = onPrevious, modifier = Modifier.size(58.dp)) {
                Icon(Icons.Default.SkipPrevious, null, Modifier.size(34.dp))
            }
            FilledIconButton(onClick = onToggle, modifier = Modifier.size(72.dp), shape = CircleShape) {
                Icon(if (isPlaying) Icons.Default.Pause else Icons.Default.PlayArrow, null, Modifier.size(38.dp))
            }
            IconButton(onClick = onNext, modifier = Modifier.size(58.dp)) {
                Icon(Icons.Default.SkipNext, null, Modifier.size(34.dp))
            }
        }
        Spacer(Modifier.height(20.dp))
        Surface(
            shape = RoundedCornerShape(22.dp),
            color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.55f)
        ) {
            Row(
                Modifier.fillMaxWidth().padding(18.dp),
                horizontalArrangement = Arrangement.SpaceAround
            ) {
                SmallMetric("再生", "${stats.playCount}回")
                SmallMetric("完走", "${(stats.completionRate * 100).toInt()}%")
                SmallMetric("スキップ", "${(stats.skipRate * 100).toInt()}%")
            }
        }
        Spacer(Modifier.height(30.dp))
    }
}

@Composable
private fun SmallMetric(label: String, value: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value, fontWeight = FontWeight.Bold)
        Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
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
    Text(text, style = MaterialTheme.typography.titleLarge)
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
