package io.github.zvikaz.shiurim

import android.content.ComponentName
import android.media.browse.MediaBrowser
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.HandlerThread
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.CompletableFuture
import java.util.concurrent.TimeUnit

/**
 * The actions a car shows on a lesson or series in its lists (custom browse actions): "remove from Continue", "heard",
 * "add to podcasts". Cars with Android built in show only those with an icon's address, which they load. (Android
 * Auto shows none: it doesn't ask for them. There, the player has "remove from Continue": see CarPlayerTest.)
 *
 *     ./gradlew connectedDebugAndroidTest   (with an emulator or a phone connected)
 */
@RunWith(AndroidJUnit4::class)
class CarBrowseActionsTest {
    private val context = InstrumentationRegistry.getInstrumentation().targetContext
    private val thread = HandlerThread("car").apply { start() }
    private val handler = Handler(thread.looper)
    private lateinit var browser: MediaBrowser

    private fun <T> onThread(block: () -> T): T = CompletableFuture<T>().also { future ->
        handler.post { future.complete(block()) }
    }.get(10, TimeUnit.SECONDS)

    @After
    fun disconnect() {
        if (::browser.isInitialized) onThread { browser.disconnect() }
        thread.quitSafely()
    }

    @Test
    fun everyActionHasAnIconAndContinueEntriesCanBeRemoved() {
        // a lesson heard lately, so Continue has it
        val newest = CatalogRepository(context.filesDir, BuildConfig.SITE_URL).catalog().newest.first()
        Positions(context.getSharedPreferences("positions", 0))
            .save("${newest.series}/${newest.position}", 60_000, 0, newest.url)

        // connecting as a car that shows them does, saying how many it shows on an item
        val hints = Bundle().apply { putInt("androidx.media.utils.MediaBrowserCompat.extras.CUSTOM_BROWSER_ACTION_LIMIT", 5) }
        val connected = CompletableFuture<Unit>()
        browser = onThread {
            MediaBrowser(context, ComponentName(context, PlaybackService::class.java), object : MediaBrowser.ConnectionCallback() {
                override fun onConnected() { connected.complete(Unit) }
                override fun onConnectionFailed() { connected.completeExceptionally(IllegalStateException("refused")) }
            }, hints).apply { connect() }
        }
        connected.get(60, TimeUnit.SECONDS)  // (a slow emulator takes long to start the service)

        @Suppress("DEPRECATION")  // (its typed form is of Android 13 on)
        val actions = browser.extras!!.getParcelableArrayList<Bundle>("androidx.media.utils.extras.CUSTOM_BROWSER_ACTION_ROOT_LIST")!!
            .associateBy { it.getString("androidx.media.utils.extras.KEY_CUSTOM_BROWSER_ACTION_ID") }
        assertEquals(setOf("subscribe", "heard", "unheard", "dismiss"), actions.keys)
        for ((id, action) in actions) {
            val icon = action.getString("androidx.media.utils.extras.KEY_CUSTOM_BROWSER_ACTION_ICON_URI")
            assertTrue("$id has no icon", icon != null)
            context.contentResolver.openInputStream(Uri.parse(icon)).use { assertTrue("$id: $icon", it!!.read() >= 0) }
        }

        val children = CompletableFuture<List<MediaBrowser.MediaItem>>()
        onThread {
            browser.subscribe(Library.CONTINUE, object : MediaBrowser.SubscriptionCallback() {
                override fun onChildrenLoaded(parentId: String, items: MutableList<MediaBrowser.MediaItem>) {
                    children.complete(items)
                }
            })
        }
        val entry = children.get(60, TimeUnit.SECONDS).first()
        val ids = entry.description.extras!!.getStringArrayList("androidx.media.utils.extras.CUSTOM_BROWSER_ACTION_ID_LIST")!!
        assertTrue("$ids", "dismiss" in ids)
    }
}
