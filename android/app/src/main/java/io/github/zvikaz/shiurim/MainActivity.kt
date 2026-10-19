package io.github.zvikaz.shiurim

import android.Manifest
import android.app.Activity
import android.content.ComponentName
import android.os.Build
import android.os.Bundle
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.BaseAdapter
import android.widget.LinearLayout
import android.widget.ListView
import android.widget.TextView
import androidx.media3.common.MediaItem
import androidx.media3.session.MediaBrowser
import androidx.media3.session.SessionToken
import androidx.media3.ui.PlayerControlView
import com.google.common.util.concurrent.ListenableFuture
import com.google.common.util.concurrent.MoreExecutors

/**
 * The app on the phone: the same library Android Auto shows (rabbis, series, lessons), browsed as a list, and the
 * player's controls
 */
class MainActivity : Activity() {
    private lateinit var browserFuture: ListenableFuture<MediaBrowser>
    private val browser get() = if (browserFuture.isDone) browserFuture.get() else null
    private val path = ArrayDeque<Pair<String, String>>()  // the folders opened: id and title
    private val items = mutableListOf<MediaItem>()
    private lateinit var title: TextView
    private lateinit var back: TextView
    private lateinit var status: TextView
    private lateinit var list: ListView
    private lateinit var controls: PlayerControlView
    private val adapter = Adapter()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(layout())
        if (Build.VERSION.SDK_INT >= 33) requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 0)
    }

    override fun onStart() {
        super.onStart()
        browserFuture = MediaBrowser.Builder(this, SessionToken(this, ComponentName(this, PlaybackService::class.java)))
            .buildAsync()
        browserFuture.addListener({
            controls.player = browser
            if (path.isEmpty()) open(Library.ROOT, getString(R.string.app_name)) else show()
        }, MoreExecutors.directExecutor())
    }

    override fun onStop() {
        controls.player = null
        MediaBrowser.releaseFuture(browserFuture)
        super.onStop()
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (path.size > 1) {
            path.removeLast()
            show()
        } else {
            @Suppress("DEPRECATION")
            super.onBackPressed()
        }
    }

    private fun open(id: String, name: String) {
        path.addLast(id to name)
        show()
    }

    /** the folder last opened: its items, from the service */
    private fun show() {
        val (id, name) = path.last()
        title.text = name
        back.visibility = if (path.size > 1) View.VISIBLE else View.GONE
        status.text = ""
        val browser = browser ?: return
        val children = browser.getChildren(id, 0, Int.MAX_VALUE, null)
        children.addListener({
            if (path.lastOrNull()?.first != id) return@addListener  // opened another meanwhile
            val result = children.get()
            items.clear()
            result.value?.let { items.addAll(it) }
            if (result.value == null) status.text = getString(R.string.offline)
            else if (items.isEmpty() && id == Library.CONTINUE) status.text = getString(R.string.nothing_to_continue)
            adapter.notifyDataSetChanged()
            list.setSelection(0)
        }, mainExecutor)
    }

    private fun tapped(item: MediaItem) {
        if (item.mediaMetadata.isBrowsable == true) open(item.mediaId, item.mediaMetadata.title.toString())
        else browser?.run {
            setMediaItem(MediaItem.Builder().setMediaId(item.mediaId).build())
            prepare()
            play()
        }
    }

    private fun layout(): View {
        val padding = dp(16)
        title = TextView(this).apply {
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 22f)
            setTextColor(getColor(android.R.color.white))
            setPadding(padding, dp(12), padding, dp(12))
        }
        back = TextView(this).apply {
            text = "→ ${getString(R.string.back)}"
            setTextColor(getColor(android.R.color.white))
            setPadding(padding, dp(12), padding, dp(12))
            setOnClickListener { onBackPressed() }
        }
        val header = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setBackgroundColor(getColor(R.color.accent))
            addView(title, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            addView(back)
        }
        status = TextView(this).apply { setPadding(padding, padding, padding, 0); setTextColor(getColor(R.color.muted)) }
        list = ListView(this).apply {
            adapter = this@MainActivity.adapter
            setOnItemClickListener { _, _, position, _ -> tapped(items[position]) }
        }
        controls = PlayerControlView(this).apply { showTimeoutMs = 0 }
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(header)
            addView(status)
            addView(list, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
            addView(controls)
        }
    }

    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()

    private inner class Adapter : BaseAdapter() {
        override fun getCount() = items.size
        override fun getItem(position: Int) = items[position]
        override fun getItemId(position: Int) = position.toLong()

        override fun getView(position: Int, convertView: View?, parent: ViewGroup): View {
            val row = (convertView as? LinearLayout) ?: LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(dp(16), dp(10), dp(16), dp(10))
                addView(TextView(context).apply { setTextSize(TypedValue.COMPLEX_UNIT_SP, 17f); setTextColor(getColor(R.color.text)) })
                addView(TextView(context).apply { setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f); setTextColor(getColor(R.color.muted)) })
            }
            val metadata = items[position].mediaMetadata
            (row.getChildAt(0) as TextView).text = metadata.title
            val extras = metadata.extras
            val heard = extras?.getDouble(androidx.media3.session.MediaConstants.EXTRAS_KEY_COMPLETION_PERCENTAGE, -1.0) ?: -1.0
            val progress = when {
                heard >= 1.0 -> " · ✓"
                heard > 0 -> " · ${(heard * 100).toInt()}%"
                else -> ""
            }
            (row.getChildAt(1) as TextView).apply {
                text = "${metadata.subtitle ?: ""}$progress"
                visibility = if (text.isEmpty()) View.GONE else View.VISIBLE
            }
            return row
        }
    }
}
