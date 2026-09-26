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
    return WalkmanProfile.detect().isA300 || width <= 380
}

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

    if (showNowPlaying && ui.current != null) {
        BackHandler { showNowPlaying = false }
        NowPlayingScreen(
            track = ui.current!!,
            isPlaying = ui.isPlaying,
            onBack = { showNowPlaying = false },
            onPrevious = vm::previous,
            onToggle = vm::togglePlayPause,
            onNext = vm::next
        )
        return
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
                val compact = isCompactWalkman()
                NavigationBar(
                    modifier = Modifier.height(if (compact) 64.dp else 80.dp),
                    containerColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.96f)
                ) {
                    NavigationBarItem(
                        selected = tab == MainTab.Home,
                        onClick = { tab = MainTab.Home },
                        icon = { Icon(Icons.Default.Home, null, Modifier.size(if (compact) 22.dp else 24.dp)) },
                        label = { Text("ホーム", fontSize = if (compact) 10.sp else 12.sp) }
                    )
                    NavigationBarItem(
                        selected = tab == MainTab.Library,
                        onClick = { tab = MainTab.Library },
                        icon = { Icon(Icons.Default.LibraryMusic, null, Modifier.size(if (compact) 22.dp else 24.dp)) },
                        label = { Text("ライブラリ", fontSize = if (compact) 10.sp else 12.sp) }
                    )
                    NavigationBarItem(
                        selected = tab == MainTab.Stats,
                        onClick = { tab = MainTab.Stats },
                        icon = { Icon(Icons.Default.BarChart, null, Modifier.size(if (compact) 22.dp else 24.dp)) },
                        label = { Text("統計", fontSize = if (compact) 10.sp else 12.sp) }
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

}

@Composable
private fun HomeScreen(ui: HomeUiState, vm: MainViewModel, modifier: Modifier = Modifier) {
    val compact = isCompactWalkman()
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

        item {
            A300AudioCard()
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
                AudioSettingLine("曲間音量", "ダイナミックノーマライザー ON")
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
    val track = item?.track
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(if (compact) 24.dp else 30.dp),
        colors = CardDefaults.cardColors(containerColor = Color.Transparent)
    ) {
        Box(
            Modifier
                .fillMaxWidth()
                .height(if (compact) 184.dp else 250.dp)
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
                        "今の俺向け",
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
    Column(modifier.fillMaxSize()) {
        Column(
            Modifier.padding(
                horizontal = if (compact) 14.dp else 20.dp,
                vertical = if (compact) 10.dp else 16.dp
            )
        ) {
            Text("ライブラリ", style = MaterialTheme.typography.headlineLarge)
            Spacer(Modifier.height(if (compact) 8.dp else 14.dp))
            OutlinedTextField(
                value = ui.searchQuery,
                onValueChange = vm::search,
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                shape = RoundedCornerShape(18.dp),
                placeholder = { Text("曲、アーティスト、アルバムを検索") },
                leadingIcon = { Icon(Icons.Default.Search, null) }
            )
            Spacer(Modifier.height(if (compact) 8.dp else 12.dp))
            LazyRow(horizontalArrangement = Arrangement.spacedBy(if (compact) 6.dp else 8.dp)) {
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
            contentPadding = PaddingValues(
                horizontal = if (compact) 10.dp else 16.dp,
                vertical = if (compact) 5.dp else 8.dp
            )
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
    val compact = isCompactWalkman()
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = if (compact) 6.dp else 8.dp)
            .clip(RoundedCornerShape(if (compact) 15.dp else 18.dp))
            .clickable(onClick = onClick),
        tonalElevation = 6.dp,
        shadowElevation = 10.dp
    ) {
        Row(
            Modifier.padding(if (compact) 5.dp else 8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Artwork(track, Modifier.size(if (compact) 42.dp else 48.dp))
            Spacer(Modifier.width(if (compact) 8.dp else 10.dp))
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
private fun NowPlayingScreen(
    track: Track,
    isPlaying: Boolean,
    onBack: () -> Unit,
    onPrevious: () -> Unit,
    onToggle: () -> Unit,
    onNext: () -> Unit
) {
    val compact = isCompactWalkman()

    BoxWithConstraints(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .statusBarsPadding()
            .navigationBarsPadding()
    ) {
        val artworkSize = if (compact) {
            minOf(maxWidth * 0.68f, maxHeight * 0.31f)
        } else {
            minOf(maxWidth * 0.76f, maxHeight * 0.40f)
        }

        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(horizontal = if (compact) 18.dp else 28.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(if (compact) 48.dp else 56.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                IconButton(
                    onClick = onBack,
                    modifier = Modifier.size(48.dp)
                ) {
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
                Spacer(Modifier.size(48.dp))
            }

            Spacer(Modifier.height(if (compact) 6.dp else 14.dp))

            Artwork(
                track,
                Modifier
                    .size(artworkSize)
                    .clip(RoundedCornerShape(if (compact) 24.dp else 30.dp))
            )

            Spacer(Modifier.height(if (compact) 18.dp else 28.dp))

            Text(
                text = track.title,
                modifier = Modifier.fillMaxWidth(),
                fontSize = if (compact) 19.sp else 24.sp,
                lineHeight = if (compact) 23.sp else 29.sp,
                fontWeight = FontWeight.Bold,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis
            )

            Spacer(Modifier.height(4.dp))

            Text(
                text = track.artist,
                modifier = Modifier.fillMaxWidth(),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = if (compact) 13.sp else 15.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )

            Spacer(Modifier.weight(1f))

            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(if (compact) 82.dp else 96.dp),
                horizontalArrangement = Arrangement.SpaceEvenly,
                verticalAlignment = Alignment.CenterVertically
            ) {
                IconButton(
                    onClick = onPrevious,
                    modifier = Modifier.size(52.dp)
                ) {
                    Icon(
                        Icons.Default.SkipPrevious,
                        contentDescription = "前の曲",
                        modifier = Modifier.size(31.dp)
                    )
                }

                FilledIconButton(
                    onClick = onToggle,
                    modifier = Modifier.size(if (compact) 66.dp else 74.dp),
                    shape = CircleShape
                ) {
                    Icon(
                        if (isPlaying) Icons.Default.Pause else Icons.Default.PlayArrow,
                        contentDescription = if (isPlaying) "一時停止" else "再生",
                        modifier = Modifier.size(if (compact) 34.dp else 40.dp)
                    )
                }

                IconButton(
                    onClick = onNext,
                    modifier = Modifier.size(52.dp)
                ) {
                    Icon(
                        Icons.Default.SkipNext,
                        contentDescription = "次の曲",
                        modifier = Modifier.size(31.dp)
                    )
                }
            }

            Text(
                text = track.genre + "  ·  " + formatDuration(track.durationMs),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = if (compact) 11.sp else 12.sp,
                maxLines = 1
            )

            Spacer(Modifier.height(if (compact) 10.dp else 18.dp))
        }
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
