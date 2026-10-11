import collections
import html
import json
import re
from datetime import datetime, timezone
from html import escape
from urllib.parse import urlparse, quote

from pyluach.dates import HebrewDate

LESSONS_FILENAME = 'lessons.json'
EPISODES_DIR = 'lessons'  # a file per podcast, of its episodes, for listing them on the page
PLAY_STORE = 'https://play.google.com/store/apps/details?id='
# an open book, with sound waves over it, in the page's colors
FAVICON = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#2f5d8a"/><path d="M10 27c8-4 16-3 22 2 6-5 14-6 22-2v25c-8-4-16-3-22 2-6-5-14-6-22-2z" fill="#fbfaf7"/><path d="M32 29v25" stroke="#2f5d8a" stroke-width="2.5"/><path d="M23 17q9-8 18 0M18 12q14-12 28 0" fill="none" stroke="#fbfaf7" stroke-width="3.5" stroke-linecap="round"/></svg>'

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
        'all': 'All',
        'episodes': 'Episode list ({count})',
        'no_app': 'No podcast app? You can install one, such as <a href="{pocketcasts}">Pocket Casts</a> or '
                  '<a href="{antennapod}">AntennaPod</a>, or listen to the episodes right from this page.',
        'script': {
            'hide': 'Close',
            'download': 'Listen / download',
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
        'all': 'הכל',
        'episodes': 'רשימת שיעורים ({count})',
        'no_app': 'אין לכם אפליקציית פודקאסטים? אפשר להתקין, למשל, <a href="{pocketcasts}">Pocket Casts</a> '
                  'או <a href="{antennapod}">AntennaPod</a>, או להאזין לשיעורים ישירות מהדף.',
        'script': {
            'hide': 'סגירה',
            'download': 'האזנה / הורדה',
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
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,{favicon}">
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
  li:target, li.chosen {{ background: color-mix(in srgb, var(--accent) 12%, transparent); }}
  #lessons li, .episodes li {{ padding: .6rem 0; }}
  .episodes {{ margin-top: .5rem; padding-inline-start: 1rem; border-inline-start: 2px solid var(--line); }}
  #ravs {{ display: flex; gap: .5rem; flex-wrap: wrap; margin-bottom: 1rem; }}
  #ravs button {{ text-decoration: none; padding: .3rem .8rem; border: 1px solid var(--line); border-radius: 1rem; }}
  #ravs button[aria-pressed=true] {{ background: var(--accent); border-color: var(--accent); color: var(--bg); }}
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
<p class="note">{no_app}</p>
{ravs}<input type="search" placeholder="{filter}" aria-label="{filter_label}">
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

// a podcast's own link is this page, scrolled to it (#<feed id>), and an episode's, scrolled to it in its
// podcast's list (#<feed id>/<its position there>); phones offer their share menu
function shareLink(button, hash, title) {
  const url = new URL(location.pathname, location.origin);
  url.hash = hash;
  if (navigator.share)
    navigator.share({title, url: url.href}).catch(() => {});
  else
    navigator.clipboard.writeText(url.href).then(() => flash(button, TEXTS.link_copied));
}
for (const button of document.querySelectorAll('button[data-share]'))
  button.onclick = () => shareLink(button, button.dataset.share, button.dataset.title);

function shareButton(hash, title) {
  const button = element('button', TEXTS.share);
  button.type = 'button';
  button.onclick = () => shareLink(button, hash, title);
  return button;
}

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

function showLesson([series, title, description, date, minutes, position], query) {
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
  link.href = `#${feedId}/${position}`;
  link.onclick = event => {  // the whole list, scrolled to the episode in its podcast, as a new page in the history
    event.preventDefault();
    history.pushState(null, '', location.pathname + link.hash);
    showAddress();
  };
  const links = element('div', null, 'links');
  links.append(link, shareButton(`${feedId}/${position}`, title));
  li.append(element('div', meta.join(' · '), 'meta'), links);
  return li;
}

// the rav whose podcasts are shown ('' for all)
let rav = '';
const ravButtons = [...document.querySelectorAll('#ravs button')];
function showRav() {
  for (const button of ravButtons) button.setAttribute('aria-pressed', button.dataset.rav === rav);
}
for (const button of ravButtons)
  button.onclick = () => { rav = button.dataset.rav; showRav(); typed(); };

// a podcast's episodes, from its own file (lessons/<feed id>.json), loaded when first opened
async function toggleEpisodes(li, open) {
  const button = li.querySelector('button[data-episodes]');
  const list = li.querySelector('.episodes');
  button.dataset.label = button.dataset.label || button.textContent;
  open = open ?? list.hidden;
  if (open && !list.children.length) {
    const episodes = await (await fetch(`lessons/${encodeURIComponent(li.id)}.json`)).json();
    list.append(...episodes.map(([title, date, minutes, url], index) => {
      const item = element('li');
      const name = element('div', title, 'name');
      name.dir = 'auto';
      const meta = [date];
      if (minutes) meta.push(TEXTS.minutes.replace('{count}', minutes));
      const download = element('a', TEXTS.download);
      download.href = url;
      download.target = '_blank';
      download.rel = 'noopener';
      const links = element('div', null, 'links');
      links.append(download, shareButton(`${li.id}/${index + 1}`, title));
      item.append(name, element('div', meta.join(' · '), 'meta'), links);
      return item;
    }));
  }
  list.hidden = !open;
  button.textContent = open ? TEXTS.hide : button.dataset.label;
}
for (const button of document.querySelectorAll('button[data-episodes]'))
  button.onclick = () => toggleEpisodes(button.closest('li'));

// typing (or choosing a rav) changes the address in place (?q=...&rav=...), so a search can be shared, and is
// there when going back to it
function typed() {
  const query = input.value.trim();
  const url = new URL(location.href);
  url.hash = '';
  if (query) url.searchParams.set('q', query); else url.searchParams.delete('q');
  if (rav) url.searchParams.set('rav', rav); else url.searchParams.delete('rav');
  history.replaceState(null, '', url);
  search();
}

// what the address says: a search (?q=...) of a rav's podcasts (&rav=...), or a podcast to scroll to (#...)
async function showAddress() {
  const url = new URL(location.href);
  input.value = url.searchParams.get('q') || '';
  rav = url.searchParams.get('rav') || '';
  showRav();
  search();
  for (const li of document.querySelectorAll('li.chosen')) li.classList.remove('chosen');
  const [feedId, position] = decodeURIComponent(url.hash.slice(1)).split('/');
  const chosen = feedId && document.getElementById(feedId);
  if (chosen) {  // a podcast reached from a search, or by its shared link: with its episodes open
    chosen.classList.add('chosen');
    await toggleEpisodes(chosen, true);
    const episode = position && chosen.querySelector(`.episodes > li:nth-child(${Number(position)})`);
    if (episode) episode.classList.add('chosen');
    (episode || chosen).scrollIntoView();
  }
}

async function search() {
  const query = input.value.trim();
  const matches = matcher(query);
  let seriesFound = 0;
  for (const li of seriesItems) {
    li.hidden = (rav && li.dataset.rav !== rav) || (query && !matches(li.dataset.name));
    seriesFound += !li.hidden;
  }
  if (query.length < 2) {
    lessonsSection.hidden = true;
    return;
  }
  const {lessons: all} = await loadLessons();
  if (input.value.trim() !== query) return;  // typed on in the meantime
  const found = all.filter(([series, title, text]) =>
    (!rav || lessons.series[series][3] === rav) && matches(title + ' ' + text));
  lessonsSection.hidden = false;
  lessonsSection.querySelector('h2').textContent = found.length || seriesFound
    ? TEXTS.lessons.replace('{count}', found.length) : TEXTS.nothing;
  lessonsSection.querySelector('ul').replaceChildren(...found.slice(0, LIMIT).map(lesson => showLesson(lesson, query)));
  lessonsSection.querySelector('.note').textContent =
    found.length > LIMIT ? TEXTS.more.replace('{count}', found.length - LIMIT) : '';
}

input.oninput = typed;
window.onpopstate = showAddress;  // back and forward
showRav();
if (location.search || location.hash) showAddress();
"""

ITEM = """<li id="{feed_id}" data-name="{name} {source}" data-rav="{rav}">
  <div class="name" dir="auto">{name}{source_label}</div>
  <div class="meta">{meta}</div>
  <div class="links">
    <a href="{app_url}">{open}</a>
    <button type="button" data-url="{url}">{copy}</button>
    <button type="button" data-share="{feed_id}" data-title="{name}">{share}</button>
    <button type="button" data-episodes="{feed_id}">{episodes}</button>
  </div>
  <ul class="episodes" hidden></ul>
</li>"""


def write_index(podcasts, path, title, lang='en'):
    """
    A page listing the podcasts, for subscribing to them from a phone, and searching them and their episodes. Each
    podcast is a dict of its podgen 'podcast', and its 'name', 'feed_id', 'source' and 'rav'.
    """
    texts = TEXTS.get(lang.split('-')[0], TEXTS['en'])
    items, series, lessons = [], [], []
    for entry in sorted(podcasts, key=lambda entry: (entry['name'], entry['source'])):
        podcast, name, source, feed_id, rav = (entry[key] for key in ('podcast', 'name', 'source', 'feed_id', 'rav'))
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
            rav=escape(rav),
            episodes=texts['episodes'].format(count=len(podcast.episodes)),
            open=texts['open'],
            copy=texts['copy'],
            share=texts['share'],
        ))
        series.append([feed_id, name, source, rav])
        episodes = sorted(podcast.episodes, key=lambda episode: episode.publication_date)
        lessons += [search_entry(len(series) - 1, episode, position, texts)
                    for position, episode in enumerate(episodes, 1)]
        write_episodes(path.parent / EPISODES_DIR / f'{feed_id}.json', episodes, texts)

    (path.parent / LESSONS_FILENAME).write_text(
        json.dumps({'series': series, 'lessons': lessons}, ensure_ascii=False, separators=(',', ':')),
        encoding='utf8')
    updated = texts['updated_date'](datetime.now(timezone.utc))
    script_texts = {**texts['script'], 'copied': texts['copied'], 'link_copied': texts['link_copied'], 'share': texts['share']}
    path.write_text(PAGE.format(title=escape(title), lang=escape(lang), dir=texts['dir'],
                                summary=texts['summary'].format(count=len(items), updated=updated),
                                ravs=rav_buttons(podcasts, texts),
                                favicon=quote(FAVICON),
                                no_app=texts['no_app'].format(pocketcasts=PLAY_STORE + 'au.com.shiftyjelly.pocketcasts',
                                                              antennapod=PLAY_STORE + 'de.danoeh.antennapod'),
                                filter=texts['filter'], filter_label=texts['filter_label'],
                                items='\n'.join(items),
                                texts=json.dumps(script_texts, ensure_ascii=False), script=SCRIPT),
                    encoding='utf8')


def write_episodes(path, episodes, texts):
    """a podcast's episodes: [title, date, minutes, audio url] each"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([[episode.title or '', texts['latest_date'](episode.publication_date),
                                 minutes(episode), episode.media.url if episode.media else '']
                                for episode in episodes], ensure_ascii=False, separators=(',', ':')),
                    encoding='utf8')


def minutes(episode):
    duration = episode.media.duration if episode.media else None
    return round(duration.total_seconds() / 60) if duration else None


def rav_buttons(podcasts, texts):
    """a button per rav, with his number of podcasts, when there's more than one"""
    counts = collections.Counter(entry['rav'] for entry in podcasts)
    if len(counts) < 2:
        return ''
    buttons = [('', texts['all'], len(podcasts))] + [(rav, rav, count) for rav, count in counts.most_common()]
    return '<nav id="ravs">' + ''.join(f'<button type="button" data-rav="{escape(rav)}">{escape(label)} ({count})</button>'
                                       for rav, label, count in buttons) + '</nav>\n'


def search_entry(series, episode, position, texts):
    """[series index, title, text to search besides the title, date, minutes, position in its series]"""
    date = texts['latest_date'](episode.publication_date)
    description = ' '.join(html.unescape(re.sub(r'<[^>]+>', ' ', html.unescape(episode.summary or ''))).split())
    if description == date:  # many episodes' description is only their date
        description = ''
    return [series, episode.title or '', description, date, minutes(episode), position]


def podcast_app_url(feed_url):
    """
    Android has no default podcast app, but podcast apps (Pocket Casts, AntennaPod, Podcast Addict...) handle the
    pcast:// scheme, so the phone opens the feed in the installed one, or asks which one if there are several.
    """
    return 'pcast://' + feed_url.removeprefix(f'{urlparse(feed_url).scheme}://')
