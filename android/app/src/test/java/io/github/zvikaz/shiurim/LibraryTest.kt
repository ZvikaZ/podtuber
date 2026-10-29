package io.github.zvikaz.shiurim

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class LibraryTest {
    private val catalog = Catalog.parse("""
        {"version":1,"updated":"2026-10-20T00:00:00+00:00",
         "groups":{"course":"סדרות","holiday":"חגים ומועדים","general":"שיעורים כלליים"},
         "ravs":[{"name":"הרב אוהד תירוש","series":3,"image":"ohad-tirosh.jpg"},{"name":"הרב יוסף קלנר","series":1,"image":"art/rav-1.png"}],
         "series":[
          {"id":"a","name":"יחסי הורים וילדים · תשע\"ג","rav":"הרב אוהד תירוש","group":"course","order":0,"lessons":3,"updated":"2013-02-01","years":"תשע\"ג","course":true,"art":"art/a.jpg"},
          {"id":"b","name":"פורים","rav":"הרב אוהד תירוש","group":"holiday","order":8,"lessons":2,"updated":"2024-03-01","years":"","course":false,"art":"art/b.jpg"},
          {"id":"c","name":"ראש השנה","rav":"הרב אוהד תירוש","group":"holiday","order":1,"lessons":1,"updated":"2023-09-01","years":"","course":false,"art":"art/c.jpg"},
          {"id":"d","name":"אגרות הראי\"ה","rav":"הרב יוסף קלנר","group":"course","order":0,"lessons":2,"updated":"2026-10-01","years":"","course":true,"art":"https://elsewhere/d.jpg","feed":"https://zvikaz.github.io/podtuber/d.rss","origin":"האתר של הרב"}],
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

    private val searchIndex = listOf(
        SearchEntry("a", 2, "שיעור 2", "על כיבוד אב ואם", "ח׳ חשון", 50, "https://x/a2.mp3"),
        SearchEntry("d", 1, "אגרת 1", "מתוך אגרות הראיה", "ח׳ חשון", 40, "https://x/d1.mp3"),
    )

    private fun library(listening: Listening = FakeListening(), lessons: Map<String, List<Lesson>> = this.lessons) = Library(object : Source {
        override fun catalog() = catalog
        override fun lessons(seriesId: String) = lessons.getValue(seriesId)
        override fun searchIndex() = searchIndex
    }, listening, Labels("המשך", "חדשים", "רבנים", { "$it סדרות" }, { "$it שיעורים" }, { "$it דק'" }))

    @Test
    fun `the root has the three tabs, the rabbis first, as a grid`() {
        val root = library().children(Library.ROOT)
        assertEquals(listOf("ravs", "newest", "continue"), root.map { it.id })
        assertEquals(true, root.first().grid)
    }

    @Test
    fun `a rav opens directly to all his series, ordered by kind and holidays by the year`() {
        val library = library()
        assertEquals(listOf("series/a", "series/c", "series/b"),
            library.children("rav/הרב אוהד תירוש").map { it.id })
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
        val continued = library(listening).children(Library.CONTINUE)
        assertEquals(listOf("lesson/a/2", "lesson/d/1"), continued.map { it.id })
        assertEquals(listOf(true, true), continued.map { it.dismissible })
    }

    @Test
    fun `search finds series by name and rav, despite quotes`() {
        val library = library()
        assertEquals(listOf("series/d"), library.search("אגרות הראיה").filter { it.browsable }.map { it.id })
        assertEquals(listOf("series/b"), library.search("פורים תירוש").filter { it.browsable }.map { it.id })
    }

    @Test
    fun `search finds lessons too, by their title or description, after the series`() {
        val library = library()
        assertEquals(listOf("lesson/a/2"), library.search("כיבוד אב").map { it.id })
        assertEquals("יחסי הורים וילדים · תשע\"ג · הרב אוהד תירוש", library.search("כיבוד אב").single().subtitle)
        assertEquals(listOf("series/d", "lesson/d/1"), library.search("אגרות").map { it.id })
    }

    @Test
    fun `a series whose artwork is elsewhere has its rav's, and every rav has an image`() {
        val library = library()
        assertEquals("art/rav-1.png", library.children("rav/הרב יוסף קלנר").single().art)
        assertEquals("art/a.jpg", library.children("series/a").first().art)
    }

    @Test
    fun `series and lessons can be added to a podcast app, by their series`() {
        val library = library()
        assertEquals("https://zvikaz.github.io/podtuber/d.rss", library.seriesOf("lesson/d/2")!!.feed)
        assertEquals("d", library.seriesOf("series/d")!!.id)
        assertEquals("d", library.children("series/d").first().series)
        assertNull(library.seriesOf("ravs"))
    }

    @Test
    fun `a series reports aggregate heard progress`() {
        val listening = FakeListening(mutableMapOf(
            "a/1" to Progress(10, 10, true),
            "a/2" to Progress(5, 10, false),
            "a/3" to Progress(10, 10, true),
        ))
        val progress = library(listening).node("series/a")!!.progress!!
        assertEquals(2L, progress.position)
        assertEquals(3L, progress.duration)
        assertEquals(false, progress.finished)
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

    /** series d, since a lesson of earlier date was added at its start: its lessons are now one number later */
    private val renumbered = lessons + ("d" to listOf(Lesson("d", 1, "אגרת 0", "א׳ חשון", 30, "https://x/d0.mp3", "")) +
        lessons.getValue("d").map { it.copy(position = it.position + 1) })

    @Test
    fun `continue follows a lesson renumbered since it was heard, and resumes where it was left`() {
        val listening = FakeListening(mutableMapOf("d/1" to Progress(5_000, 2_000_000, false, "https://x/d1.mp3")),
            mutableListOf("d/1"))
        val library = library(listening, renumbered)
        val continued = library.children(Library.CONTINUE).single()
        assertEquals("lesson/d/2", continued.id)
        assertEquals(5_000L, continued.progress!!.position)
        val queue = library.queue(continued.id)!!
        assertEquals("https://x/d1.mp3", queue.lessons[queue.start].url)
        assertEquals(5_000L, queue.position)
        assertEquals("lesson/d/2", library.play("").let { it!!.lessons[it.start].id })
    }

    @Test
    fun `a lesson isn't given the progress of another that had its number`() {
        val listening = FakeListening(mutableMapOf("d/1" to Progress(5_000, 2_000_000, true, "https://x/d1.mp3")),
            mutableListOf("d/1"))
        val library = library(listening, renumbered)
        assertNull(library.children("series/d").first().progress)  // the new lesson 1 wasn't heard
        assertEquals(0L, library.queue("lesson/d/1")!!.position)
        assertEquals(true, library.children("series/d")[1].progress!!.finished)  // the one heard, now 2
        // heard to its end, continue goes on to the lesson after it
        assertEquals("lesson/d/3", library.children(Library.CONTINUE).single().id)
    }

    @Test
    fun `resuming goes on after a lesson heard to its end, from where the next one was left`() {
        // (the phone app used to load the lesson heard last itself, to its start, even when it was heard to its end)
        val listening = FakeListening(
            mutableMapOf("a/1" to Progress(3_000_000, 3_000_000, true), "a/2" to Progress(60_000, 3_000_000, false)),
            mutableListOf("a/1"))
        val queue = library(listening).play("")!!
        assertEquals("lesson/a/2", queue.lessons[queue.start].id)
        assertEquals(60_000L, queue.position)
    }

    @Test
    fun `a lesson's line names the site it's from, after its series and rav`() {
        val library = library()
        assertEquals("אגרות הראי\"ה · הרב יוסף קלנר · האתר של הרב", library.children(Library.NEWEST).first().subtitle)
        assertEquals("אגרות הראי\"ה · הרב יוסף קלנר · האתר של הרב", library.search("מתוך אגרות").single().subtitle)
        assertEquals("2 שיעורים · האתר של הרב", library.children("rav/הרב יוסף קלנר").single().subtitle)
        // a series of no named site: as before
        assertEquals("פורים · הרב אוהד תירוש", library.children(Library.NEWEST)[1].subtitle)
    }
}
