package io.github.zvikaz.shiurim

import android.content.ContentProvider
import android.content.ContentValues
import android.content.Context
import android.net.Uri
import android.os.ParcelFileDescriptor
import java.io.File
import java.io.FileNotFoundException
import java.net.HttpURLConnection
import java.net.URL

/**
 * The site's images (a series' artwork, a rav's portrait), as content: URIs, which is what Android Auto shows:
 * content://<package>.artwork/<path in the site>, fetched once and kept in the app's cache. Only the site's own
 * paths are served.
 */
class ArtworkProvider : ContentProvider() {
    companion object {
        private val PATH = Regex("[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*")

        fun uri(context: Context, path: String): Uri =
            Uri.parse("content://${context.packageName}.artwork/$path")
    }

    override fun onCreate() = true

    override fun openFile(uri: Uri, mode: String): ParcelFileDescriptor {
        val path = uri.path.orEmpty().removePrefix("/")
        if (!PATH.matches(path) || ".." in path) throw FileNotFoundException(path)
        val file = File(context!!.cacheDir, "artwork/$path")
        if (!file.exists()) {
            val connection = URL(BuildConfig.SITE_URL + path).openConnection() as HttpURLConnection
            connection.connectTimeout = 8000
            connection.readTimeout = 8000
            try {
                if (connection.responseCode != 200) throw FileNotFoundException("${connection.responseCode} for $path")
                file.parentFile?.mkdirs()
                val partial = File(file.path + ".part")
                connection.inputStream.use { input -> partial.outputStream().use { input.copyTo(it) } }
                partial.renameTo(file)
            } catch (error: java.io.IOException) {
                throw FileNotFoundException("$path: $error")
            } finally {
                connection.disconnect()
            }
        }
        return ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY)
    }

    override fun getType(uri: Uri) = if (uri.path.orEmpty().endsWith(".png")) "image/png" else "image/jpeg"

    override fun query(uri: Uri, projection: Array<out String>?, selection: String?, selectionArgs: Array<out String>?,
                       sortOrder: String?) = null
    override fun insert(uri: Uri, values: ContentValues?) = null
    override fun delete(uri: Uri, selection: String?, selectionArgs: Array<out String>?) = 0
    override fun update(uri: Uri, values: ContentValues?, selection: String?, selectionArgs: Array<out String>?) = 0
}
