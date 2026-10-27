package io.github.zvikaz.shiurim

import android.content.SharedPreferences

/**
 * where a lesson was stopped, of how long it is (0 if not known yet), and whether it was heard to its end; and its
 * audio's address (null if kept before it was), which tells whether it's still the lesson of that number
 */
data class Progress(val position: Long, val duration: Long, val finished: Boolean, val url: String? = null) {
    val fraction get() = if (finished) 1.0 else if (duration > 0) position.toDouble() / duration else 0.0
}

/**
 * The listener's progress: each lesson's, and the series heard lately (newest first), which "continue" lists.
 * A lesson is "<series id>/<its number in the series>".
 */
class Positions(private val preferences: SharedPreferences) : Listening {
    private companion object {
        const val RECENT = "recent"
        const val RECENT_LIMIT = 30
        const val NEAR_END = 5_000L  // tolerate only player/timing imprecision right at the end
    }

    override fun progress(lesson: String): Progress? = preferences.getString("p:$lesson", null)?.split('|', limit = 4)?.let {
        Progress(it[0].toLong(), it[1].toLong(), it[2] == "1", it.getOrNull(3)?.ifEmpty { null })
    }

    private fun stored(progress: Progress) =
        "${progress.position}|${progress.duration}|${if (progress.finished) 1 else 0}|${progress.url ?: ""}"

    @Synchronized
    fun save(lesson: String, position: Long, duration: Long, url: String? = null) {
        val old = progress(lesson)?.takeIf { url == null || it.url == null || it.url == url }  // (not another's)
        // "Heard" is durable: replaying the beginning of a finished lesson must not make it unfinished again.
        val finished = old?.finished == true || duration > 0 && position >= duration - NEAR_END
        preferences.edit().putString("p:$lesson", stored(Progress(position, duration, finished, url ?: old?.url))).apply()
        heard(lesson)
    }

    @Synchronized
    fun finished(lesson: String, url: String? = null) {
        val old = progress(lesson)?.takeIf { url == null || it.url == null || it.url == url } ?: Progress(0, 0, false)
        preferences.edit().putString("p:$lesson", stored(old.copy(finished = true, url = url ?: old.url))).apply()
        heard(lesson)
    }

    /** Undo an explicit or automatic heard mark, keeping useful partial progress. */
    @Synchronized
    fun unfinished(lesson: String) {
        val old = progress(lesson) ?: return
        val position = if (old.duration > 0 && old.position >= old.duration - NEAR_END) 0 else old.position
        preferences.edit().putString("p:$lesson", stored(old.copy(position = position, finished = false))).apply()
        heard(lesson)
    }

    /** Mark every currently known lesson of a series as heard, and continue after its last one. */
    @Synchronized
    fun finishedSeries(series: String, lessons: Int) {
        if (lessons <= 0) return
        val editor = preferences.edit()
        for (position in 1..lessons) {
            val key = "$series/$position"
            val old = progress(key) ?: Progress(0, 0, false)
            editor.putString("p:$key", stored(old.copy(finished = true)))
        }
        editor.apply()
        heard("$series/$lessons")
    }

    @Synchronized
    fun unfinishedSeries(series: String, lessons: Int) {
        if (lessons <= 0) return
        val editor = preferences.edit()
        for (number in 1..lessons) {
            val key = "$series/$number"
            val old = progress(key) ?: continue
            val position = if (old.duration > 0 && old.position >= old.duration - NEAR_END) 0 else old.position
            editor.putString("p:$key", stored(old.copy(position = position, finished = false)))
        }
        editor.apply()
        heard("$series/1")
    }

    /** Remove this series' entry from Continue without changing any lesson's progress or heard state. */
    @Synchronized
    fun dismiss(lesson: String) {
        val series = lesson.substringBeforeLast('/')
        preferences.edit().putString(RECENT,
            recent().filter { it.substringBeforeLast('/') != series }.joinToString("\n")).apply()
    }

    /** the lesson last heard of each series heard lately, newest first */
    override fun recent(): List<String> = preferences.getString(RECENT, "")!!.split('\n').filter { it.isNotEmpty() }

    private fun heard(lesson: String) {
        val series = lesson.substringBeforeLast('/')
        val recent = listOf(lesson) + recent().filter { it.substringBeforeLast('/') != series }
        preferences.edit().putString(RECENT, recent.take(RECENT_LIMIT).joinToString("\n")).apply()
    }
}
