package io.github.zvikaz.shiurim

import android.content.ComponentName
import android.content.Intent
import android.media.browse.MediaBrowser
import android.media.session.MediaController
import android.media.session.PlaybackState
import android.os.Handler
import android.os.HandlerThread
import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.CompletableFuture
import java.util.concurrent.TimeUnit
import kotlin.math.abs

/**
 * The player as Android Auto has it: by the platform's MediaBrowser and MediaController (the session Media3 keeps
 * for them), not Media3's own. It plays the newest lesson, from the site.
 *
 *     ./gradlew connectedDebugAndroidTest   (with an emulator or a phone connected)
 */
@RunWith(AndroidJUnit4::class)
class CarPlayerTest {
    private val context = InstrumentationRegistry.getInstrumentation().targetContext
    private val thread = HandlerThread("car").apply { start() }
    private val handler = Handler(thread.looper)
    private lateinit var browser: MediaBrowser
    private lateinit var controller: MediaController

    private fun <T> onThread(block: () -> T): T = CompletableFuture<T>().also { future ->
        handler.post { future.complete(block()) }
    }.get(10, TimeUnit.SECONDS)

    private fun connect() {
        val connected = CompletableFuture<Unit>()
        browser = onThread {
            MediaBrowser(context, ComponentName(context, PlaybackService::class.java), object : MediaBrowser.ConnectionCallback() {
                override fun onConnected() { connected.complete(Unit) }
                override fun onConnectionFailed() { connected.completeExceptionally(IllegalStateException("refused")) }
            }, null).apply { connect() }
        }
        connected.get(20, TimeUnit.SECONDS)
        controller = onThread { MediaController(context, browser.sessionToken) }
    }

    private fun newestLesson(): String {
        val children = CompletableFuture<String>()
        onThread {
            browser.subscribe(Library.NEWEST, object : MediaBrowser.SubscriptionCallback() {
                override fun onChildrenLoaded(parentId: String, items: MutableList<MediaBrowser.MediaItem>) {
                    children.complete(items.first { it.isPlayable }.mediaId)
                }
            })
        }
        return children.get(60, TimeUnit.SECONDS)
    }

    private fun waitFor(what: String, seconds: Int = 60, test: (PlaybackState) -> Boolean): PlaybackState {
        val until = SystemClock.elapsedRealtime() + seconds * 1000
        while (SystemClock.elapsedRealtime() < until) {
            controller.playbackState?.takeIf(test)?.let { return it }
            Thread.sleep(200)
        }
        throw AssertionError("no $what: ${controller.playbackState}")
    }

    private fun position(state: PlaybackState = controller.playbackState!!) =
        state.position + ((SystemClock.elapsedRealtime() - state.lastPositionUpdateTime) * state.playbackSpeed).toLong()

    private fun action(state: PlaybackState, name: String) = state.customActions.single { it.action == name }

    @After
    fun disconnect() {
        runCatching { controller.transportControls.pause() }
        onThread { browser.disconnect() }
        thread.quitSafely()
    }

    @Test
    fun buttonsSkip30SecondsAndShowTheSpeed() {
        // in the foreground, as with Android Auto, or Android (15) denies the player audio focus, and it won't play
        context.startActivity(Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        connect()
        val lesson = newestLesson()
        controller.transportControls.playFromMediaId(lesson, null)
        waitFor("playing") { it.state == PlaybackState.STATE_PLAYING }
        controller.transportControls.seekTo(120_000)
        var state = waitFor("seeked") { it.state == PlaybackState.STATE_PLAYING && abs(position(it) - 120_000) < 3_000 }

        // what the car is given: our buttons for back and forward, in their slots, and no "previous"
        println("car state: $state, extras ${state.extras?.keySet()?.associateWith { state.extras!!.get(it) }}")
        val completionAction = state.customActions.single { it.action == "heard" || it.action == "unheard" }.action
        assertEquals(listOf("back", "forward", "speed", "next", completionAction, "subscribe"),
            state.customActions.map { it.action })
        assertTrue(state.actions and PlaybackState.ACTION_PLAY_PAUSE != 0L)
        assertEquals(0L, state.actions and PlaybackState.ACTION_SKIP_TO_PREVIOUS)
        assertEquals(0L, state.actions and PlaybackState.ACTION_SKIP_TO_NEXT)
        assertFalse(state.extras!!.getBoolean("android.media.playback.ALWAYS_RESERVE_SPACE_FOR.ACTION_SKIP_TO_PREVIOUS", true))
        assertFalse(state.extras!!.getBoolean("android.media.playback.ALWAYS_RESERVE_SPACE_FOR.ACTION_SKIP_TO_NEXT", true))

        // back: 30 seconds, not to the lesson's start
        var before = position(state)
        controller.transportControls.sendCustomAction(action(state, "back"), null)
        state = waitFor("back 30") { abs(position(it) - (before - 30_000)) < 3_000 }
        assertEquals(controller.metadata?.description?.mediaId ?: lesson, lesson)

        before = position(state)
        controller.transportControls.sendCustomAction(action(state, "forward"), null)
        state = waitFor("forward 30") { abs(position(it) - (before + 30_000)) < 3_000 }

        // the speed button shows the speed, and goes round them all, back to where it was
        val speeds = mapOf(1.0f to R.drawable.ic_speed_1, 1.2f to R.drawable.ic_speed_1_2, 1.5f to R.drawable.ic_speed_1_5,
            1.8f to R.drawable.ic_speed_1_8, 2.0f to R.drawable.ic_speed_2, 0.8f to R.drawable.ic_speed_0_8)
        val first = state.extras!!.getFloat("EXO_SPEED", 1f)
        assertEquals(speeds.getValue(first), action(state, "speed").icon)
        val seen = mutableListOf(first)
        repeat(speeds.size) {
            val icon = action(controller.playbackState!!, "speed").icon
            controller.transportControls.sendCustomAction("speed", null)
            state = waitFor("next speed") { action(it, "speed").icon != icon }
            val speed = speeds.entries.single { it.value == action(state, "speed").icon }.key
            assertEquals(speed, state.extras!!.getFloat("EXO_SPEED"), 0.01f)  // (its playbackSpeed is 0 while it buffers)
            seen += speed
        }
        assertEquals(speeds.keys, seen.toSet())
        assertEquals(first, seen.last())

        // the heard button's icon shows whether the lesson was heard: a filled check once it was, unfilled before
        val heardIcon = mapOf("heard" to androidx.media3.session.R.drawable.media3_icon_check_circle_unfilled,
            "unheard" to androidx.media3.session.R.drawable.media3_icon_check_circle_filled)
        assertEquals(heardIcon.getValue(completionAction), action(state, completionAction).icon)
        controller.transportControls.sendCustomAction(action(state, completionAction), null)
        val opposite = if (completionAction == "heard") "unheard" else "heard"
        state = waitFor("heard button to toggle") { current -> current.customActions.any { it.action == opposite } }
        assertEquals(heardIcon.getValue(opposite), action(state, opposite).icon)
        controller.transportControls.sendCustomAction(action(state, opposite), null)
        waitFor("heard button to toggle back") { current -> current.customActions.any { it.action == completionAction } }
    }
}
