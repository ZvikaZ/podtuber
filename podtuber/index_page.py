import html
import json
import re
from datetime import datetime, timezone
from html import escape
from urllib.parse import urlparse

from pyluach.dates import HebrewDate

LESSONS_FILENAME = 'lessons.json'

# the page's texts, by the index page's language (config.toml's [general] language); English for any other
TEXTS = {
    'en': {
        'dir': 'ltr',
        'latest_date': lambda date: date.strftime('%Y-%m-%d'),
        'updated_date': lambda date: date.strftime('%Y-%m-%d %H:%M UTC'),
        'summary': '{count} podcasts &middot; updated {updated}',
        'filter': 'Search a podcast or an episode&hellip;',
        'filter_label': 'Search podcasts and episodes',
        'meta': '{episodes} episodes &middot; latest {latest}',
        'open': 'Open in podcast app',
        'copy': 'Copy RSS link',
        'copied': 'Copied',
        'share': 'Share',
        'link_copied': 'Link copied',
        'script': {
            'lessons': 'Episodes ({count})',
            'to_series': 'To the podcast',
            'minutes': '{count} min',
            'more': 'and {count} more; a more specific search will narrow them down',
            'nothing': 'Nothing found',
        },
    },
    'he': {
        'dir': 'rtl',
        'latest_date': lambda date: HebrewDate.from_pydate(date.date()).hebrew_date_string(),  # 'ל׳ שבט תשפ״ג'
        'updated_date': lambda date: HebrewDate.from_pydate(date.date()).hebrew_date_string(),
        'summary': '{count} פודקאסטים &middot; עודכן {updated}',
        'filter': 'חיפוש סדרה או שיעור&hellip;',
        'filter_label': 'חיפוש סדרות ושיעורים',
        'meta': '{episodes} פרקים &middot; אחרון {latest}',
        'open': 'פתיחה באפליקציית פודקאסטים',
        'copy': 'העתקת קישור RSS',
        'copied': 'הועתק',
        'share': 'שיתוף',
        'link_copied': 'הקישור הועתק',
        'script': {
            'lessons': 'שיעורים ({count})',
            'to_series': 'לסדרה',
            'minutes': "{count} דק'",
            'more': 'ועוד {count} שיעורים; חיפוש מדויק יותר יצמצם אותם',
            'nothing': 'לא נמצא דבר',
        },
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
  h2 {{ font-size: 1.1rem; margin: 2rem 0 .5rem; }}
  .note {{ color: var(--muted); margin: 0 0 1.5rem; font-size: .9rem; }}
  input {{ width: 100%; box-sizing: border-box; padding: .6rem .75rem; margin-bottom: 1rem; font: inherit;
          color: inherit; background: transparent; border: 1px solid var(--line); border-radius: .5rem; }}
  ul {{ list-style: none; margin: 0; padding: 0; }}
  li {{ padding: .9rem 0; border-top: 1px solid var(--line); scroll-margin-top: 1rem; }}
  li:target {{ background: color-mix(in srgb, var(--accent) 12%, transparent); }}
  #lessons li {{ padding: .6rem 0; }}
  .name {{ font-weight: 600; }}
  .source {{ font-weight: normal; color: var(--muted); }}
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
<input type="search" placeholder="{filter}" aria-label="{filter_label}">
<ul id="series">
{items}
</ul>
<section id="lessons" hidden>
  <h2></h2>
  <ul></ul>
  <p class="note"></p>
</section>
</main>
<script>
const TEXTS = {texts};
{script}
</script>
</body>
</html>
"""

# a plain string, not a template: the page's texts reach it as TEXTS
SCRIPT = r"""
function flash(button, text) {
  const original = button.textContent;
  button.textContent = text;
  setTimeout(() => button.textContent = original, 1500);
}
for (const button of document.querySelectorAll('button[data-url]'))
  button.onclick = () => navigator.clipboard.writeText(button.dataset.url).then(() => flash(button, TEXTS.copied));

// a series' own link is this page, scrolled to it; phones offer their share menu
for (const button of document.querySelectorAll('button[data-share]'))
  button.onclick = () => {
    const url = new URL(location.pathname, location.origin);
    url.hash = button.dataset.share;
    if (navigator.share)
      navigator.share({title: button.dataset.title, url: url.href}).catch(() => {});
    else
      navigator.clipboard.writeText(url.href).then(() => flash(button, TEXTS.link_copied));
  };

// every word searched for must appear in the text, even within a word ('פור' finds 'פורים', and so does
// 'הכיפורים'); gershayim, quotes and niqqud don't count, so 'עין איה' finds 'עין אי"ה'
const normalize = text => text.replace(/[\u0591-\u05C7]/g, '').replace(/["'`״׳’‘”“]/g, '').toLowerCase();
const queryWords = query => normalize(query).split(/\s+/).filter(Boolean);
function matcher(query) {
  const words = queryWords(query);
  return text => { const normalized = normalize(text); return words.every(word => normalized.includes(word)); };
}

// where the description, rather than the title, has what was searched for: the words around it
function excerpt(text, query) {
  const normalized = normalize(text);
  const word = queryWords(query).find(word => normalized.includes(word));
  if (!word) return '';
  // find the word in the text as written (with its gershayim and the like), by skipping what normalize removes
  const ignored = /[\u0591-\u05C7"'`״׳’‘”“]/;
  let at = 0;
  for (let found = normalized.indexOf(word), seen = 0; at < text.length && seen < found; at++)
    if (!ignored.test(text[at])) seen++;
  const start = Math.max(0, at - 60), end = Math.min(text.length, at + word.length + 60);
  return (start ? '…' : '') + text.slice(start, end).trim() + (end < text.length ? '…' : '');
}

const input = document.querySelector('input[type=search]');
const seriesItems = [...document.querySelectorAll('#series > li')];
const lessonsSection = document.getElementById('lessons');
const LIMIT = 100;
let lessons = null;  // the search index, loaded once something is searched for

async function loadLessons() {
  if (!lessons) {
    try {
      lessons = await (await fetch('lessons.json')).json();
    } catch {
      lessons = {series: [], lessons: []};
    }
  }
  return lessons;
}

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function showLesson([series, title, description, date, minutes], query) {
  const [feedId, seriesName, source] = lessons.series[series];
  const li = element('li');
  const name = element('div', title, 'name');
  name.dir = 'auto';
  li.append(name);
  if (!matcher(query)(title)) {  // found by its description, which the result then shows a part of
    const why = element('div', excerpt(description, query), 'meta');
    why.dir = 'auto';
    li.append(why);
  }
  const meta = [seriesName + (source ? ` [${source}]` : ''), date];
  if (minutes) meta.push(TEXTS.minutes.replace('{count}', minutes));
  const link = element('a', TEXTS.to_series);
  link.href = '#' + feedId;
  link.onclick = () => { input.value = ''; search(); };  // show the whole list, scrolled to the series
  const links = element('div', null, 'links');
  links.append(link);
  li.append(element('div', meta.join(' · '), 'meta'), links);
  return li;
}

async function search() {
  const query = input.value.trim();
  const url = new URL(location.href);
  if (query) url.searchParams.set('q', query); else url.searchParams.delete('q');
  history.replaceState(null, '', url);

  const matches = matcher(query);
  let seriesFound = 0;
  for (const li of seriesItems) {
    li.hidden = query && !matches(li.dataset.name);
    seriesFound += !li.hidden;
  }
  if (query.length < 2) {
    lessonsSection.hidden = true;
    return;
  }
  const {lessons: all} = await loadLessons();
  if (input.value.trim() !== query) return;  // typed on in the meantime
  const found = all.filter(([, title, text]) => matches(title + ' ' + text));
  lessonsSection.hidden = false;
  lessonsSection.querySelector('h2').textContent = found.length || seriesFound
    ? TEXTS.lessons.replace('{count}', found.length) : TEXTS.nothing;
  lessonsSection.querySelector('ul').replaceChildren(...found.slice(0, LIMIT).map(lesson => showLesson(lesson, query)));
  lessonsSection.querySelector('.note').textContent =
    found.length > LIMIT ? TEXTS.more.replace('{count}', found.length - LIMIT) : '';
}

// the search is kept in the address (?q=...), so it can be shared, and is restored when opened
input.oninput = search;
const query = new URL(location.href).searchParams.get('q');
if (query) {
  input.value = query;
  search();
}
"""

ITEM = """<li id="{feed_id}" data-name="{name} {source}">
  <div class="name" dir="auto">{name}{source_label}</div>
  <div class="meta">{meta}</div>
  <div class="links">
    <a href="{app_url}">{open}</a>
    <button type="button" data-url="{url}">{copy}</button>
    <button type="button" data-share="{feed_id}" data-title="{name}">{share}</button>
  </div>
</li>"""


def write_index(podcasts, path, title, lang='en'):
    """
    A page listing the podcasts (each a (podgen Podcast, name, source)), for subscribing to them from a phone,
    and searching them and their episodes.
    """
    texts = TEXTS.get(lang.split('-')[0], TEXTS['en'])
    items, series, lessons = [], [], []
    for podcast, name, source in sorted(podcasts, key=lambda entry: (entry[1], entry[2])):
        feed_id = podcast.feed_url.rsplit('/', 1)[-1].removesuffix('.rss')
        latest = max((episode.publication_date for episode in podcast.episodes), default=None)
        items.append(ITEM.format(
            name=escape(name),
            source=escape(source),
            source_label=f' <span class="source">[{escape(source)}]</span>' if source else '',
            meta=texts['meta'].format(episodes=len(podcast.episodes),
                                      latest=texts['latest_date'](latest) if latest else '-'),
            url=escape(podcast.feed_url),
            app_url=escape(podcast_app_url(podcast.feed_url)),
            feed_id=escape(feed_id),
            open=texts['open'],
            copy=texts['copy'],
            share=texts['share'],
        ))
        series.append([feed_id, name, source])
        lessons += [search_entry(len(series) - 1, episode, texts) for episode in podcast.episodes]

    (path.parent / LESSONS_FILENAME).write_text(
        json.dumps({'series': series, 'lessons': lessons}, ensure_ascii=False, separators=(',', ':')),
        encoding='utf8')
    updated = texts['updated_date'](datetime.now(timezone.utc))
    script_texts = {**texts['script'], 'copied': texts['copied'], 'link_copied': texts['link_copied']}
    path.write_text(PAGE.format(title=escape(title), lang=escape(lang), dir=texts['dir'],
                                summary=texts['summary'].format(count=len(items), updated=updated),
                                filter=texts['filter'], filter_label=texts['filter_label'],
                                items='\n'.join(items),
                                texts=json.dumps(script_texts, ensure_ascii=False), script=SCRIPT),
                    encoding='utf8')


def search_entry(series, episode, texts):
    """[series index, title, text to search besides the title, date, minutes]"""
    date = texts['latest_date'](episode.publication_date)
    description = ' '.join(html.unescape(re.sub(r'<[^>]+>', ' ', episode.summary or '')).split())
    if description == date:  # many episodes' description is only their date
        description = ''
    duration = episode.media.duration if episode.media else None
    return [series, episode.title or '', description, date, round(duration.total_seconds() / 60) if duration else None]


def podcast_app_url(feed_url):
    """
    Android has no default podcast app, but podcast apps (Pocket Casts, AntennaPod, Podcast Addict...) handle the
    pcast:// scheme, so the phone opens the feed in the installed one, or asks which one if there are several.
    """
    return 'pcast://' + feed_url.removeprefix(f'{urlparse(feed_url).scheme}://')
