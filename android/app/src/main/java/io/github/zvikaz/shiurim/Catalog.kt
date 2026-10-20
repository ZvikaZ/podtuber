package io.github.zvikaz.shiurim

import android.util.JsonReader
import android.util.JsonToken
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/**
 * What the site publishes for the app (podtuber/index_page.py's write_catalog): the rabbis, their series and the
 * newest lessons; and a series' lessons, in a file of its own.
 */
data class Rav(val name: String, val seriesCount: Int, val image: String?)

data class Series(
    val id: String, val name: String, val rav: String, val group: String, val order: Int, val lessons: Int,
    val updated: String, val years: String, val course: Boolean, val art: String,
    val feed: String,  // its podcast feed, for adding it to a podcast app
)

data class Newest(
    val series: String, val position: Int, val title: String, val date: String, val minutes: Int?, val url: String,
)

/** a lesson as the site's search index has it: its series, title, the start of its description, and so on */
data class SearchEntry(
    val series: String, val position: Int, val title: String, val description: String, val date: String,
    val minutes: Int?, val url: String,
)

data class Lesson(
    val series: String, val position: Int, val title: String, val date: String, val minutes: Int?, val url: String,
    val description: String,
)

class Catalog(
    val ravs: List<Rav>, val series: List<Series>, val newest: List<Newest>, val groups: Map<String, String>,
    val search: String = "",  // the site's search index (its name changes with its contents)
) {
    private val byId = series.associateBy { it.id }
    fun series(id: String) = byId[id]
    fun seriesOf(rav: String) = series.filter { it.rav == rav }
    fun rav(name: String) = ravs.find { it.name == name }

    companion object {
        const val VERSION = 1  // the catalog's version this app reads

        fun parse(text: String): Catalog {
            val json = JSONObject(text)
            if (json.optInt("version") > VERSION) throw IOException("catalog version ${json.optInt("version")}")
            val groups = json.getJSONObject("groups").let { groups -> groups.keys().asSequence().associateWith { groups.getString(it) } }
            return Catalog(
                ravs = json.getJSONArray("ravs").objects().map {
                    Rav(it.getString("name"), it.getInt("series"), it.optStringOrNull("image"))
                },
                series = json.getJSONArray("series").objects().map {
                    Series(it.getString("id"), it.getString("name"), it.getString("rav"), it.getString("group"),
                        it.optInt("order"), it.getInt("lessons"), it.getString("updated"), it.optString("years"),
                        it.optBoolean("course"), it.optString("art"), it.optString("feed"))
                },
                newest = json.getJSONArray("newest").objects().map {
                    Newest(it.getString("series"), it.getInt("position"), it.getString("title"), it.getString("date"),
                        it.optIntOrNull("minutes"), it.getString("url"))
                },
                groups = groups,
                search = json.optString("search"),
            )
        }

        /** a series' lessons file: [title, date, minutes, audio url, description] each, in order */
        fun parseLessons(series: String, text: String): List<Lesson> =
            JSONArray(text).let { lessons ->
                (0 until lessons.length()).map { index ->
                    val lesson = lessons.getJSONArray(index)
                    Lesson(series, index + 1, lesson.getString(0), lesson.getString(1),
                        if (lesson.isNull(2)) null else lesson.getInt(2), lesson.getString(3), lesson.optString(4))
                }
            }
    }
}

private fun JSONArray.objects() = (0 until length()).map { getJSONObject(it) }
private fun JSONObject.optStringOrNull(key: String) = if (isNull(key)) null else optString(key).ifEmpty { null }
private fun JSONObject.optIntOrNull(key: String) = if (isNull(key)) null else optInt(key)

/**
 * The catalog and the series' lessons, from the site, kept in the phone's files: from there while they're current
 * (Android Auto expects content in seconds), from the site when they're not, and as kept when the site can't be
 * reached (which isn't tried again for a while: offline, in the car, each try would wait for its timeout)
 */
class CatalogRepository(private val directory: File, private val siteUrl: String,
                        private val maxAge: Long = 6 * 60 * 60 * 1000L) : Source {
    private companion object {
        const val RETRY_AFTER = 10 * 60 * 1000L
        const val TIMEOUT = 8000
    }

    private var catalog: Catalog? = null
    private val lessons = mutableMapOf<String, Pair<String?, List<Lesson>>>()  // by series: as of its update
    private var offlineUntil = 0L
    private var searchIndex: Pair<String, List<SearchEntry>>? = null

    /** the catalog; throws if it was never fetched and the site can't be reached */
    @Synchronized
    override fun catalog(): Catalog {
        val file = File(directory, "catalog.json")
        val current = file.exists() && System.currentTimeMillis() - file.lastModified() < maxAge
        catalog?.let { if (current || offline()) return it }
        val text = if (current) file.readText() else fetchOrKept(file, "catalog.json")
        return Catalog.parse(text).also { catalog = it }
    }

    /** a series' lessons, as of its last update in the catalog (a newer one fetches them again) */
    @Synchronized
    override fun lessons(seriesId: String): List<Lesson> {
        val updated = catalog().series(seriesId)?.updated
        lessons[seriesId]?.let { (asOf, kept) -> if (asOf == updated || offline()) return kept }
        val file = File(directory, "lessons/$seriesId.json")
        val stamp = File(directory, "lessons/$seriesId.updated")
        val current = file.exists() && stamp.exists() && stamp.readText() == updated
        val text = if (current) file.readText() else fetchOrKept(file, "lessons/$seriesId.json") {
            if (updated != null) stamp.writeText(updated)
        }
        return Catalog.parseLessons(seriesId, text).also { lessons[seriesId] = (if (current) updated else stamp.takeIf { it.exists() }?.readText()) to it }
    }

    /**
     * every lesson, from the site's search index: fetched once per version of it (its name changes with it), and
     * kept; read as a stream, as it's big
     */
    @Synchronized
    override fun searchIndex(): List<SearchEntry> {
        val name = catalog().search.ifEmpty { return emptyList() }
        searchIndex?.let { (kept, entries) -> if (kept == name) return entries }
        val file = File(directory, "search/$name")
        if (!file.exists()) {
            fetchOrKept(file, name)
            file.parentFile?.listFiles()?.filter { it.name != name }?.forEach { it.delete() }  // older versions
        }
        val entries = JsonReader(file.bufferedReader()).use { reader -> readSearchIndex(reader) }
        searchIndex = name to entries
        return entries
    }

    /** {"series": [[id, name, rav], ...], "lessons": [[series index, title, description, date, minutes, position, url], ...]} */
    private fun readSearchIndex(reader: JsonReader): List<SearchEntry> {
        val series = mutableListOf<String>()
        val entries = mutableListOf<SearchEntry>()
        reader.beginObject()
        while (reader.hasNext()) when (reader.nextName()) {
            "series" -> {
                reader.beginArray()
                while (reader.hasNext()) {
                    reader.beginArray()
                    series.add(reader.nextString())
                    while (reader.hasNext()) reader.skipValue()
                    reader.endArray()
                }
                reader.endArray()
            }
            "lessons" -> {
                reader.beginArray()
                while (reader.hasNext()) {
                    reader.beginArray()
                    val index = reader.nextInt()
                    val title = reader.nextString()
                    val description = reader.nextString()
                    val date = reader.nextString()
                    val minutes = if (reader.peek() == JsonToken.NULL) { reader.nextNull(); null } else reader.nextInt()
                    val position = reader.nextInt()
                    val url = reader.nextString()
                    while (reader.hasNext()) reader.skipValue()
                    reader.endArray()
                    entries.add(SearchEntry(series[index], position, title, description, date, minutes, url))
                }
                reader.endArray()
            }
            else -> reader.skipValue()
        }
        reader.endObject()
        return entries
    }

    /** the catalog from the site, now (on opening the app) */
    @Synchronized
    fun refresh() {
        offlineUntil = 0
        catalog = Catalog.parse(fetchOrKept(File(directory, "catalog.json"), "catalog.json"))
    }

    private fun offline() = System.currentTimeMillis() < offlineUntil

    /** the file from the site (then [fetched]), kept; or as kept before, when the site can't be reached */
    private fun fetchOrKept(file: File, path: String, fetched: () -> Unit = {}): String {
        if (!offline()) {
            try {
                return fetch(siteUrl + path).also { text ->
                    file.parentFile?.mkdirs()
                    File(file.path + ".tmp").apply { writeText(text) }.renameTo(file)
                    fetched()
                }
            } catch (error: IOException) {
                offlineUntil = System.currentTimeMillis() + RETRY_AFTER
                if (!file.exists()) throw error
            }
        }
        if (!file.exists()) throw IOException("offline, and $path was never fetched")
        return file.readText()
    }

    private fun fetch(url: String): String {
        val connection = URL(url).openConnection() as HttpURLConnection
        connection.connectTimeout = TIMEOUT
        connection.readTimeout = TIMEOUT
        try {
            if (connection.responseCode != 200) throw IOException("${connection.responseCode} for $url")
            return connection.inputStream.bufferedReader().readText()
        } finally {
            connection.disconnect()
        }
    }
}
