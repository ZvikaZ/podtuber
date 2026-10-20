package io.github.zvikaz.shiurim

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.ComponentName
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.view.View
import android.view.ViewGroup
import android.webkit.JavascriptInterface
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.LinearLayout
import android.widget.Toast
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.session.MediaController
import androidx.media3.session.SessionToken
import androidx.media3.ui.PlayerControlView
import com.google.common.util.concurrent.ListenableFuture
import com.google.common.util.concurrent.MoreExecutors

/**
 * The app on the phone is the site itself. Its pages open here; any other link (a podcast app's, to add a series
 * to it, or another site's) opens in the app the phone has for it. A lesson the site's "listen" plays is played by
 * the app's player, as in Android Auto: so where it was left is kept, and it can be continued in the car.
 */
class MainActivity : Activity() {
    private lateinit var web: WebView
    private lateinit var controls: PlayerControlView
    private lateinit var controllerFuture: ListenableFuture<MediaController>
    private val controller get() = if (controllerFuture.isDone) controllerFuture.get() else null
    private val site = Uri.parse(BuildConfig.SITE_URL)

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        web = WebView(this).apply {
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            // the site's own pages only can call it (any other is opened outside the app)
            addJavascriptInterface(Bridge(), "ShiurimApp")
            webViewClient = object : WebViewClient() {
                override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                    if (ours(request.url)) return false
                    open(request.url)
                    return true
                }
            }
        }
        controls = PlayerControlView(this).apply { showTimeoutMs = 0; visibility = View.GONE }
        setContentView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(web, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
            addView(controls)
        })
        if (savedInstanceState == null || web.restoreState(savedInstanceState) == null) web.loadUrl(BuildConfig.SITE_URL)
        if (Build.VERSION.SDK_INT >= 33) requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 0)
    }

    override fun onStart() {
        super.onStart()
        controllerFuture = MediaController.Builder(this, SessionToken(this, ComponentName(this, PlaybackService::class.java)))
            .buildAsync()
        controllerFuture.addListener({
            val controller = controller ?: return@addListener
            controls.player = controller
            showControls(controller)
            controller.addListener(object : Player.Listener {
                override fun onEvents(player: Player, events: Player.Events) = showControls(player)
            })
        }, MoreExecutors.directExecutor())
    }

    override fun onStop() {
        controls.player = null
        MediaController.releaseFuture(controllerFuture)
        super.onStop()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        web.saveState(outState)
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (web.canGoBack()) web.goBack()
        else @Suppress("DEPRECATION") super.onBackPressed()
    }

    /** the player's controls, while there's something to play */
    private fun showControls(player: Player) {
        controls.visibility = if (player.mediaItemCount > 0) View.VISIBLE else View.GONE
    }

    private fun ours(url: Uri) = url.scheme == site.scheme && url.host == site.host && url.path.orEmpty().startsWith(site.path.orEmpty())

    private fun open(url: Uri) {
        try {
            startActivity(Intent(Intent.ACTION_VIEW, url))
        } catch (error: ActivityNotFoundException) {
            Toast.makeText(this, R.string.no_app, Toast.LENGTH_LONG).show()
        }
    }

    /** what the site calls when it's in the app (window.ShiurimApp) */
    private inner class Bridge {
        /** a lesson ("<series id>/<its number>") played by the app's player, its series on from it */
        @JavascriptInterface
        fun play(lesson: String) = runOnUiThread {
            controller?.run {
                setMediaItem(MediaItem.Builder().setMediaId(Library.lessonId(
                    lesson.substringBeforeLast('/'), lesson.substringAfterLast('/').toInt())).build())
                prepare()
                play()
            }
        }
    }
}
