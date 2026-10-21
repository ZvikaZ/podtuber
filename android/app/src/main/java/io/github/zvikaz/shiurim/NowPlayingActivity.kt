package io.github.zvikaz.shiurim

import android.app.Activity
import android.content.ComponentName
import android.content.res.ColorStateList
import android.graphics.BitmapFactory
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.ImageButton
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.SeekBar
import android.widget.Space
import android.widget.TextView
import androidx.media3.common.C
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.session.MediaController
import androidx.media3.session.SessionCommand
import androidx.media3.session.SessionToken
import com.google.common.util.concurrent.ListenableFuture
import com.google.common.util.concurrent.MoreExecutors
import java.util.Locale
import kotlin.math.roundToInt

/** The phone's full spoken-word player. Browsing stays in the WebView; listening has a native, stable home. */
@UnstableApi
class NowPlayingActivity : Activity() {
    private lateinit var controllerFuture: ListenableFuture<MediaController>
    private val controller get() = if (controllerFuture.isDone) controllerFuture.get() else null
    private val handler = Handler(Looper.getMainLooper())
    private lateinit var artwork: ImageView
    private lateinit var title: TextView
    private lateinit var subtitle: TextView
    private lateinit var elapsed: TextView
    private lateinit var duration: TextView
    private lateinit var seek: SeekBar
    private lateinit var play: ImageButton
    private lateinit var speed: TextView
    private lateinit var heard: TextView
    private var seeking = false
    private var artworkId = ""
    private val tick = object : Runnable {
        override fun run() {
            updateProgress(controller)
            handler.postDelayed(this, 500)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = Color.rgb(47, 93, 138)
        window.navigationBarColor = Color.rgb(251, 250, 247)
        setContentView(makePlayer())
    }

    override fun onStart() {
        super.onStart()
        controllerFuture = MediaController.Builder(this,
            SessionToken(this, ComponentName(this, PlaybackService::class.java))).buildAsync()
        controllerFuture.addListener({
            val player = controller ?: return@addListener
            update(player)
            player.addListener(object : Player.Listener {
                override fun onEvents(player: Player, events: Player.Events) = update(player)
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

    private fun makePlayer(): View {
        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutDirection = View.LAYOUT_DIRECTION_RTL
            setPadding(dp(24), dp(12), dp(24), dp(24))
        }
        val toolbar = LinearLayout(this).apply {
            gravity = Gravity.CENTER_VERTICAL
            addView(action(getString(R.string.close_player)) { finish() },
                LinearLayout.LayoutParams(dp(72), dp(48)))
            addView(label(getString(R.string.now_playing), 18f, Color.rgb(29, 28, 26), Typeface.BOLD).apply {
                gravity = Gravity.CENTER
            }, LinearLayout.LayoutParams(0, dp(48), 1f))
            addView(Space(this@NowPlayingActivity), LinearLayout.LayoutParams(dp(72), dp(48)))
        }
        artwork = ImageView(this).apply {
            scaleType = ImageView.ScaleType.CENTER_CROP
            setImageResource(R.mipmap.ic_launcher)
            background = rounded(Color.rgb(237, 242, 247), 20)
            clipToOutline = true
            elevation = dp(3).toFloat()
        }
        title = label(getString(R.string.no_lesson), 23f, Color.rgb(29, 28, 26), Typeface.BOLD).apply {
            gravity = Gravity.CENTER
            maxLines = 3
        }
        subtitle = label("", 16f, Color.rgb(89, 86, 80)).apply {
            gravity = Gravity.CENTER
            maxLines = 2
        }
        elapsed = label("0:00", 14f, Color.rgb(89, 86, 80)).apply { gravity = Gravity.START }
        duration = label("0:00", 14f, Color.rgb(89, 86, 80)).apply { gravity = Gravity.END }
        seek = SeekBar(this).apply {
            max = 1000
            layoutDirection = View.LAYOUT_DIRECTION_RTL
            progressTintList = ColorStateList.valueOf(Color.rgb(47, 93, 138))
            thumbTintList = ColorStateList.valueOf(Color.rgb(47, 93, 138))
            setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
                override fun onStartTrackingTouch(seekBar: SeekBar) { seeking = true }
                override fun onProgressChanged(seekBar: SeekBar, progress: Int, fromUser: Boolean) {
                    if (fromUser) controller?.duration?.takeIf { it > 0 }?.let {
                        elapsed.text = time(it * progress / 1000)
                    }
                }
                override fun onStopTrackingTouch(seekBar: SeekBar) {
                    controller?.duration?.takeIf { it > 0 }?.let { controller?.seekTo(it * seekBar.progress / 1000) }
                    seeking = false
                }
            })
        }
        play = primaryAction {
            controller?.let { if (it.isPlaying) it.pause() else it.play() }
        }
        speed = control("1×") { command("speed") }
        val back = control("↶\n30") { controller?.seekBack() }
        val forward = control("↷\n30") { controller?.seekForward() }
        val next = control(getString(R.string.next_short)) { controller?.seekToNextMediaItem() }
        heard = action(getString(R.string.mark_heard)) { command("heard"); heard.text = getString(R.string.heard) }
        val subscribe = action(getString(R.string.subscribe_short)) { command("subscribe") }

        content.addView(toolbar)
        content.addView(artwork, LinearLayout.LayoutParams(dp(292), dp(292)).apply {
            gravity = Gravity.CENTER_HORIZONTAL
            topMargin = dp(12)
            bottomMargin = dp(24)
        })
        content.addView(title, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        content.addView(subtitle, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
            topMargin = dp(6)
            bottomMargin = dp(16)
        })
        content.addView(seek, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(42)))
        content.addView(LinearLayout(this).apply {
            layoutDirection = View.LAYOUT_DIRECTION_RTL
            addView(elapsed, LinearLayout.LayoutParams(0, dp(28), 1f))
            addView(duration, LinearLayout.LayoutParams(0, dp(28), 1f))
        })
        content.addView(LinearLayout(this).apply {
            gravity = Gravity.CENTER
            layoutDirection = View.LAYOUT_DIRECTION_RTL
            addView(speed, weighted())
            addView(back, weighted())
            addView(play, LinearLayout.LayoutParams(dp(68), dp(68)).apply { marginStart = dp(8); marginEnd = dp(8) })
            addView(forward, weighted())
            addView(next, weighted())
        }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(84)).apply { topMargin = dp(8) })
        content.addView(LinearLayout(this).apply {
            gravity = Gravity.CENTER
            addView(heard, LinearLayout.LayoutParams(0, dp(48), 1f).apply { marginEnd = dp(6) })
            addView(subscribe, LinearLayout.LayoutParams(0, dp(48), 1f).apply { marginStart = dp(6) })
        }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(56)).apply { topMargin = dp(12) })
        return ScrollView(this).apply {
            setBackgroundColor(Color.rgb(251, 250, 247))
            isFillViewport = true
            addView(content)
        }
    }

    private fun update(player: Player) {
        val metadata = player.mediaMetadata
        title.text = metadata.title ?: getString(R.string.no_lesson)
        subtitle.text = metadata.artist ?: metadata.subtitle ?: ""
        play.setImageResource(if (player.isPlaying) R.drawable.ic_pause else R.drawable.ic_play_rtl)
        play.contentDescription = getString(if (player.isPlaying) R.string.pause else R.string.play)
        speed.text = speedText(player.playbackParameters.speed)
        updateProgress(player)
        loadArtwork(player.currentMediaItem?.mediaId.orEmpty(), metadata.artworkUri)
    }

    private fun updateProgress(player: Player?) {
        if (player == null) return
        val total = player.duration.takeIf { it != C.TIME_UNSET && it > 0 } ?: 0
        if (!seeking) {
            seek.progress = if (total > 0) (player.currentPosition * 1000 / total).toInt() else 0
            elapsed.text = time(player.currentPosition)
        }
        duration.text = if (total > 0) time(total) else "—:—"
    }

    private fun loadArtwork(id: String, uri: android.net.Uri?) {
        if (id == artworkId) return
        artworkId = id
        artwork.setImageResource(R.mipmap.ic_launcher)
        if (uri == null) return
        Thread {
            val bitmap = runCatching { contentResolver.openInputStream(uri)?.use(BitmapFactory::decodeStream) }.getOrNull()
            runOnUiThread { if (artworkId == id && bitmap != null) artwork.setImageBitmap(bitmap) }
        }.start()
    }

    private fun command(action: String) {
        controller?.sendCustomCommand(SessionCommand(action, Bundle.EMPTY), Bundle.EMPTY)
    }

    private fun control(text: String, click: () -> Unit) = action(text, click).apply {
        textSize = 16f
        background = null
    }

    private fun primaryAction(click: () -> Unit) = ImageButton(this).apply {
        setImageResource(R.drawable.ic_play_rtl)
        scaleType = ImageView.ScaleType.CENTER
        setPadding(0, 0, 0, 0)
        background = rounded(Color.rgb(47, 93, 138), 34)
        isClickable = true
        isFocusable = true
        setOnClickListener { click() }
    }

    private fun action(text: String, click: () -> Unit) = TextView(this).apply {
        this.text = text
        textSize = 15f
        setTextColor(Color.rgb(47, 93, 138))
        gravity = Gravity.CENTER
        isClickable = true
        isFocusable = true
        setPadding(dp(6), dp(4), dp(6), dp(4))
        background = GradientDrawable().apply {
            setColor(Color.TRANSPARENT)
            setStroke(dp(1), Color.rgb(228, 225, 218))
            cornerRadius = dp(12).toFloat()
        }
        setOnClickListener { click() }
    }

    private fun label(text: String, size: Float, color: Int, style: Int = Typeface.NORMAL) = TextView(this).apply {
        this.text = text
        textSize = size
        setTextColor(color)
        typeface = Typeface.create(Typeface.DEFAULT, style)
    }

    private fun weighted() = LinearLayout.LayoutParams(0, dp(60), 1f)
    private fun rounded(color: Int, radius: Int) = GradientDrawable().apply {
        setColor(color)
        cornerRadius = dp(radius).toFloat()
    }
    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()
    private fun time(milliseconds: Long): String {
        val seconds = (milliseconds.coerceAtLeast(0) / 1000).toInt()
        return if (seconds >= 3600) String.format(Locale.getDefault(), "%d:%02d:%02d", seconds / 3600,
            seconds / 60 % 60, seconds % 60)
        else String.format(Locale.getDefault(), "%d:%02d", seconds / 60, seconds % 60)
    }

    private fun speedText(value: Float): String {
        val tenths = (value * 10).roundToInt()
        return if (tenths % 10 == 0) "${tenths / 10}×" else "${tenths / 10}.${tenths % 10}×"
    }
}
