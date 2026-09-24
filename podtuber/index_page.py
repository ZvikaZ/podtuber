from datetime import datetime, timezone
from html import escape
from urllib.parse import urlparse

# the page's texts, by the index page's language (config.toml's [general] language); English for any other
TEXTS = {
    'en': {
        'dir': 'ltr',
        'date_format': '%Y-%m-%d',
        'summary': '{count} podcasts &middot; updated {updated}',
        'filter': 'Filter&hellip;',
        'filter_label': 'Filter podcasts',
        'meta': '{episodes} episodes &middot; latest {latest}',
        'open': 'Open in podcast app',
        'copy': 'Copy RSS link',
        'copied': 'Copied',
    },
    'he': {
        'dir': 'rtl',
        'date_format': '%d/%m/%Y',
        'summary': '{count} פודקאסטים &middot; עודכן {updated}',
        'filter': 'סינון&hellip;',
        'filter_label': 'סינון פודקאסטים',
        'meta': '{episodes} פרקים &middot; אחרון {latest}',
        'open': 'פתיחה באפליקציית פודקאסטים',
        'copy': 'העתקת קישור RSS',
        'copied': 'הועתק',
    },
}

PAGE = """<!DOCTYPE html>
<html lang="{lang}" dir="{dir}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{ --bg: #fbfaf7; --fg: #1d1c1a; --muted: #6b6860; --line: #e4e1da; --accent: #2f5d8a; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg: #181816; --fg: #ecebe6; --muted: #a09d94; --line: #33322e; --accent: #8db8e3; }}
  }}
  body {{ margin: 0; background: var(--bg); color: var(--fg);
         font: 16px/1.5 system-ui, -apple-system, "Segoe UI", Arial, sans-serif; }}
  main {{ max-width: 44rem; margin: 0 auto; padding: 1.5rem 1rem 3rem; }}
  h1 {{ font-size: 1.5rem; margin: 0 0 .25rem; }}
  .note {{ color: var(--muted); margin: 0 0 1.5rem; font-size: .9rem; }}
  input {{ width: 100%; box-sizing: border-box; padding: .6rem .75rem; margin-bottom: 1rem; font: inherit;
          color: inherit; background: transparent; border: 1px solid var(--line); border-radius: .5rem; }}
  ul {{ list-style: none; margin: 0; padding: 0; }}
  li {{ padding: .9rem 0; border-top: 1px solid var(--line); }}
  .name {{ font-weight: 600; }}
  .meta {{ color: var(--muted); font-size: .85rem; }}
  .links {{ margin-top: .35rem; display: flex; gap: 1rem; flex-wrap: wrap; font-size: .95rem; }}
  a {{ color: var(--accent); }}
  button {{ font: inherit; font-size: .95rem; color: var(--accent); background: none; border: 0; padding: 0;
           cursor: pointer; text-decoration: underline; }}
</style>
</head>
<body>
<main>
<h1>{title}</h1>
<p class="note">{summary}</p>
<input type="search" placeholder="{filter}" aria-label="{filter_label}" dir="auto"
       oninput="for (const li of document.querySelectorAll('li'))
                  li.hidden = !li.dataset.name.includes(this.value.trim())">
<ul>
{items}
</ul>
</main>
<script>
  for (const button of document.querySelectorAll('button[data-url]'))
    button.onclick = () => navigator.clipboard.writeText(button.dataset.url)
      .then(() => {{ button.textContent = '{copied}'; setTimeout(() => button.textContent = '{copy}', 1500); }});
</script>
</body>
</html>
"""

ITEM = """<li data-name="{name}">
  <div class="name" dir="auto">{name}</div>
  <div class="meta">{meta}</div>
  <div class="links">
    <a href="{app_url}">{open}</a>
    <button type="button" data-url="{url}">{copy}</button>
  </div>
</li>"""


def write_index(podcasts, path, title, lang='en'):
    """A page listing the podcasts, for subscribing to them from a phone."""
    texts = TEXTS.get(lang.split('-')[0], TEXTS['en'])
    items = []
    for podcast in sorted(podcasts, key=lambda podcast: podcast.name):
        latest = max((episode.publication_date for episode in podcast.episodes), default=None)
        items.append(ITEM.format(
            name=escape(podcast.name),
            meta=texts['meta'].format(episodes=len(podcast.episodes),
                                      latest=latest.strftime(texts['date_format']) if latest else '-'),
            url=escape(podcast.feed_url),
            app_url=escape(podcast_app_url(podcast.feed_url)),
            open=texts['open'],
            copy=texts['copy'],
        ))
    updated = datetime.now(timezone.utc).strftime(texts['date_format'] + ' %H:%M UTC')
    path.write_text(PAGE.format(title=escape(title), lang=escape(lang), dir=texts['dir'],
                                summary=texts['summary'].format(count=len(items), updated=updated),
                                filter=texts['filter'], filter_label=texts['filter_label'],
                                copy=texts['copy'], copied=texts['copied'],
                                items='\n'.join(items)),
                    encoding='utf8')


def podcast_app_url(feed_url):
    """
    Android has no default podcast app, but podcast apps (Pocket Casts, AntennaPod, Podcast Addict...) handle the
    pcast:// scheme, so the phone opens the feed in the installed one, or asks which one if there are several.
    """
    return 'pcast://' + feed_url.removeprefix(f'{urlparse(feed_url).scheme}://')
