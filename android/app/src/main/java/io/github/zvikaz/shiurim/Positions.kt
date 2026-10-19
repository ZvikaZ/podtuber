package io.github.zvikaz.shiurim

import android.content.SharedPreferences

/** where a lesson was stopped, of how long it is (0 if not known yet), and whether it was heard to its end */
data class Progress(val position: Long, val duration: Long, val finished: Boolean) {
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
        const val NEAR_END = 30_000L  // a lesson stopped this close to its end was heard
    }

    override fun progress(lesson: String): Progress? = preferences.getString("p:$lesson", null)?.split('|')?.let {
        Progress(it[0].toLong(), it[1].toLong(), it[2] == "1")
    }

    fun save(lesson: String, position: Long, duration: Long) {
        val finished = duration > 0 && position >= duration - NEAR_END
        preferences.edit().putString("p:$lesson", "$position|$duration|${if (finished) 1 else 0}").apply()
        heard(lesson)
    }

    fun finished(lesson: String) {
        val duration = progress(lesson)?.duration ?: 0
        preferences.edit().putString("p:$lesson", "$duration|$duration|1").apply()
        heard(lesson)
    }

    /** the lesson last heard of each series heard lately, newest first */
    override fun recent(): List<String> = preferences.getString(RECENT, "")!!.split('\n').filter { it.isNotEmpty() }

    private fun heard(lesson: String) {
        val series = lesson.substringBeforeLast('/')
        val recent = listOf(lesson) + recent().filter { it.substringBeforeLast('/') != series }
        preferences.edit().putString(RECENT, recent.take(RECENT_LIMIT).joinToString("\n")).apply()
    }
}
