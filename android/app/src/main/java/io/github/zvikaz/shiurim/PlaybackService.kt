package io.github.zvikaz.shiurim

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata
import androidx.media3.common.PlaybackParameters
import androidx.media3.common.Player
import androidx.media3.datasource.DefaultDataSource
import androidx.media3.datasource.DefaultHttpDataSource
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import androidx.media3.session.CommandButton
import androidx.media3.session.LibraryResult
import androidx.media3.session.MediaConstants
import androidx.media3.session.MediaLibraryService
import androidx.media3.session.MediaSession
import androidx.media3.session.MediaSession.MediaItemsWithStartPosition
import androidx.media3.session.SessionCommand
import androidx.media3.session.SessionError
import androidx.media3.session.SessionResult
import com.google.common.collect.ImmutableList
import com.google.common.util.concurrent.ListenableFuture
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.guava.future
import kotlinx.coroutines.launch

/**
 * The player, and the library Android Auto (and the app's own screen) browses: see [Library]. Playing a lesson plays
 * its series on from it, from where it was left; where each lesson was left is saved as it plays.
 */
class PlaybackService : MediaLibraryService() {
    private companion object {
        const val SAVE_EVERY = 10_000L
        const val RECENT_ROOT = "recent"  // the root the system asks for to offer resuming, after a restart
        const val SEEK = 30_000L  // back and forward, in the car's player and the notification
        // the player's buttons are custom commands, even those a player command would do: Android Auto (by the
        // platform session) is only given a session's custom commands, and without a button of its own in the back
        // slot it shows "previous", which goes back to the lesson's start
        const val BACK = "back"
        const val FORWARD = "forward"
        const val NEXT = "next"
        const val SPEED = "speed"  // the player's speed, to the next one of SPEEDS
        const val SUBSCRIBE = "subscribe"  // a series (or the playing lesson's), to a podcast app
        const val CHANNEL = "subscribe"
        // with the icons that show them (written by tools/speed_icons.py)
        val SPEEDS = listOf(1.0f to R.drawable.ic_speed_1, 1.2f to R.drawable.ic_speed_1_2,
            1.5f to R.drawable.ic_speed_1_5, 1.8f to R.drawable.ic_speed_1_8, 2.0f to R.drawable.ic_speed_2,
            0.8f to R.drawable.ic_speed_0_8)
        val COMMANDS = listOf(BACK, FORWARD, NEXT, SPEED, SUBSCRIBE).map { SessionCommand(it, Bundle.EMPTY) }
    }

    private lateinit var player: ExoPlayer
    private lateinit var session: MediaLibrarySession
    private lateinit var library: Library
    private lateinit var positions: Positions
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private val handler = Handler(Looper.getMainLooper())
    private val searches = mutableMapOf<String, List<Node>>()

    override fun onCreate() {
        super.onCreate()
        positions = Positions(getSharedPreferences("positions", MODE_PRIVATE))
        library = Library(CatalogRepository(filesDir, BuildConfig.SITE_URL), positions, Labels(
            continueTab = getString(R.string.tab_continue), newestTab = getString(R.string.tab_newest),
            ravsTab = getString(R.string.tab_ravs),
            seriesCount = { getString(R.string.series_count, it) },
            lessonsCount = { getString(R.string.lessons_count, it) },
            minutes = { getString(R.string.minutes, it) },
        ))
        // (lessons' links redirect, some from http to https)
        val http = DefaultHttpDataSource.Factory().setAllowCrossProtocolRedirects(true).setUserAgent("shiurim")
        player = ExoPlayer.Builder(this)
            .setAudioAttributes(AudioAttributes.Builder().setUsage(C.USAGE_MEDIA)
                .setContentType(C.AUDIO_CONTENT_TYPE_SPEECH).build(), /* handleAudioFocus= */ true)
            .setHandleAudioBecomingNoisy(true)
            .setMediaSourceFactory(DefaultMediaSourceFactory(DefaultDataSource.Factory(this, http)))
            .setSeekBackIncrementMs(SEEK).setSeekForwardIncrementMs(SEEK)
            .build()
        player.playbackParameters = PlaybackParameters(settings.getFloat(SPEED, 1.0f))
        player.addListener(Saver())
        session = MediaLibrarySession.Builder(this, player, Callback())
            .setSessionActivity(PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java),
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT))
            .setMediaButtonPreferences(buttons())
            .setCommandButtonsForMediaItems(listOf(subscribeButton()))
            .build()
    }

    private val settings by lazy { getSharedPreferences("settings", MODE_PRIVATE) }

    /**
     * the player's buttons: back and forward 30 seconds (rather than to the lesson's start and the next one), and
     * in the overflow its speed, the next lesson, and adding the series to a podcast app
     */
    private fun buttons(): List<CommandButton> {
        val speed = player.playbackParameters.speed
        return listOf(
            CommandButton.Builder(CommandButton.ICON_SKIP_BACK_30).setSessionCommand(SessionCommand(BACK, Bundle.EMPTY))
                .setDisplayName(getString(R.string.back_30)).setSlots(CommandButton.SLOT_BACK).build(),
            CommandButton.Builder(CommandButton.ICON_SKIP_FORWARD_30).setSessionCommand(SessionCommand(FORWARD, Bundle.EMPTY))
                .setDisplayName(getString(R.string.forward_30)).setSlots(CommandButton.SLOT_FORWARD).build(),
            // the speed itself as its icon, in our own font
            CommandButton.Builder(CommandButton.ICON_UNDEFINED).setCustomIconResId(speedOf(speed).second)
                .setSessionCommand(SessionCommand(SPEED, Bundle.EMPTY))
                .setDisplayName(getString(R.string.speed, speed)).setSlots(CommandButton.SLOT_OVERFLOW).build(),
            CommandButton.Builder(CommandButton.ICON_NEXT).setSessionCommand(SessionCommand(NEXT, Bundle.EMPTY))
                .setDisplayName(getString(R.string.next_lesson)).setSlots(CommandButton.SLOT_OVERFLOW).build(),
            subscribeButton(),
        )
    }

    private fun speedOf(speed: Float) = SPEEDS.minBy { kotlin.math.abs(it.first - speed) }

    private fun subscribeButton() = CommandButton.Builder(CommandButton.ICON_PLAYLIST_ADD)
        .setSessionCommand(SessionCommand(SUBSCRIBE, Bundle.EMPTY))
        .setDisplayName(getString(R.string.subscribe)).setSlots(CommandButton.SLOT_OVERFLOW).build()

    /** the player's next speed (of SPEEDS), kept for next time */
    private fun nextSpeed() {
        val speed = player.playbackParameters.speed
        val next = SPEEDS[(SPEEDS.indexOf(speedOf(speed)) + 1) % SPEEDS.size].first
        player.playbackParameters = PlaybackParameters(next)
        settings.edit().putFloat(SPEED, next).apply()
        session.setMediaButtonPreferences(buttons())
    }

    /**
     * a series to a podcast app: not opened while driving, but left as a notification on the phone, which opens
     * the podcast app (by its pcast: link, as the site's "add to app" does)
     */
    private fun subscribe(series: Series) {
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel(CHANNEL, getString(R.string.subscribe_channel),
            NotificationManager.IMPORTANCE_DEFAULT))
        val link = Uri.parse("pcast://" + series.feed.substringAfter("://"))
        val open = PendingIntent.getActivity(this, series.id.hashCode(), Intent(Intent.ACTION_VIEW, link),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        manager.notify(series.id.hashCode(), Notification.Builder(this, CHANNEL)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(getString(R.string.subscribe))
            .setContentText("${series.name} · ${series.rav}")
            .setContentIntent(open).setAutoCancel(true).build())
    }

    override fun onGetSession(controllerInfo: MediaSession.ControllerInfo) = session

    override fun onTaskRemoved(rootIntent: Intent?) {
        if (!player.playWhenReady || player.mediaItemCount == 0) stopSelf()
    }

    override fun onDestroy() {
        save()
        handler.removeCallbacksAndMessages(null)
        scope.cancel()
        session.release()
        player.release()
        super.onDestroy()
    }

    /** where the playing lesson is, saved */
    private fun save() {
        val id = player.currentMediaItem?.mediaId ?: return
        if (id.startsWith("lesson/") && player.currentPosition > 0)
            positions.save(Library.lessonKey(id), player.currentPosition, player.duration.coerceAtLeast(0))
    }

    private inner class Saver : Player.Listener {
        private val tick = object : Runnable {
            override fun run() {
                save()
                handler.postDelayed(this, SAVE_EVERY)
            }
        }

        override fun onIsPlayingChanged(isPlaying: Boolean) {
            handler.removeCallbacks(tick)
            if (isPlaying) handler.postDelayed(tick, SAVE_EVERY) else save()
        }

        override fun onPositionDiscontinuity(old: Player.PositionInfo, new: Player.PositionInfo, reason: Int) {
            // played to its end, on to the next lesson: the one before was heard
            if (reason == Player.DISCONTINUITY_REASON_AUTO_TRANSITION)
                old.mediaItem?.mediaId?.takeIf { it.startsWith("lesson/") }?.let { positions.finished(Library.lessonKey(it)) }
        }

        override fun onPlaybackStateChanged(state: Int) {
            if (state == Player.STATE_ENDED)
                player.currentMediaItem?.mediaId?.takeIf { it.startsWith("lesson/") }?.let { positions.finished(Library.lessonKey(it)) }
        }
    }

    private inner class Callback : MediaLibrarySession.Callback {
        /** the player's buttons and the podcast app, besides what a library offers */
        override fun onConnect(session: MediaSession, controller: MediaSession.ControllerInfo): MediaSession.ConnectionResult {
            val commands = MediaSession.ConnectionResult.DEFAULT_SESSION_AND_LIBRARY_COMMANDS.buildUpon()
                .apply { COMMANDS.forEach(::add) }.build()
            return MediaSession.ConnectionResult.AcceptedResultBuilder(session).setAvailableSessionCommands(commands)
                .setMediaButtonPreferences(buttons()).build()
        }

        override fun onCustomCommand(session: MediaSession, controller: MediaSession.ControllerInfo,
                                     command: SessionCommand, args: Bundle): ListenableFuture<SessionResult> {
            when (command.customAction) {
                BACK -> player.seekBack()
                FORWARD -> player.seekForward()
                NEXT -> player.seekToNextMediaItem()
                SPEED -> nextSpeed()
                SUBSCRIBE -> {
                    // a series or lesson in a list, or the lesson playing
                    val id = args.getString(MediaConstants.EXTRA_KEY_MEDIA_ID) ?: player.currentMediaItem?.mediaId
                    return scope.future(Dispatchers.IO) {
                        val series = id?.let { runCatching { library.seriesOf(it) }.getOrNull() }
                            ?: return@future SessionResult(SessionError.ERROR_BAD_VALUE)
                        launch(Dispatchers.Main) { subscribe(series) }
                        SessionResult(SessionResult.RESULT_SUCCESS)
                    }
                }
                else -> return immediate(SessionResult(SessionError.ERROR_NOT_SUPPORTED))
            }
            return immediate(SessionResult(SessionResult.RESULT_SUCCESS))
        }

        override fun onGetLibraryRoot(session: MediaLibrarySession, browser: MediaSession.ControllerInfo,
                                      params: LibraryParams?): ListenableFuture<LibraryResult<MediaItem>> {
            val extras = Bundle().apply {
                putInt(MediaConstants.EXTRAS_KEY_CONTENT_STYLE_BROWSABLE, MediaConstants.EXTRAS_VALUE_CONTENT_STYLE_LIST_ITEM)
                putInt(MediaConstants.EXTRAS_KEY_CONTENT_STYLE_PLAYABLE, MediaConstants.EXTRAS_VALUE_CONTENT_STYLE_LIST_ITEM)
            }
            val root = if (params?.isRecent == true) RECENT_ROOT else Library.ROOT
            return immediate(LibraryResult.ofItem(folder(root, getString(R.string.app_name)),
                LibraryParams.Builder().setExtras(extras).build()))
        }

        override fun onGetChildren(session: MediaLibrarySession, browser: MediaSession.ControllerInfo, parentId: String,
                                   page: Int, pageSize: Int, params: LibraryParams?) = scope.future(Dispatchers.IO) {
            try {
                val nodes = if (parentId == RECENT_ROOT) library.children(Library.CONTINUE).take(1) else library.children(parentId)
                LibraryResult.ofItemList(nodes.map(::item), params)
            } catch (error: Exception) {
                LibraryResult.ofError<ImmutableList<MediaItem>>(LibraryResult.RESULT_ERROR_IO)
            }
        }

        override fun onGetItem(session: MediaLibrarySession, browser: MediaSession.ControllerInfo,
                               mediaId: String) = scope.future(Dispatchers.IO) {
            val node = runCatching { library.node(mediaId) }.getOrNull()
            if (node != null) LibraryResult.ofItem(item(node), null)
            else LibraryResult.ofError(LibraryResult.RESULT_ERROR_BAD_VALUE)
        }

        override fun onSearch(session: MediaLibrarySession, browser: MediaSession.ControllerInfo, query: String,
                              params: LibraryParams?) = scope.future(Dispatchers.IO) {
            val found = runCatching { library.search(query) }.getOrDefault(emptyList())
            searches[query] = found
            session.notifySearchResultChanged(browser, query, found.size, params)
            LibraryResult.ofVoid()
        }

        override fun onGetSearchResult(session: MediaLibrarySession, browser: MediaSession.ControllerInfo, query: String,
                                       page: Int, pageSize: Int, params: LibraryParams?) = scope.future(Dispatchers.IO) {
            val found = searches[query] ?: runCatching { library.search(query) }.getOrDefault(emptyList())
            LibraryResult.ofItemList(found.map(::item), params)
        }

        /** what a controller (Android Auto, a voice request, the app's screen) asks to play, made playable */
        override fun onSetMediaItems(mediaSession: MediaSession, controller: MediaSession.ControllerInfo,
                                     mediaItems: MutableList<MediaItem>, startIndex: Int,
                                     startPositionMs: Long): ListenableFuture<MediaItemsWithStartPosition> =
            scope.future(Dispatchers.IO) {
                val requested = mediaItems.singleOrNull()
                val query = requested?.requestMetadata?.searchQuery
                val queue = when {
                    query != null -> library.play(query)
                    requested != null && requested.mediaId.startsWith("lesson/") -> library.queue(requested.mediaId)
                    else -> null
                }
                if (queue != null) MediaItemsWithStartPosition(queue.lessons.map(::item), queue.start, queue.position)
                else MediaItemsWithStartPosition(resolve(mediaItems), startIndex, startPositionMs)
            }

        override fun onAddMediaItems(mediaSession: MediaSession, controller: MediaSession.ControllerInfo,
                                     mediaItems: MutableList<MediaItem>) = scope.future(Dispatchers.IO) {
            resolve(mediaItems)
        }

        /** "resume" (after a restart, from the system's media controls): what was heard last */
        override fun onPlaybackResumption(mediaSession: MediaSession,
                                          controller: MediaSession.ControllerInfo) = scope.future(Dispatchers.IO) {
            val queue = library.play("") ?: throw IllegalStateException("nothing to resume")
            MediaItemsWithStartPosition(queue.lessons.map(::item), queue.start, queue.position)
        }

        private fun resolve(items: List<MediaItem>): MutableList<MediaItem> =
            items.mapNotNull { requested -> library.node(requested.mediaId)?.let(::item) }.toMutableList()
    }

    private fun folder(id: String, title: String) = MediaItem.Builder().setMediaId(id).setMediaMetadata(
        MediaMetadata.Builder().setTitle(title).setIsBrowsable(true).setIsPlayable(false)
            .setMediaType(MediaMetadata.MEDIA_TYPE_FOLDER_MIXED).build()).build()

    private fun item(node: Node): MediaItem {
        val extras = Bundle()
        if (node.grid) extras.putInt(MediaConstants.EXTRAS_KEY_CONTENT_STYLE_BROWSABLE,
            MediaConstants.EXTRAS_VALUE_CONTENT_STYLE_GRID_ITEM)
        node.progress?.let { progress ->
            extras.putInt(MediaConstants.EXTRAS_KEY_COMPLETION_STATUS, when {
                progress.finished -> MediaConstants.EXTRAS_VALUE_COMPLETION_STATUS_FULLY_PLAYED
                progress.position > 0 -> MediaConstants.EXTRAS_VALUE_COMPLETION_STATUS_PARTIALLY_PLAYED
                else -> MediaConstants.EXTRAS_VALUE_COMPLETION_STATUS_NOT_PLAYED
            })
            extras.putDouble(MediaConstants.EXTRAS_KEY_COMPLETION_PERCENTAGE, progress.fraction)
        }
        val metadata = MediaMetadata.Builder()
            .setTitle(node.title).setSubtitle(node.subtitle).setArtist(node.subtitle.ifEmpty { null })
            .setIsBrowsable(node.browsable).setIsPlayable(!node.browsable)
            .setMediaType(if (node.browsable) MediaMetadata.MEDIA_TYPE_FOLDER_MIXED else MediaMetadata.MEDIA_TYPE_PODCAST_EPISODE)
            .setArtworkUri(artwork(node.art))
            .setExtras(extras)
            .setSupportedCommands(if (node.series != null) listOf(SUBSCRIBE) else emptyList())
            .build()
        return MediaItem.Builder().setMediaId(node.id).setMediaMetadata(metadata)
            .apply { node.url?.let { setUri(it) } }.build()
    }

    private fun artwork(art: String?): Uri? = when {
        art.isNullOrEmpty() -> null
        art.startsWith("icon:") -> Uri.parse("android.resource://$packageName/drawable/ic_tab_${art.removePrefix("icon:")}")
        else -> ArtworkProvider.uri(this, art)
    }

    private fun <T> immediate(value: T): ListenableFuture<T> = com.google.common.util.concurrent.Futures.immediateFuture(value)
}
