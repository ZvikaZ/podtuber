package io.github.zvikaz.shiurim

/** where the library's lessons and the listener's progress come from (the site and the phone; fakes in tests) */
interface Source {
    fun catalog(): Catalog
    fun lessons(seriesId: String): List<Lesson>
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
)

data class Queue(val lessons: List<Node>, val start: Int, val position: Long)

/**
 * The browse tree, as Android Auto and the phone show it:
 *   root: continue (the series heard lately, each at its next lesson), newest lessons, the rabbis
 *   a rav: his series, in groups (courses, holidays, general lessons) when he has more than one
 *   a series: its lessons, numbered, with how much of each was heard
 * Ids: "continue", "newest", "ravs", "rav/<name>", "group/<group>/<rav>", "series/<id>", "lesson/<series id>/<number>"
 */
class Library(private val source: Source, private val listening: Listening, private val labels: Labels) {
    companion object {
        const val ROOT = "root"
        const val CONTINUE = "continue"
        const val NEWEST = "newest"
        const val RAVS = "ravs"
        private val GROUP_ORDER = listOf("course", "holiday", "general")
        private const val SEARCH_LIMIT = 50

        fun lessonId(series: String, position: Int) = "lesson/$series/$position"
        /** a lesson id's "<series id>/<number>" (as Positions keeps it), series id and number */
        fun lessonKey(id: String) = id.removePrefix("lesson/")
        fun lessonParts(id: String) = lessonKey(id).let { it.substringBeforeLast('/') to it.substringAfterLast('/').toInt() }
    }

    fun root() = listOf(
        Node(CONTINUE, labels.continueTab, browsable = true, art = "icon:continue"),
        Node(NEWEST, labels.newestTab, browsable = true, art = "icon:newest"),
        Node(RAVS, labels.ravsTab, browsable = true, art = "icon:ravs", grid = true),
    )

    fun children(id: String): List<Node> = when {
        id == ROOT -> root()
        id == CONTINUE -> continueListening()
        id == NEWEST -> source.catalog().newest.mapNotNull { newest ->
            val series = source.catalog().series(newest.series) ?: return@mapNotNull null
            Node(lessonId(newest.series, newest.position), newest.title, "${series.name} · ${series.rav}",
                art = series.art, progress = listening.progress("${newest.series}/${newest.position}"), url = newest.url)
        }
        id == RAVS -> source.catalog().ravs.map {
            Node("rav/${it.name}", it.name, labels.seriesCount(it.seriesCount), browsable = true, art = it.image)
        }
        id.startsWith("rav/") -> {
            val rav = id.removePrefix("rav/")
            val series = source.catalog().seriesOf(rav)
            val groups = GROUP_ORDER.filter { group -> series.any { it.group == group } }
            if (groups.size > 1) groups.map { group ->
                Node("group/$group/$rav", source.catalog().groups[group] ?: group,
                    labels.seriesCount(series.count { it.group == group }), browsable = true)
            } else sorted(series).map(::seriesNode)
        }
        id.startsWith("group/") -> {
            val (group, rav) = id.removePrefix("group/").let { it.substringBefore('/') to it.substringAfter('/') }
            sorted(source.catalog().seriesOf(rav).filter { it.group == group }).map(::seriesNode)
        }
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

    /** the series and lessons a search finds: every word of it, in the series' name or rav, or the lesson's title */
    fun search(query: String): List<Node> {
        val words = normalize(query).split(' ').filter { it.isNotEmpty() }
        if (words.isEmpty()) return emptyList()
        fun matches(text: String) = normalize(text).let { normalized -> words.all { it in normalized } }
        val catalog = source.catalog()
        val series = catalog.series.filter { matches("${it.name} ${it.rav}") }
        val lessons = catalog.newest.filter { matches(it.title) }.mapNotNull { newest ->
            catalog.series(newest.series)?.let { Node(lessonId(it.id, newest.position), newest.title, it.name, art = it.art, url = newest.url) }
        }
        return (sorted(series).map(::seriesNode) + lessons).take(SEARCH_LIMIT)
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
        val rav = catalog.ravs.maxByOrNull { score(it.name) }?.takeIf { score(it.name) > 0 } ?: return null
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
            Node(lessonId(seriesId, lesson.position), "${lesson.position}. ${lesson.title}", details, art = series.art,
                progress = listening.progress("$seriesId/${lesson.position}"), url = lesson.url)
        }
    }

    private fun seriesNode(series: Series) = Node(
        "series/${series.id}", series.name,
        listOf(labels.lessonsCount(series.lessons), series.years).filter { it.isNotEmpty() }.joinToString(" · "),
        browsable = true, art = series.art,
    )

    /** holidays in the order of the year; any other series by name */
    private fun sorted(series: List<Series>) = series.sortedWith(compareBy<Series>({ GROUP_ORDER.indexOf(it.group) },
        { if (it.group == "holiday") it.order else 0 }, { it.name }))

    /** for searching: no niqqud, quotes or gershayim; common spellings as one ('אלוקים', 'אלקים') */
    private fun normalize(text: String) = text.replace(Regex("[֑-ׇ]"), "")
        .replace(Regex("[\"'`״׳’‘”“]"), "").lowercase()
        .replace("אלוק", "אלק").replace("וו", "ו").replace("יי", "י")
        .split(Regex("\\s+")).joinToString(" ").trim()
}
