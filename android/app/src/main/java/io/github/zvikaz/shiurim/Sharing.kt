package io.github.zvikaz.shiurim

import android.content.Context
import android.content.Intent

/** a lesson's page on the site, which opens it (and from which it's played): "<site>#<series id>/<number>" */
fun lessonPage(lessonId: String) = "${BuildConfig.SITE_URL}#${Library.lessonKey(lessonId)}"

/** shares a page of the site, by the phone's share sheet (WhatsApp and the like) */
fun share(context: Context, title: String, url: String) {
    val send = Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_SUBJECT, title)
        .putExtra(Intent.EXTRA_TEXT, listOf(title, url).filter { it.isNotBlank() }.joinToString("\n"))
    context.startActivity(Intent.createChooser(send, null).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
}
