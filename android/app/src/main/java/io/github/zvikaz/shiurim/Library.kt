package io.github.zvikaz.shiurim

/** where the library's lessons and the listener's progress come from (the site and the phone; fakes in tests) */
interface Source {
    fun catalog(): Catalog
    fun lessons(seriesId: String): List<Lesson>
    fun searchIndex(): List<SearchEntry>
}

interface Listening {
    fun progress(lesson: String): Progress?
    fun recent(): List<String>
}

/** the texts the library shows, from the app's resources */
data class Labels(
    val continueTab: String, val newestTab: String, val ravsTab: String,
    val seriesCount: (Int) -> String, val lessonsCount: (Int) -> String, val minutes: (Int) -> String,
)

/** a node of the browse tree: a folder (browsable), or a lesson (playable) */
data class Node(
    val id: String, val title: String, val subtitle: String = "", val browsable: Boolean = false,
    val art: String? = null,  // an image of the site (a path in it), or one of the app's icons ("icon:<name>")
    val progress: Progress? = null, val grid: Boolean = false,  // grid: its children shown as a grid
    val url: String? = null,  // a lesson's audio
    val series: String? = null,  // a series', or a lesson's: which can be added to a podcast app
)

data class Queue(val lessons: List<Node>, val start: Int, val position: Long)

/**
 * The browse tree, as Android Auto and the phone show it:
 *   root: the rabbis, the newest lessons, continue (the series heard lately, each at its next lesson)
 *   a rav: his series, ordered by courses, holidays, and general lessons
 *   a series: its lessons, numbered, with how much of each was heard
 * Ids: "continue", "newest", "ravs", "rav/<name>", "series/<id>", "lesson/<series id>/<number>"
 */
class Library(private val source: Source, private val listening: Listening, private val labels: Labels) {
    companion object {
        const val ROOT = "root"
        const val CONTINUE = "continue"
        const val NEWEST = "newest"
        const val RAVS = "ravs"
        private val GROUP_ORDER = listOf("course", "holiday", "general")
        private const val SEARCH_LIMIT = 60
        private const val SERIES_FOUND = 20

        fun lessonId(series: String, position: Int) = "lesson/$series/$position"
        /** a lesson id's "<series id>/<number>" (as Positions keeps it), series id and number */
        fun lessonKey(id: String) = id.removePrefix("lesson/")
        fun lessonParts(id: String) = lessonKey(id).let { it.substringBeforeLast('/') to it.substringAfterLast('/').toInt() }
    }

    fun root() = listOf(
        Node(RAVS, labels.ravsTab, browsable = true, art = "icon:ravs", grid = true),
        Node(NEWEST, labels.newestTab, browsable = true, art = "icon:newest"),
        Node(CONTINUE, labels.continueTab, browsable = true, art = "icon:continue"),
    )

    fun children(id: String): List<Node> = when {
        id == ROOT -> root()
        id == CONTINUE -> continueListening()
        id == NEWEST -> source.catalog().newest.mapNotNull { newest ->
            val series = source.catalog().series(newest.series) ?: return@mapNotNull null
            Node(lessonId(newest.series, newest.position), newest.title, "${series.name} · ${series.rav}",
                art = art(series), progress = listening.progress("${newest.series}/${newest.position}"), url = newest.url,
                series = series.id)
        }
        id == RAVS -> source.catalog().ravs.map {
            Node("rav/${it.name}", it.name, labels.seriesCount(it.seriesCount), browsable = true, art = it.image)
        }
        id.startsWith("rav/") -> sorted(source.catalog().seriesOf(id.removePrefix("rav/"))).map(::seriesNode)
        id.startsWith("series/") -> lessonNodes(id.removePrefix("series/"))
        else -> emptyList()
    }

    /** a node by its id (what Android Auto asks for a node it has kept, such as the one playing) */
    fun node(id: String): Node? = when {
        id.startsWith("lesson/") -> {
            val (series, position) = lessonParts(id)
            lessonNodes(series).getOrNull(position - 1)
        }
        id.startsWith("series/") -> source.catalog().series(id.removePrefix("series/"))?.let(::seriesNode)
        else -> (root() + children(RAVS)).find { it.id == id }
    }

    /** playing a lesson plays its series on from it, from where it was stopped */
    fun queue(lessonId: String): Queue? {
        val (series, position) = lessonParts(lessonId)
        val lessons = lessonNodes(series).ifEmpty { return null }
        val start = (position - 1).coerceIn(lessons.indices)
        val progress = lessons[start].progress
        return Queue(lessons, start, if (progress != null && !progress.finished) progress.position else 0)
    }

    /**
     * What a search finds, as the site's does: the series with every word of it in their name or rav, then the
     * lessons with every word in their title or description (of all lessons, from the site's search index; of the
     * newest only, if it can't be had)
     */
    fun search(query: String): List<Node> {
        val words = normalize(query).split(' ').filter { it.isNotEmpty() }
        if (words.isEmpty()) return emptyList()
        fun matches(text: String) = normalize(text).let { normalized -> words.all { it in normalized } }
        val catalog = source.catalog()
        val series = sorted(catalog.series.filter { matches("${it.name} ${it.rav}") }).take(SERIES_FOUND)
        val index = runCatching { source.searchIndex() }.getOrNull()
            ?: catalog.newest.map { SearchEntry(it.series, it.position, it.title, "", it.date, it.minutes, it.url) }
        val lessons = index.asSequence().filter { matches("${it.title} ${it.description}") }
            .mapNotNull { entry -> catalog.series(entry.series)?.let { foundLesson(entry, it) } }
            .take(SEARCH_LIMIT - series.size).toList()
        return series.map(::seriesNode) + lessons
    }

    private fun foundLesson(entry: SearchEntry, series: Series) = Node(
        lessonId(series.id, entry.position), entry.title, "${series.name} · ${series.rav}", art = art(series),
        progress = listening.progress("${series.id}/${entry.position}"), url = entry.url, series = series.id)

    /** the series a node is, or is of (for adding it to a podcast app) */
    fun seriesOf(id: String): Series? = when {
        id.startsWith("series/") -> source.catalog().series(id.removePrefix("series/"))
        id.startsWith("lesson/") -> source.catalog().series(lessonParts(id).first)
        else -> null
    }

    /**
     * What "play <query>" plays: with none, what was heard last (or the newest lesson); a series, on from where it was
     * left; a rav, his newest lesson
     */
    fun play(query: String): Queue? {
        val catalog = source.catalog()
        if (normalize(query).isBlank()) {
            val next = continueListening().firstOrNull()?.id ?: catalog.newest.firstOrNull()?.let { lessonId(it.series, it.position) }
            return next?.let(::queue)
        }
        val words = normalize(query).split(' ').filter { it.isNotEmpty() && it != "הרב" }
        fun score(text: String) = normalize(text).let { normalized -> words.count { it in normalized } }
        val series = catalog.series.maxByOrNull { score(it.name) * 2 + score(it.rav) }
            ?.takeIf { score(it.name) > 0 && score(it.name) * 2 + score(it.rav) >= words.size }
        if (series != null) return queue(nextIn(series))
        val rav = catalog.ravs.maxByOrNull { score(it.name) }?.takeIf { score(it.name) > 0 }
            ?: return search(query).firstOrNull { !it.browsable }?.let { queue(it.id) }  // a lesson, by its title
        val newest = catalog.newest.firstOrNull { catalog.series(it.series)?.rav == rav.name }
            ?: catalog.seriesOf(rav.name).maxByOrNull { it.updated }?.let { Newest(it.id, it.lessons, "", "", null, "") }
        return newest?.let { queue(lessonId(it.series, it.position)) }
    }

    /** the series heard lately, each at its lesson to continue: the one left in the middle, or the next */
    private fun continueListening(): List<Node> = listening.recent().mapNotNull { key ->
        val (seriesId, position) = lessonParts(key)
        val lessons = runCatching { lessonNodes(seriesId) }.getOrDefault(emptyList())
        val progress = listening.progress(key)
        val index = if (progress?.finished == true) position else position - 1
        val series = source.catalog().series(seriesId) ?: return@mapNotNull null
        lessons.getOrNull(index)?.copy(subtitle = "${series.name} · ${series.rav}")
    }

    /** a series' lesson to go on from: the last one heard, or after it; else its first (a course) or newest */
    private fun nextIn(series: Series): String {
        val heard = listening.recent().firstOrNull { it.substringBeforeLast('/') == series.id }
        if (heard != null) {
            val position = heard.substringAfterLast('/').toInt()
            val next = if (listening.progress(heard)?.finished == true) position + 1 else position
            if (next <= series.lessons) return lessonId(series.id, next)
        }
        return lessonId(series.id, if (series.course) 1 else series.lessons)
    }

    private fun lessonNodes(seriesId: String): List<Node> {
        val series = source.catalog().series(seriesId) ?: return emptyList()
        return source.lessons(seriesId).map { lesson ->
            val details = listOfNotNull(lesson.date, lesson.minutes?.let(labels.minutes)).joinToString(" · ")
            Node(lessonId(seriesId, lesson.position), "${lesson.position}. ${lesson.title}", details, art = art(series),
                progress = listening.progress("$seriesId/${lesson.position}"), url = lesson.url, series = seriesId)
        }
    }

    private fun seriesNode(series: Series) = Node(
        "series/${series.id}", series.name,
        listOf(labels.lessonsCount(series.lessons), series.years).filter { it.isNotEmpty() }.joinToString(" · "),
        browsable = true, art = art(series), series = series.id,
    )

    /** a series' artwork: its own, if the site has it (a podcast published elsewhere has its own elsewhere), or its rav's */
    private fun art(series: Series) = series.art.takeIf { it.isNotEmpty() && "://" !in it }
        ?: source.catalog().rav(series.rav)?.image

    /** holidays in the order of the year; any other series by name */
    private fun sorted(series: List<Series>) = series.sortedWith(compareBy<Series>({ GROUP_ORDER.indexOf(it.group) },
        { if (it.group == "holiday") it.order else 0 }, { it.name }))

    /** for searching: no niqqud, quotes or gershayim; common spellings as one ('אלוקים', 'אלקים') */
    private fun normalize(text: String) = text.replace(Regex("[֑-ׇ]"), "")
        .replace(Regex("[\"'`״׳’‘”“]"), "").lowercase()
        .replace("אלוק", "אלק").replace("וו", "ו").replace("יי", "י")
        .split(Regex("\\s+")).joinToString(" ").trim()
}
