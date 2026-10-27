package io.github.zvikaz.shiurim

import android.content.ComponentName
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
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.CompletableFuture
import java.util.concurrent.TimeUnit
import kotlin.math.abs

/**
 * Android Auto connecting while the app isn't in use (no screen of it open, nothing played since it started): it's
 * given the lesson Continue would play, paused where it was left, so its player shows "play" (with nothing loaded,
 * it was given no lesson, and showed "stop"). The service must start with this test: it runs before CarPlayerTest.
 *
 *     ./gradlew connectedDebugAndroidTest   (with an emulator or a phone connected)
 */
@RunWith(AndroidJUnit4::class)
class CarIdleStateTest {
    private val context = InstrumentationRegistry.getInstrumentation().targetContext
    private val thread = HandlerThread("car").apply { start() }
    private val handler = Handler(thread.looper)
    private lateinit var browser: MediaBrowser
    private lateinit var controller: MediaController

    private fun <T> onThread(block: () -> T): T = CompletableFuture<T>().also { future ->
        handler.post { future.complete(block()) }
    }.get(10, TimeUnit.SECONDS)

    @After
    fun disconnect() {
        if (::browser.isInitialized) onThread { browser.disconnect() }
        thread.quitSafely()
    }

    @Test
    fun theCarIsGivenTheLessonToContinuePausedWhereItWasLeft() {
        // a lesson left in its middle, a minute and a half in
        val newest = CatalogRepository(context.filesDir, BuildConfig.SITE_URL).catalog().newest.first()
        val key = "${newest.series}/${newest.position}"
        Positions(context.getSharedPreferences("positions", 0)).save(key, 90_000, 0, newest.url)

        val connected = CompletableFuture<Unit>()
        browser = onThread {
            MediaBrowser(context, ComponentName(context, PlaybackService::class.java), object : MediaBrowser.ConnectionCallback() {
                override fun onConnected() { connected.complete(Unit) }
                override fun onConnectionFailed() { connected.completeExceptionally(IllegalStateException("refused")) }
            }, null).apply { connect() }
        }
        connected.get(20, TimeUnit.SECONDS)
        controller = onThread { MediaController(context, browser.sessionToken) }

        val until = SystemClock.elapsedRealtime() + 60_000
        while (SystemClock.elapsedRealtime() < until && controller.playbackState?.state != PlaybackState.STATE_PAUSED)
            SystemClock.sleep(200)
        val state = controller.playbackState!!
        assertEquals("the car's player state", PlaybackState.STATE_PAUSED, state.state)
        assertNotEquals(0L, state.actions and PlaybackState.ACTION_PLAY)
        assertEquals(Library.lessonId(newest.series, newest.position), controller.metadata?.description?.mediaId)
        assertTrue("at ${state.position}", abs(state.position - 90_000) < 2_000)
        assertTrue(state.customActions.any { it.action == "back" })
    }
}
