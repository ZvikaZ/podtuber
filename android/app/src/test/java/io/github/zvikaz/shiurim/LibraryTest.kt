package io.github.zvikaz.shiurim

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class LibraryTest {
    private val catalog = Catalog.parse("""
        {"version":1,"updated":"2026-10-20T00:00:00+00:00",
         "groups":{"course":"סדרות","holiday":"חגים ומועדים","general":"שיעורים כלליים"},
         "ravs":[{"name":"הרב אוהד תירוש","series":3,"image":"ohad-tirosh.jpg"},{"name":"הרב יוסף קלנר","series":1,"image":null}],
         "series":[
          {"id":"a","name":"יחסי הורים וילדים · תשע\"ג","rav":"הרב אוהד תירוש","group":"course","order":0,"lessons":3,"updated":"2013-02-01","years":"תשע\"ג","course":true,"art":"art/a.jpg"},
          {"id":"b","name":"פורים","rav":"הרב אוהד תירוש","group":"holiday","order":8,"lessons":2,"updated":"2024-03-01","years":"","course":false,"art":"art/b.jpg"},
          {"id":"c","name":"ראש השנה","rav":"הרב אוהד תירוש","group":"holiday","order":1,"lessons":1,"updated":"2023-09-01","years":"","course":false,"art":"art/c.jpg"},
          {"id":"d","name":"אגרות הראי\"ה","rav":"הרב יוסף קלנר","group":"course","order":0,"lessons":2,"updated":"2026-10-01","years":"","course":true,"art":"art/d.jpg"}],
         "newest":[{"series":"d","position":2,"title":"אגרת ב","date":"2026-10-01","minutes":40,"url":"https://x/d2.mp3"},
                   {"series":"b","position":2,"title":"פורים ב","date":"2024-03-01","minutes":null,"url":"https://x/b2.mp3"}]}
    """.trimIndent())

    private val lessons = mapOf(
        "a" to (1..3).map { Lesson("a", it, "שיעור $it", "א׳ חשון", 50, "https://x/a$it.mp3", "") },
        "b" to (1..2).map { Lesson("b", it, "פורים $it", "י״ד אדר", null, "https://x/b$it.mp3", "") },
        "c" to listOf(Lesson("c", 1, "ראש השנה", "א׳ תשרי", 30, "https://x/c1.mp3", "")),
        "d" to (1..2).map { Lesson("d", it, "אגרת $it", "ח׳ חשון", 40, "https://x/d$it.mp3", "") },
    )

    private class FakeListening(val progress: MutableMap<String, Progress> = mutableMapOf(),
                                val recent: MutableList<String> = mutableListOf()) : Listening {
        override fun progress(lesson: String) = progress[lesson]
        override fun recent() = recent
    }

    private fun library(listening: Listening = FakeListening()) = Library(object : Source {
        override fun catalog() = catalog
        override fun lessons(seriesId: String) = lessons.getValue(seriesId)
    }, listening, Labels("המשך", "חדשים", "רבנים", { "$it סדרות" }, { "$it שיעורים" }, { "$it דק'" }))

    @Test
    fun `the root has the three tabs, the rabbis as a grid`() {
        val root = library().children(Library.ROOT)
        assertEquals(listOf("continue", "newest", "ravs"), root.map { it.id })
        assertEquals(true, root.last().grid)
    }

    @Test
    fun `a rav with series of several groups is shown by group, holidays in the order of the year`() {
        val library = library()
        assertEquals(listOf("group/course/הרב אוהד תירוש", "group/holiday/הרב אוהד תירוש"),
            library.children("rav/הרב אוהד תירוש").map { it.id })
        assertEquals(listOf("series/c", "series/b"), library.children("group/holiday/הרב אוהד תירוש").map { it.id })
        // one group: his series right away
        assertEquals(listOf("series/d"), library.children("rav/הרב יוסף קלנר").map { it.id })
    }

    @Test
    fun `a series' lessons are numbered and playable`() {
        val nodes = library().children("series/a")
        assertEquals(listOf("1. שיעור 1", "2. שיעור 2", "3. שיעור 3"), nodes.map { it.title })
        assertEquals("lesson/a/2", nodes[1].id)
        assertEquals("https://x/a2.mp3", nodes[1].url)
        assertEquals("א׳ חשון · 50 דק'", nodes[0].subtitle)
    }

    @Test
    fun `playing a lesson plays its series on from it, where it was left`() {
        val listening = FakeListening(mutableMapOf("a/2" to Progress(60_000, 3_000_000, false)))
        val queue = library(listening).queue("lesson/a/2")!!
        assertEquals(3, queue.lessons.size)
        assertEquals(1, queue.start)
        assertEquals(60_000L, queue.position)
        // a lesson heard to its end starts again from its beginning
        assertEquals(0L, library(FakeListening(mutableMapOf("a/2" to Progress(3_000_000, 3_000_000, true))))
            .queue("lesson/a/2")!!.position)
    }

    @Test
    fun `continue lists each series heard lately at its lesson to go on from`() {
        val listening = FakeListening(
            mutableMapOf("a/1" to Progress(3_000_000, 3_000_000, true), "d/1" to Progress(5_000, 2_000_000, false)),
            mutableListOf("a/1", "d/1"))
        assertEquals(listOf("lesson/a/2", "lesson/d/1"), library(listening).children(Library.CONTINUE).map { it.id })
    }

    @Test
    fun `search finds series by name and rav, despite quotes`() {
        val library = library()
        assertEquals(listOf("series/d"), library.search("אגרות הראיה").map { it.id })
        assertEquals(listOf("series/b"), library.search("פורים תירוש").map { it.id })
    }

    @Test
    fun `voice requests play a series on from where it was left, a rav's newest, or what was heard last`() {
        val listening = FakeListening(mutableMapOf("a/1" to Progress(3_000_000, 3_000_000, true)), mutableListOf("a/1"))
        val library = library(listening)
        assertEquals("lesson/a/2", library.play("יחסי הורים וילדים").let { it!!.lessons[it.start].id })
        assertEquals("lesson/d/2", library.play("הרב קלנר").let { it!!.lessons[it.start].id })
        assertEquals("lesson/a/2", library.play("").let { it!!.lessons[it.start].id })
        assertNull(library.play("משהו אחר לגמרי"))
    }
}
