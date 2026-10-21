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
        const val NEAR_END = 5_000L  // tolerate only player/timing imprecision right at the end
    }

    override fun progress(lesson: String): Progress? = preferences.getString("p:$lesson", null)?.split('|')?.let {
        Progress(it[0].toLong(), it[1].toLong(), it[2] == "1")
    }

    @Synchronized
    fun save(lesson: String, position: Long, duration: Long) {
        // "Heard" is durable: replaying the beginning of a finished lesson must not make it unfinished again.
        val finished = progress(lesson)?.finished == true || duration > 0 && position >= duration - NEAR_END
        preferences.edit().putString("p:$lesson", "$position|$duration|${if (finished) 1 else 0}").apply()
        heard(lesson)
    }

    @Synchronized
    fun finished(lesson: String) {
        val duration = progress(lesson)?.duration ?: 0
        preferences.edit().putString("p:$lesson", "$duration|$duration|1").apply()
        heard(lesson)
    }

    /** Mark every currently known lesson of a series as heard, and continue after its last one. */
    @Synchronized
    fun finishedSeries(series: String, lessons: Int) {
        if (lessons <= 0) return
        val editor = preferences.edit()
        for (position in 1..lessons) {
            val key = "$series/$position"
            val duration = progress(key)?.duration ?: 0
            editor.putString("p:$key", "$duration|$duration|1")
        }
        editor.apply()
        heard("$series/$lessons")
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
