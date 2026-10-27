package io.github.zvikaz.shiurim

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.ComponentName
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.webkit.JavascriptInterface
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.ImageButton
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.session.MediaController
import androidx.media3.session.SessionToken
import com.google.common.util.concurrent.ListenableFuture
import com.google.common.util.concurrent.MoreExecutors
import org.json.JSONArray
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat

/**
 * The app on the phone is the site itself. Its pages open here; any other link (a podcast app's, to add a series
 * to it, or another site's) opens in the app the phone has for it. A lesson the site's "listen" plays is played by
 * the app's player, as in Android Auto: so where it was left is kept, and it can be continued in the car.
 */
@UnstableApi
class MainActivity : Activity() {
    private lateinit var web: WebView
    private lateinit var miniPlayer: LinearLayout
    private lateinit var miniTitle: TextView
    private lateinit var miniSubtitle: TextView
    private lateinit var miniPlay: ImageButton
    private lateinit var miniProgress: ProgressBar
    private lateinit var controllerFuture: ListenableFuture<MediaController>
    private val controller get() = if (controllerFuture.isDone) controllerFuture.get() else null
    private val site = Uri.parse(BuildConfig.SITE_URL)
    private val positions by lazy { Positions(getSharedPreferences("positions", MODE_PRIVATE)) }
    private val handler = Handler(Looper.getMainLooper())
    private val tick = object : Runnable {
        override fun run() {
            updateMiniPlayer(controller)
            handler.postDelayed(this, 500)
        }
    }

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
        miniPlayer = makeMiniPlayer()
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(web, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
            addView(miniPlayer, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(76)))
        }
        ViewCompat.setOnApplyWindowInsetsListener(root) { view, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            view.setPadding(0, bars.top, 0, bars.bottom)
            insets
        }
        setContentView(root)
        if (savedInstanceState == null || web.restoreState(savedInstanceState) == null) web.loadUrl(BuildConfig.SITE_URL)
        if (Build.VERSION.SDK_INT >= 33) requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 0)
    }

    override fun onStart() {
        super.onStart()
        controllerFuture = MediaController.Builder(this, SessionToken(this, ComponentName(this, PlaybackService::class.java)))
            .buildAsync()
        controllerFuture.addListener({
            val controller = controller ?: return@addListener
            updateMiniPlayer(controller)
            controller.addListener(object : Player.Listener {
                override fun onEvents(player: Player, events: Player.Events) = updateMiniPlayer(player)
            })
            handler.removeCallbacks(tick)
            handler.post(tick)
        }, MoreExecutors.directExecutor())
    }

    override fun onStop() {
        handler.removeCallbacks(tick)
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

    /** A persistent, useful entry to the full player instead of Media3's context-free rectangular control strip. */
    private fun makeMiniPlayer(): LinearLayout {
        miniTitle = label(16f, Color.rgb(29, 28, 26), Typeface.BOLD).apply { maxLines = 1 }
        miniSubtitle = label(13f, Color.rgb(89, 86, 80)).apply { maxLines = 1 }
        val words = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_VERTICAL
            addView(miniTitle)
            addView(miniSubtitle)
        }
        miniPlay = ImageButton(this).apply {
            setImageResource(R.drawable.ic_play_rtl)
            scaleType = ImageView.ScaleType.CENTER
            setPadding(0, 0, 0, 0)
            background = rounded(Color.rgb(47, 93, 138), 28f)
            isFocusable = true
            setOnClickListener {
                controller?.let { player -> if (player.isPlaying) player.pause() else player.play() }
            }
        }
        miniProgress = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
            max = 1000
            layoutDirection = View.LAYOUT_DIRECTION_RTL
            progressTintList = android.content.res.ColorStateList.valueOf(Color.rgb(47, 93, 138))
            progressBackgroundTintList = android.content.res.ColorStateList.valueOf(Color.rgb(228, 225, 218))
        }
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            layoutDirection = View.LAYOUT_DIRECTION_RTL
            setPadding(dp(16), dp(7), dp(12), dp(5))
            addView(TextView(this@MainActivity).apply {
                text = "☊"
                textSize = 25f
                gravity = Gravity.CENTER
                setTextColor(Color.rgb(47, 93, 138))
                contentDescription = getString(R.string.app_name)
            }, LinearLayout.LayoutParams(dp(48), dp(48)))
            addView(words, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f).apply {
                marginStart = dp(10)
                marginEnd = dp(8)
            })
            addView(miniPlay, LinearLayout.LayoutParams(dp(52), dp(52)))
        }
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = GradientDrawable().apply {
                setColor(Color.rgb(251, 250, 247))
                setStroke(dp(1), Color.rgb(228, 225, 218))
            }
            elevation = dp(8).toFloat()
            visibility = View.GONE
            addView(miniProgress, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(3)))
            addView(row, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
            setOnClickListener { startActivity(Intent(this@MainActivity, NowPlayingActivity::class.java)) }
        }
    }

    private fun updateMiniPlayer(player: Player?) {
        if (player == null || player.mediaItemCount == 0) {
            miniPlayer.visibility = View.GONE
            return
        }
        miniPlayer.visibility = View.VISIBLE
        val metadata = player.mediaMetadata
        miniTitle.text = metadata.title ?: getString(R.string.app_name)
        miniSubtitle.text = metadata.artist ?: metadata.subtitle ?: ""
        miniPlay.setImageResource(if (player.isPlaying) R.drawable.ic_pause else R.drawable.ic_play_rtl)
        miniPlay.contentDescription = getString(if (player.isPlaying) R.string.pause else R.string.play)
        miniProgress.progress = if (player.duration > 0) (player.currentPosition * 1000 / player.duration).toInt() else 0
    }

    private fun label(size: Float, color: Int, style: Int = Typeface.NORMAL) = TextView(this).apply {
        textSize = size
        setTextColor(color)
        typeface = Typeface.create(Typeface.DEFAULT, style)
        gravity = Gravity.START
        ellipsize = android.text.TextUtils.TruncateAt.END
    }

    private fun rounded(color: Int, radius: Float) = GradientDrawable().apply {
        setColor(color)
        cornerRadius = dp(radius.toInt()).toFloat()
    }

    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()

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

        /** "heard", "started", or "" for a lesson shown by the site. */
        @JavascriptInterface
        fun state(lesson: String): String = lessonKey(lesson)?.let { key ->
            positions.progress(key)?.let { if (it.finished) "heard" else if (it.position > 0) "started" else "" }
        }.orEmpty()

        @JavascriptInterface
        fun markHeard(lesson: String) = lessonKey(lesson)?.let(positions::finished) ?: Unit

        @JavascriptInterface
        fun markUnheard(lesson: String) = lessonKey(lesson)?.let(positions::unfinished) ?: Unit

        @JavascriptInterface
        fun markSeriesHeard(series: String, lessonCount: Int) {
            if (series.isNotBlank() && '/' !in series && lessonCount in 1..10_000)
                positions.finishedSeries(series, lessonCount)
        }

        @JavascriptInterface
        fun markSeriesUnheard(series: String, lessonCount: Int) {
            if (series.isNotBlank() && '/' !in series && lessonCount in 1..10_000)
                positions.unfinishedSeries(series, lessonCount)
        }

        @JavascriptInterface
        fun removeFromContinue(lesson: String) = lessonKey(lesson)?.let(positions::dismiss) ?: Unit

        @JavascriptInterface
        fun recent(): String = JSONArray(positions.recent()).toString()

        private fun lessonKey(value: String): String? {
            val series = value.substringBeforeLast('/', "")
            val position = value.substringAfterLast('/', "").toIntOrNull()
            return value.takeIf { series.isNotBlank() && '\n' !in series && position != null && position > 0 }
        }
    }
}
