"""
The index page: what the site is and how to listen, the rabbis, each one's series grouped, a series' lessons, and a
search of all series and lessons. A static page; the lessons of a series, and the search index, load when needed.
"""
import collections
import hashlib
import html
import json
import re
from datetime import datetime, timedelta, timezone
from html import escape
from urllib.parse import urlparse

from pyluach.dates import HebrewDate

from podtuber import presentation

LESSONS_PREFIX = 'lessons'  # the search index, lessons.<version>.json, versioned so browsers may keep it
EPISODES_DIR = 'lessons'  # a file per podcast, of its episodes, for listing them on the page
PLAY_STORE = 'https://play.google.com/store/apps/details?id='
POCKET_CASTS = PLAY_STORE + 'au.com.shiftyjelly.pocketcasts'
ISSUES_URL = 'https://github.com/ZvikaZ/podtuber/issues'
DESCRIPTION_LIMIT = 200  # characters of a lesson's description kept in the search index
NEW_LESSONS = 12  # how many of the newest lessons the home screen shows
ONGOING = timedelta(days=90)  # a series with a lesson this recent is still being added to
# an open book, with sound waves over it, in the page's colors
FAVICON = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#2f5d8a"/><path d="M10 27c8-4 16-3 22 2 6-5 14-6 22-2v25c-8-4-16-3-22 2-6-5-14-6-22-2z" fill="#fbfaf7"/><path d="M32 29v25" stroke="#2f5d8a" stroke-width="2.5"/><path d="M23 17q9-8 18 0M18 12q14-12 28 0" fill="none" stroke="#fbfaf7" stroke-width="3.5" stroke-linecap="round"/></svg>'
# holidays in the order of the year (from Elul), for listing a rav's holiday podcasts
HOLIDAYS = ['אלול', 'ראש השנה', 'יום כיפור', 'סוכות', 'חנוכה', 'עשרה בטבת', 'ט"ו בשבט', 'שובבים', 'פורים', 'פסח',
            'ספירת העומר', 'יום השואה', 'יום הזיכרון', 'יום העצמאות', 'ל"ג בעומר', 'יום ירושלים', 'שבועות', 'תשעה באב']
GENERAL = re.compile(r'^(כללי|שיעורים נוספים|ימי עיון|חגים|שו"ת)(?![א-ת])')

TEXTS = {
    'he': {
        'dir': 'rtl',
        'date': lambda date: HebrewDate.from_pydate(date).hebrew_date_string(),  # 'ל׳ שבט תשפ״ג'
        'tagline': 'שיעורי תורה מכמה אתרים, כפודקאסטים שמתעדכנים מעצמם: להאזנה בטלפון וברכב.',
        'summary': '{count} סדרות של {ravs} רבנים · עודכן {updated}',
        'stale': 'שיעורי {sites} מעודכנים עד {date}.',
        'howto': 'איך מאזינים?',
        'howto_body': (
            '<ol><li>אפשר להאזין לכל שיעור כאן, בלחיצה על <b>האזנה</b>.</li>'
            '<li>כדי לקבל שיעורים חדשים מעצמם, ולשמוע ברכב: מתקינים אפליקציית פודקאסטים (מומלץ: '
            '<a href="{pocketcasts}">Pocket Casts</a>), ובסדרה לוחצים <b>הוספה ל-Pocket Casts</b>.</li>'
            '<li>באפליקציה אחרת: בסדרה, תחת <b>עוד</b>, מעתיקים את כתובת הפודקאסט, ומוסיפים אותה באפליקציה '
            '("הוספה לפי כתובת").</li></ol>'
            '<h3>ברכב (Android Auto)</h3>'
            '<ul><li>הסדרות שנוספו לאפליקציה מופיעות ברכב; סדרות של שיעורים ברצף מתחילות מהשיעור הראשון.</li>'
            '<li>כדאי להפעיל באפליקציה הורדה אוטומטית של שיעורים חדשים, כדי שהשיעור לא ייעצר בלי קליטה.</li>'
            '<li>את השיעורים הבאים בסדרה מוסיפים לתור (Up Next) לפני הנסיעה, והם יתנגנו זה אחר זה.</li>'
            '<li>חיפוש קולי בעברית לא תמיד מוצא את הסדרה; עדיף לבחור אותה במסך.</li></ul>'),
        'ravs_title': 'הרבנים',
        'series_count': '{count} סדרות',
        'new_title': 'שיעורים חדשים',
        'all': 'כל הרבנים',
        'filter': 'חיפוש סדרה או שיעור…',
        'filter_label': 'חיפוש סדרות ושיעורים',
        'whole_words': 'מילים שלמות בלבד',
        'skip': 'דילוג לרשימה',
        'sort': 'מיון:',
        'sort_name': 'לפי שם',
        'sort_updated': 'לפי עדכון',
        'sort_size': 'לפי גודל',
        'groups': {'course': 'סדרות', 'holiday': 'חגים ומועדים', 'general': 'שיעורים כלליים'},
        'lessons_count': '{count} שיעורים',
        'hours': '{count} שעות',
        'minutes_total': '{count} דקות',
        'ongoing': 'מתעדכנת',
        'missing': 'חסרים {count} שיעורים',
        'missing_title': 'ל-{count} שיעורים בסדרה אין הקלטה באתר המקור',
        'source': {'בני דוד': 'מקור: בני דוד', 'ערוץ מאיר': 'מקור: ערוץ מאיר', 'ישיבת הכותל': 'מקור: ישיבת הכותל',
                   'שבי חברון': 'מקור: שבי חברון', 'אתר הרב': 'מקור: האתר של הרב', 'פודקאסט': 'הפודקאסט הרשמי'},
        'open': 'הוספה ל-Pocket Casts',
        'lessons_button': 'השיעורים ({count})',
        'more': 'עוד',
        'copy': 'העתקת כתובת הפודקאסט (לאפליקציות אחרות)',
        'apple': 'פתיחה באפליקציית Podcasts (אייפון)',
        'share': 'שיתוף הסדרה',
        'footer': ('אתר לא רשמי, שמרכז שיעורים שפורסמו באתרים האלה: {sources}. כל הזכויות לשיעורים שמורות להם.'
                   ' הצעות, בקשות לרבנים נוספים ודיווח על בעיות: <a href="{issues}">כאן</a>.'),
        'script': {
            'close': 'סגירה',
            'back': 'חזרה',
            'listen': 'האזנה',
            'share': 'שיתוף',
            'to_series': 'לסדרה',
            'minutes': "{count} דק'",
            'lesson_of': 'שיעור {number}',
            'found_series': 'סדרות ({count})',
            'found_lessons': 'שיעורים ({count})',
            'more': 'ועוד {count} שיעורים; חיפוש מדויק יותר יצמצם אותם',
            'nothing': 'לא נמצאו סדרות או שיעורים. נסו מילה אחרת.',
            'nothing_whole': 'לא נמצאו סדרות או שיעורים. נסו מילה אחרת, או בטלו "מילים שלמות בלבד".',
            'loading': 'טוען את מאגר השיעורים…',
            'copied': 'הכתובת הועתקה',
            'link_copied': 'הקישור הועתק',
            'no_app': 'לא נפתחה אפליקציה? אפשר להעתיק את כתובת הפודקאסט, תחת "עוד".',
            'from_first': 'מהראשון',
            'from_last': 'מהאחרון',
            'share_text': '"{name}" – {rav}, {count} שיעורים. להאזנה ולהוספה לאפליקציה:',
        },
    },
}
TEXTS['en'] = TEXTS['he']  # the page is Hebrew only (the sites are)

PAGE = """<!DOCTYPE html>
<html lang="%LANG%" dir="%DIR%">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>%TITLE%</title>
<meta name="description" content="%TAGLINE%">
<meta property="og:type" content="website">
<meta property="og:title" content="%TITLE%">
<meta property="og:description" content="%TAGLINE%">
<meta property="og:image" content="%BASE%og.png">
<meta property="og:url" content="%BASE%">
<meta name="theme-color" content="#2f5d8a">
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%FAVICON%">
<link rel="apple-touch-icon" href="icon-180.png">
<link rel="manifest" href="manifest.webmanifest">
<style>
  :root { --bg: #fbfaf7; --fg: #1d1c1a; --muted: #595650; --line: #e4e1da; --accent: #2f5d8a; --on-accent: #ffffff;
          --soft: #edf2f7; --warn: #8a5a14; --warn-soft: #fbefd9; --good: #2e6b3c; --good-soft: #e3f1e6; }
  @media (prefers-color-scheme: dark) {
    :root { --bg: #181816; --fg: #ecebe6; --muted: #aeaba2; --line: #33322e; --accent: #8db8e3; --on-accent: #10161d;
            --soft: #1f2a35; --warn: #e9b161; --warn-soft: #362a17; --good: #8fd19e; --good-soft: #1b2e21; }
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--fg);
         font: 16px/1.5 system-ui, -apple-system, "Segoe UI", Arial, sans-serif; }
  main, header, footer { max-width: 46rem; margin: 0 auto; padding-inline: 16px; }
  h1 { font-size: 1.6rem; margin: 1.5rem 0 .25rem; }
  h2 { font-size: 1.15rem; margin: 1.75rem 0 .5rem; }
  h3 { font-size: 1rem; margin: 1rem 0 .25rem; }
  .tagline { margin: 0 0 .25rem; font-size: 1.05rem; }
  .note { color: var(--muted); margin: 0 0 .5rem; font-size: .9rem; }
  .skip { position: absolute; inset-inline-start: -999px; }
  .skip:focus { inset-inline-start: 1rem; top: 1rem; background: var(--bg); padding: .5rem; z-index: 3; }
  details.howto { border: 1px solid var(--line); border-radius: .5rem; padding: .25rem .9rem; margin: .75rem 0; }
  details.howto summary { cursor: pointer; font-weight: 600; min-height: 44px; display: flex; align-items: center; }
  details.howto ol, details.howto ul { padding-inline-start: 1.2rem; margin: .25rem 0 .75rem; }
  .bar { position: sticky; top: env(safe-area-inset-top, 0px); z-index: 2; background: var(--bg);
         max-width: 46rem; margin: 0 auto; padding: .6rem 16px; border-bottom: 1px solid var(--line); }
  input[type=search] { width: 100%; padding: .7rem .8rem; font: inherit; color: inherit; background: var(--bg);
         border: 1px solid var(--muted); border-radius: .5rem; min-height: 44px; }
  .option { display: inline-flex; align-items: center; gap: .4rem; margin-top: .35rem; color: var(--muted);
            font-size: .9rem; cursor: pointer; min-height: 32px; }
  .option input { width: 1.1rem; height: 1.1rem; }
  #ravs { display: flex; gap: .5rem; overflow-x: auto; padding-block: .5rem 0; scrollbar-width: thin; }
  #ravs button { flex: none; padding: .45rem .9rem; border: 1px solid var(--line); border-radius: 99px;
                 min-height: 40px; text-decoration: none; color: var(--fg); }
  #ravs button[aria-pressed=true] { background: var(--accent); border-color: var(--accent); color: var(--on-accent); }
  .ravs { display: grid; grid-template-columns: repeat(auto-fill, minmax(9.5rem, 1fr)); gap: .75rem; padding: 0;
          list-style: none; }
  .ravs button { width: 100%; display: flex; flex-direction: column; align-items: center; gap: .4rem; padding: .9rem .5rem;
                 border: 1px solid var(--line); border-radius: .75rem; text-decoration: none; color: var(--fg);
                 min-height: 44px; }
  .ravs img, .avatar { width: 72px; height: 72px; border-radius: 50%; object-fit: cover; }
  .avatar { display: grid; place-items: center; color: #fff; font-size: 1.6rem; font-weight: 600; }
  .ravs .who { font-weight: 600; text-align: center; }
  .ravs .count { color: var(--muted); font-size: .85rem; }
  ul.plain { list-style: none; margin: 0; padding: 0; }
  .series > li { display: grid; grid-template-columns: 72px 1fr; gap: .25rem .9rem; padding: .9rem 0;
                 border-top: 1px solid var(--line); scroll-margin-top: 9rem; }
  .series > li > * { min-width: 0; }
  .series .art { width: 72px; height: 72px; border-radius: .4rem; grid-row: span 2; }
  li.chosen { background: color-mix(in srgb, var(--accent) 8%, transparent); }
  .name { font-weight: 600; }
  .meta, .source { color: var(--muted); font-size: .875rem; }
  .badge { display: inline-block; font-size: .78rem; padding: .05rem .5rem; border-radius: 99px; margin-inline-start: .3rem; }
  .badge.missing { color: var(--warn); background: var(--warn-soft); }
  .badge.ongoing { color: var(--good); background: var(--good-soft); }
  .actions { grid-column: 1 / -1; display: flex; gap: .5rem; flex-wrap: wrap; align-items: center; margin-top: .4rem; }
  .btn, .actions summary { display: inline-flex; align-items: center; justify-content: center; min-height: 44px;
         padding: .45rem 1rem; border-radius: .5rem; border: 1px solid var(--line); font: inherit; font-size: .95rem;
         color: var(--accent); background: transparent; text-decoration: none; cursor: pointer; }
  .btn.primary { background: var(--accent); border-color: var(--accent); color: var(--on-accent); font-weight: 600; }
  details.more { position: relative; }
  details.more summary { list-style: none; }
  details.more summary::-webkit-details-marker { display: none; }
  details.more .menu { position: absolute; inset-inline-end: 0; top: calc(100% + .25rem); z-index: 1; display: grid;
         gap: .25rem; min-width: 15rem; padding: .4rem; background: var(--bg); border: 1px solid var(--line);
         border-radius: .5rem; box-shadow: 0 6px 18px rgb(0 0 0 / .12); }
  .menu .btn { justify-content: flex-start; border: 0; width: 100%; }
  .episodes { grid-column: 1 / -1; margin-top: .5rem; }
  .episodes-bar { display: flex; gap: .5rem; align-items: center; flex-wrap: wrap; justify-content: space-between; }
  .episodes ol { list-style: none; margin: .25rem 0 0; padding: 0; }
  .episodes ol > li, #lessons li { padding: .6rem 0; border-top: 1px solid var(--line); }
  .num { color: var(--muted); font-variant-numeric: tabular-nums; margin-inline-end: .35rem; }
  .description { display: block; text-align: start; color: var(--muted); font: inherit; font-size: .9rem; background: none;
                 border: 0; padding: 0; cursor: pointer; display: -webkit-box; -webkit-box-orient: vertical;
                 -webkit-line-clamp: 3; overflow: hidden; }
  .description[aria-expanded=true] { -webkit-line-clamp: unset; }
  .links { display: flex; gap: .5rem; flex-wrap: wrap; margin-top: .3rem; }
  .links .btn { min-height: 40px; padding: .3rem .8rem; }
  mark { background: color-mix(in srgb, var(--accent) 25%, transparent); color: inherit; border-radius: .15rem; }
  .group-head { display: flex; justify-content: space-between; align-items: baseline; gap: 1rem; flex-wrap: wrap; }
  .sort { color: var(--muted); font-size: .9rem; }
  .sort select { font: inherit; color: inherit; background: var(--bg); border: 1px solid var(--line);
                 border-radius: .4rem; min-height: 40px; padding-inline: .5rem; }
  .backbar { padding: .4rem 0; }
  #toast { position: fixed; inset-inline: 16px; bottom: calc(env(safe-area-inset-bottom, 0px) + 1rem); margin: 0 auto;
           max-width: 24rem; background: var(--fg); color: var(--bg); padding: .7rem 1rem; border-radius: .5rem;
           text-align: center; z-index: 4; }
  #top { position: fixed; inset-inline-end: 16px; bottom: calc(env(safe-area-inset-bottom, 0px) + 1rem); z-index: 2;
         width: 48px; height: 48px; border-radius: 50%; border: 1px solid var(--line); background: var(--bg);
         color: var(--accent); font-size: 1.3rem; cursor: pointer; }
  footer { color: var(--muted); font-size: .875rem; padding-block: 2rem 4rem; border-top: 1px solid var(--line);
           margin-top: 2rem; }
  a { color: var(--accent); }
  :focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
</style>
</head>
<body>
<a class="skip" href="#content">%SKIP%</a>
<header>
<h1>%TITLE%</h1>
<p class="tagline">%TAGLINE%</p>
<p class="note">%SUMMARY%</p>
%STALE%
<details class="howto" id="howto"><summary>%HOWTO%</summary>%HOWTO_BODY%</details>
</header>
<div class="bar">
<input type="search" id="search" placeholder="%FILTER%" aria-label="%FILTER_LABEL%" autocomplete="off">
<label class="option"><input type="checkbox" id="whole-words"> %WHOLE_WORDS%</label>
<nav id="ravs" aria-label="%RAVS_TITLE%">%RAV_PILLS%</nav>
</div>
<main id="content">
<p id="status" class="note" aria-live="polite"></p>
<section id="home">
<h2>%RAVS_TITLE%</h2>
<ul class="ravs">%RAV_CARDS%</ul>
<h2>%NEW_TITLE%</h2>
<ul class="plain" id="new">%NEW%</ul>
</section>
<section id="browse" hidden>
<div class="group-head"><h2 id="browse-title"></h2>
<label class="sort">%SORT% <select id="sort"><option value="name">%SORT_NAME%</option><option value="updated">%SORT_UPDATED%</option><option value="size">%SORT_SIZE%</option></select></label></div>
<div id="groups"></div>
</section>
<section id="results" hidden>
<h2 id="series-found"></h2>
<ul class="plain series" id="series-results"></ul>
<h2 id="lessons-found"></h2>
<ul class="plain" id="lessons"></ul>
<p class="note" id="lessons-more"></p>
</section>
<ul class="plain series" id="series" hidden>
%ITEMS%
</ul>
</main>
<footer>%FOOTER%</footer>
<button type="button" id="top" aria-label="למעלה" hidden>↑</button>
<div id="toast" role="status" hidden></div>
<script>
const TEXTS = %TEXTS%;
const LESSONS_URL = %LESSONS_URL%;
%SCRIPT%
</script>
</body>
</html>
"""

ITEM = """<li id="{feed_id}" data-rav="{rav}" data-name="{name}" data-search="{name} {rav} {source}" data-group="{group}"
    data-order="{order}" data-updated="{updated}" data-size="{size}">
  <img class="art" src="{art}" alt="" loading="lazy" width="72" height="72">
  <div class="name" dir="auto">{name}</div>
  <div class="meta">{meta}{badges}<br><span class="source">{source_label}</span></div>
  <div class="actions">
    {open}
    <button type="button" class="btn" data-episodes aria-expanded="false" aria-controls="ep-{feed_id}">{lessons_button}</button>
    <details class="more"><summary>{more}</summary><div class="menu">
      <button type="button" class="btn" data-copy="{url}">{copy}</button>
      {apple}
      <button type="button" class="btn" data-share data-title="{share_title}" data-text="{share_text}">{share}</button>
    </div></details>
  </div>
  <div class="episodes" id="ep-{feed_id}" hidden></div>
</li>"""

# a plain string, not a template: the page's texts reach it as TEXTS
SCRIPT = r"""
const $ = id => document.getElementById(id);
function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text) node.textContent = text;
  if (className) node.className = className;
  return node;
}
let toastTimer;
function toast(text) {
  const box = $('toast');
  box.textContent = text;
  box.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => box.hidden = true, 2500);
}
function copy(text, done) {
  navigator.clipboard.writeText(text).then(() => toast(done), () => window.prompt('', text));
}
const store = {  // per-viewer conveniences only; the page works without them
  get(key) { try { return localStorage.getItem(key); } catch { return null; } },
  set(key, value) { try { localStorage.setItem(key, value); } catch {} },
};

// how to listen: open on the first visit, as the visitor left it afterwards
const howto = $('howto');
howto.open = store.get('howto') !== 'closed';
howto.ontoggle = () => store.set('howto', howto.open ? 'open' : 'closed');

// searching: gershayim, quotes and niqqud don't count ('עין איה' finds 'עין אי"ה'), nor do common spellings:
// 'אלוקים', 'אלקים' and 'אלהים' are one word, as are 'ודאות' and 'וודאות'. Every word must appear, even within a
// word ('פור' finds 'פורים'); or, with "whole words", as a word of its own, perhaps after prefixes ('פורים' finds
// 'לפורים', but not 'הכיפורים')
const strip = text => text.replace(/[֑-ׇ]/g, '').replace(/["'`״׳’‘”“]/g, '').toLowerCase();
const normalize = text => strip(text).replace(/אלוק/g, 'אלק').replace(/אלה(?=(ים|ות|י|ית|יך|ינו)(?![א-ת]))/g, 'אלק')
  .replace(/וו/g, 'ו').replace(/יי/g, 'י');
const queryWords = query => normalize(query).split(/\s+/).filter(Boolean);
const wholeWords = $('whole-words');
const escapeRegex = word => word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
function found(normalized, word) {
  if (!wholeWords.checked) return normalized.includes(word);
  return new RegExp(`(^|[^\\p{L}\\p{N}])[ובהלמשכ]{0,3}${escapeRegex(word)}(?![\\p{L}\\p{N}])`, 'u').test(normalized);
}
function matcher(query) {
  const words = queryWords(query);
  return text => { const normalized = normalize(text); return words.every(word => found(normalized, word)); };
}
// the text, with the words searched for marked (as typed, gershayim and niqqud aside)
function highlighted(text, query) {
  const node = document.createElement('span');
  const words = strip(query).split(/\s+/).filter(word => word.length > 1);
  if (!words.length) { node.textContent = text; return node; }
  const any = `[\\u0591-\\u05C7"'״׳]*`;
  const pattern = new RegExp(words.map(word => [...word].map(escapeRegex).join(any)).join('|'), 'gu');
  let at = 0;
  for (const match of text.matchAll(pattern)) {
    node.append(text.slice(at, match.index), element('mark', match[0]));
    at = match.index + match[0].length;
  }
  node.append(text.slice(at));
  return node;
}
function excerpt(text, query) {
  const word = strip(query).split(/\s+/).find(Boolean) || '';
  const at = Math.max(0, strip(text).indexOf(word));
  const start = Math.max(0, at - 60), end = Math.min(text.length, at + 100);
  return (start ? '…' : '') + text.slice(start, end).trim() + (end < text.length ? '…' : '');
}

// the series, rendered once, and moved between the views
const items = [...document.querySelectorAll('#series > li')];
const byId = Object.fromEntries(items.map(li => [li.id, li]));

// opening a podcast app: if the page is still in view a moment later, none opened
for (const link of document.querySelectorAll('a[data-app]'))
  link.addEventListener('click', () => {
    let left = false;
    const away = () => left = true;
    document.addEventListener('visibilitychange', away, {once: true});
    setTimeout(() => { if (!left && document.visibilityState === 'visible') toast(TEXTS.no_app); }, 1800);
  });
for (const button of document.querySelectorAll('button[data-copy]'))
  button.onclick = () => copy(button.dataset.copy, TEXTS.copied);
function shareLink(hash, title, text) {
  const url = new URL(location.pathname, location.origin);
  url.hash = hash;
  if (navigator.share) navigator.share({title, text, url: url.href}).catch(() => {});
  else copy(`${text ? text + ' ' : ''}${url.href}`, TEXTS.link_copied);
}
for (const button of document.querySelectorAll('button[data-share]'))
  button.onclick = () => shareLink(button.closest('li').id, button.dataset.title, button.dataset.text);

function listenLink(url) {
  const link = element('a', TEXTS.listen, 'btn');
  link.href = url;
  link.target = '_blank';
  link.rel = 'noopener';
  return link;
}
function descriptionButton(text) {  // three lines of it, all of it when tapped
  const button = element('button', text, 'description');
  button.type = 'button';
  button.dir = 'auto';
  button.setAttribute('aria-expanded', 'false');
  button.onclick = () => button.setAttribute('aria-expanded', button.getAttribute('aria-expanded') !== 'true');
  return button;
}

// a series' lessons, from its own file (lessons/<feed id>.json), loaded when first opened; numbered, and
// listed from the first or the last
async function toggleEpisodes(li, open) {
  const button = li.querySelector('button[data-episodes]');
  const box = li.querySelector('.episodes');
  open = open ?? box.hidden;
  if (open && !box.childElementCount) {
    const episodes = await (await fetch(`lessons/${encodeURIComponent(li.id)}.json`)).json();
    const list = element('ol');
    list.append(...episodes.map(([title, date, minutes, url, text], index) => {
      const item = element('li');
      item.id = `${li.id}/${index + 1}`;
      const name = element('div', null, 'name');
      name.dir = 'auto';
      name.append(element('span', `${index + 1}.`, 'num'), title);
      item.append(name);
      if (text) item.append(descriptionButton(text));
      const meta = [date];
      if (minutes) meta.push(TEXTS.minutes.replace('{count}', minutes));
      const links = element('div', null, 'links');
      const share = element('button', TEXTS.share, 'btn');
      share.type = 'button';
      share.onclick = () => shareLink(`${li.id}/${index + 1}`, title);
      links.append(listenLink(url), share);
      item.append(element('div', meta.join(' · '), 'meta'), links);
      return item;
    }));
    const bar = element('div', null, 'episodes-bar');
    const order = element('button', TEXTS.from_last, 'btn');
    order.type = 'button';
    order.onclick = () => {
      list.append(...[...list.children].reverse());
      order.textContent = order.textContent === TEXTS.from_last ? TEXTS.from_first : TEXTS.from_last;
    };
    const close = element('button', TEXTS.close, 'btn');
    close.type = 'button';
    close.onclick = () => { toggleEpisodes(li, false); li.scrollIntoView({block: 'nearest'}); };
    bar.append(order);
    if (episodes.length > 1) box.append(bar);
    box.append(list, close);
  }
  box.hidden = !open;
  button.setAttribute('aria-expanded', open);
}
for (const button of document.querySelectorAll('button[data-episodes]'))
  button.onclick = () => toggleEpisodes(button.closest('li'));

// the views: home (the rabbis and the newest lessons), a rav's series (?rav=), search results (?q=), a series
// alone (#feed, or #feed/n for one of its lessons); the address is kept up to date, so any view can be shared,
// and Back returns to the one before
let rav = '';
const pills = [...document.querySelectorAll('#ravs button')];
for (const pill of pills) pill.onclick = () => { rav = pill.dataset.rav; typed(); };
for (const card of document.querySelectorAll('.ravs button'))
  card.onclick = () => { rav = card.dataset.rav; typed(); window.scrollTo({top: 0}); };
const sortSelect = $('sort');
sortSelect.value = store.get('sort') || 'name';
sortSelect.onchange = () => { store.set('sort', sortSelect.value); showBrowse(); };

function sorted(list) {
  const key = sortSelect.value;
  return [...list].sort((a, b) => key === 'updated' ? b.dataset.updated.localeCompare(a.dataset.updated)
    : key === 'size' ? b.dataset.size - a.dataset.size
    : a.dataset.name.localeCompare(b.dataset.name, 'he'));
}
function showBrowse() {
  const groups = $('groups');
  groups.replaceChildren();
  const mine = items.filter(li => li.dataset.rav === rav);
  $('browse-title').textContent = rav;
  for (const [group, label] of Object.entries(TEXTS.groups)) {
    let members = mine.filter(li => li.dataset.group === group);
    if (!members.length) continue;
    members = group === 'holiday' ? members.sort((a, b) => a.dataset.order - b.dataset.order) : sorted(members);
    const list = element('ul', null, 'plain series');
    list.append(...members);
    groups.append(element('h2', `${label} (${members.length})`), list);
  }
}

let searchTimer, lessons = null, loading = null;
function loadLessons() {
  loading = loading || fetch(LESSONS_URL).then(response => response.json())
    .catch(() => ({series: [], lessons: []})).then(data => lessons = data);
  return loading;
}
const input = $('search');
input.addEventListener('focus', loadLessons, {once: true});
input.oninput = () => { clearTimeout(searchTimer); searchTimer = setTimeout(typed, 180); };
wholeWords.onchange = typed;

function lessonResult([series, title, description, date, minutes, position, url], query) {
  const [feedId, seriesName, rav] = lessons.series[series];
  const li = element('li');
  const name = element('div', null, 'name');
  name.dir = 'auto';
  name.append(highlighted(title, query));
  li.append(name);
  if (description && !matcher(query)(title)) {  // found by its description: the part of it that matched
    const why = element('div', null, 'meta');
    why.dir = 'auto';
    why.append(highlighted(excerpt(description, query), query));
    li.append(why);
  }
  const meta = [`${seriesName} · ${rav}`, date];
  if (minutes) meta.push(TEXTS.minutes.replace('{count}', minutes));
  const link = element('a', TEXTS.to_series, 'btn');
  link.href = `#${feedId}/${position}`;
  link.onclick = event => {
    event.preventDefault();
    history.pushState(null, '', location.pathname + link.hash);
    show();
  };
  const links = element('div', null, 'links');
  links.append(listenLink(url), link);
  li.append(element('div', meta.join(' · '), 'meta'), links);
  return li;
}

async function showResults(query) {
  const matches = matcher(query);
  const seriesFound = items.filter(li => (!rav || li.dataset.rav === rav) && matches(li.dataset.search));
  $('series-results').replaceChildren(...seriesFound.slice(0, 30));
  $('series-found').textContent = seriesFound.length ? TEXTS.found_series.replace('{count}', seriesFound.length) : '';
  $('lessons').replaceChildren();
  $('lessons-found').textContent = '';
  $('lessons-more').textContent = '';
  if (query.length < 2) return;
  if (!lessons) $('status').textContent = TEXTS.loading;
  await loadLessons();
  if (input.value.trim() !== query) return;  // typed on in the meantime
  const LIMIT = 100;
  const all = lessons.lessons.filter(([series, title, text]) =>
    (!rav || lessons.series[series][2] === rav) && matches(title + ' ' + text));
  $('lessons-found').textContent = all.length ? TEXTS.found_lessons.replace('{count}', all.length) : '';
  $('lessons').replaceChildren(...all.slice(0, LIMIT).map(lesson => lessonResult(lesson, query)));
  $('lessons-more').textContent = all.length > LIMIT ? TEXTS.more.replace('{count}', all.length - LIMIT) : '';
  $('status').textContent = seriesFound.length || all.length ? ''
    : wholeWords.checked ? TEXTS.nothing_whole : TEXTS.nothing;
}

function typed() {
  const url = new URL(location.href);
  url.hash = '';
  const query = input.value.trim();
  for (const [key, value] of [['q', query], ['rav', rav], ['w', wholeWords.checked ? '1' : '']])
    if (value) url.searchParams.set(key, value); else url.searchParams.delete(key);
  history.replaceState(null, '', url);
  show();
}

async function show() {
  const url = new URL(location.href);
  input.value = url.searchParams.get('q') || '';
  rav = url.searchParams.get('rav') || '';
  wholeWords.checked = url.searchParams.get('w') === '1';
  for (const pill of pills) pill.setAttribute('aria-pressed', pill.dataset.rav === rav);
  $('status').textContent = '';
  for (const li of document.querySelectorAll('li.chosen')) li.classList.remove('chosen');
  const [feedId, position] = decodeURIComponent(url.hash.slice(1)).split('/');
  const query = input.value.trim();
  const view = byId[feedId] ? 'series' : query ? 'results' : rav ? 'browse' : 'home';
  $('home').hidden = view !== 'home';
  $('browse').hidden = view !== 'browse';
  $('results').hidden = view !== 'results';
  $('series').hidden = view !== 'series';
  if (view === 'browse') showBrowse();
  if (view === 'results') await showResults(query);
  if (view === 'series') {  // the series alone, with its lessons open, and a way back
    const li = byId[feedId];
    const series = $('series');
    const back = element('div', null, 'backbar');
    const button = element('button', `→ ${TEXTS.back}`, 'btn');
    button.type = 'button';
    button.onclick = () => {  // to the view the series was opened from: the search, the rav, or home
      history.pushState(null, '', location.pathname + location.search);
      show();
    };
    back.append(button);
    series.replaceChildren(back, li);
    li.classList.add('chosen');
    await toggleEpisodes(li, true);
    const episode = position && document.getElementById(`${feedId}/${Number(position)}`);
    if (episode) episode.classList.add('chosen');
    (episode || li).scrollIntoView({block: episode ? 'center' : 'start'});
  }
}
window.onpopstate = show;
window.onhashchange = show;
show();

const toTop = $('top');
window.addEventListener('scroll', () => toTop.hidden = window.scrollY < 1500, {passive: true});
toTop.onclick = () => window.scrollTo({top: 0, behavior: 'smooth'});
"""


def write_index(podcasts, path, title, lang='he', base_url='', stale=None):
    """
    A page listing the podcasts, for subscribing to them from a phone, and searching them and their episodes. Each
    podcast is a dict of its podgen 'podcast' (with the 'missing', 'course' and 'years' create_rss sets), and its
    'name', 'feed_id', 'source', 'rav' and 'rav_image' (the image config.toml gives his podcasts, if any).
    """
    texts = TEXTS.get(lang.split('-')[0], TEXTS['he'])
    base_url = base_url.rstrip('/') + '/'
    now = datetime.now(timezone.utc)
    items, series, lessons, newest = [], [], [], []
    for entry in sorted(podcasts, key=lambda entry: (entry['name'], entry['source'])):
        podcast, name, source, feed_id, rav = (entry[key] for key in ('podcast', 'name', 'source', 'feed_id', 'rav'))
        episodes = sorted(podcast.episodes, key=lambda episode: episode.publication_date)
        latest = episodes[-1].publication_date
        seconds = sum(episode.media.duration.total_seconds() for episode in episodes
                      if episode.media and episode.media.duration)
        meta = [texts['lessons_count'].format(count=len(episodes))]
        if getattr(podcast, 'years', ''):
            meta.append(podcast.years)
        if seconds:
            meta.append(texts['hours'].format(count=round(seconds / 3600)) if seconds >= 5400
                        else texts['minutes_total'].format(count=round(seconds / 60)))
        badges = ''
        if now - latest < ONGOING:
            badges += f' <span class="badge ongoing">{texts["ongoing"]}</span>'
        if getattr(podcast, 'missing', 0):
            badges += (f' <span class="badge missing" title="{texts["missing_title"].format(count=podcast.missing)}">'
                       f'{texts["missing"].format(count=podcast.missing)}</span>')
        group, order = group_of(name)
        items.append(ITEM.format(
            feed_id=escape(feed_id), rav=escape(rav), name=escape(name), source=escape(source), group=group, order=order,
            updated=latest.isoformat(), size=len(episodes),
            art=escape((podcast.image or '').removeprefix(base_url)), meta=' · '.join(meta), badges=badges,
            source_label=escape(texts['source'].get(source, source)),
            open=f'<a class="btn primary" data-app href="{escape(podcast_app_url(podcast.feed_url))}">{texts["open"]}</a>',
            lessons_button=texts['lessons_button'].format(count=len(episodes)),
            more=texts['more'], url=escape(podcast.feed_url), copy=texts['copy'],
            apple=f'<a class="btn" href="{escape(apple_podcasts_url(podcast.feed_url))}">{texts["apple"]}</a>',
            share=texts['share'], share_title=escape(name),
            share_text=escape(texts['script']['share_text'].format(name=name, rav=rav, count=len(episodes))),
        ))
        series.append([feed_id, name, rav])
        lessons += [search_entry(len(series) - 1, episode, position, texts)
                    for position, episode in enumerate(episodes, 1)]
        newest += [(episode, position, feed_id, name, rav) for position, episode in enumerate(episodes, 1)][-3:]
        write_episodes(path.parent / EPISODES_DIR / f'{feed_id}.json', episodes, texts)

    index = json.dumps({'series': series, 'lessons': lessons}, ensure_ascii=False, separators=(',', ':'))
    lessons_file = f'{LESSONS_PREFIX}.{hashlib.sha1(index.encode()).hexdigest()[:10]}.json'
    for old in path.parent.glob(f'{LESSONS_PREFIX}*.json'):
        old.unlink()
    (path.parent / lessons_file).write_text(index, encoding='utf8')

    ravs = rav_summary(podcasts, base_url)
    sources = sorted({entry['source'] for entry in podcasts if entry['source']})
    replacements = {
        'LANG': escape(lang), 'DIR': texts['dir'], 'TITLE': escape(title), 'TAGLINE': escape(texts['tagline']),
        'BASE': escape(base_url), 'FAVICON': FAVICON.replace('#', '%23').replace('"', "'"),
        'SKIP': texts['skip'],
        'SUMMARY': texts['summary'].format(count=len(items), ravs=len(ravs), updated=texts['date'](now.date())),
        'STALE': stale_note(stale, texts),
        'HOWTO': texts['howto'], 'HOWTO_BODY': texts['howto_body'].format(pocketcasts=POCKET_CASTS),
        'FILTER': texts['filter'], 'FILTER_LABEL': texts['filter_label'], 'WHOLE_WORDS': texts['whole_words'],
        'RAVS_TITLE': texts['ravs_title'], 'RAV_PILLS': rav_pills(ravs, texts), 'RAV_CARDS': rav_cards(ravs, texts),
        'NEW_TITLE': texts['new_title'], 'NEW': new_lessons(newest, texts),
        'SORT': texts['sort'], 'SORT_NAME': texts['sort_name'], 'SORT_UPDATED': texts['sort_updated'],
        'SORT_SIZE': texts['sort_size'],
        'ITEMS': '\n'.join(items),
        'FOOTER': texts['footer'].format(sources=', '.join(sources), issues=ISSUES_URL),
        'TEXTS': json.dumps({**texts['script'], 'groups': texts['groups']}, ensure_ascii=False),
        'LESSONS_URL': json.dumps(lessons_file),
        'SCRIPT': SCRIPT,
    }
    page = PAGE
    for key, value in replacements.items():
        page = page.replace(f'%{key}%', value)
    path.write_text(page, encoding='utf8')
    presentation.make_site_images(path.parent, title, texts['tagline'], len(items), len(ravs))
    (path.parent / 'manifest.webmanifest').write_text(json.dumps({
        'name': title, 'short_name': title, 'lang': lang, 'dir': texts['dir'], 'start_url': '.', 'display': 'standalone',
        'background_color': '#fbfaf7', 'theme_color': '#2f5d8a',
        'icons': [{'src': f'icon-{size}.png', 'sizes': f'{size}x{size}', 'type': 'image/png'} for size in (192, 512)],
    }, ensure_ascii=False), encoding='utf8')


def group_of(name):
    """a podcast's group on its rav's page ('course', 'holiday' or 'general'), and its order among holidays"""
    plain = name.split(' · ')[0]
    if plain in HOLIDAYS:
        return 'holiday', HOLIDAYS.index(plain)
    return ('general' if GENERAL.match(plain) else 'course'), 0


def rav_summary(podcasts, base_url):
    """each rav, with his number of podcasts and his portrait (only one of this site's own: the others are logos)"""
    counts = collections.Counter(entry['rav'] for entry in podcasts)
    portraits = {}
    for entry in podcasts:
        image = entry.get('rav_image') or ''
        if image.startswith(base_url) and not image.endswith('bneidavid.png'):
            portraits.setdefault(entry['rav'], image.removeprefix(base_url))
    return [(rav, count, portraits.get(rav)) for rav, count in counts.most_common()]


def rav_pills(ravs, texts):
    return ''.join([f'<button type="button" data-rav="">{texts["all"]}</button>'] +
                   [f'<button type="button" data-rav="{escape(rav)}">{escape(rav)}</button>' for rav, _, _ in ravs])


def rav_cards(ravs, texts):
    cards = []
    for rav, count, portrait in ravs:
        picture = (f'<img src="{escape(portrait)}" alt="" loading="lazy" width="72" height="72">' if portrait else
                   f'<span class="avatar" style="background:{presentation.rav_color(rav)}">'
                   f'{escape(rav.split()[-1][0])}</span>')
        cards.append(f'<li><button type="button" data-rav="{escape(rav)}">{picture}'
                     f'<span class="who">{escape(rav)}</span>'
                     f'<span class="count">{texts["series_count"].format(count=count)}</span></button></li>')
    return ''.join(cards)


def new_lessons(newest, texts):
    lines = []
    for episode, position, feed_id, name, rav in sorted(newest, key=lambda item: item[0].publication_date,
                                                         reverse=True)[:NEW_LESSONS]:
        url = escape(audio_url(episode))
        lines.append(
            f'<li><div class="name" dir="auto">{escape(episode.original_title or episode.title or "")}</div>'
            f'<div class="meta">{escape(name)} · {escape(rav)} · {texts["date"](episode.publication_date.date())}</div>'
            f'<div class="links"><a class="btn" href="{url}" target="_blank" rel="noopener">{texts["script"]["listen"]}</a>'
            f'<a class="btn" href="#{escape(feed_id)}/{position}">{texts["script"]["to_series"]}</a></div></li>')
    return ''.join(lines)


def stale_note(stale, texts):
    """a line, when some site's newest lessons couldn't be read"""
    if not stale:
        return ''
    names = {'meirtv.com': 'ערוץ מאיר', 'bneidavid.org': 'בני דוד', 'www.hakotel.org.il': 'ישיבת הכותל',
             'shaveihevron.org': 'שבי חברון'}
    dates = [re.search(r'of (\d{4}-\d{2}-\d{2})', reason) for reason in stale.values()]
    sites = ', '.join(names.get(urlparse(site).netloc, urlparse(site).netloc) for site in stale)
    date = min((datetime.fromisoformat(match.group(1)).date() for match in dates if match), default=None)
    return f'<p class="note">{texts["stale"].format(sites=sites, date=texts["date"](date) if date else "")}</p>' \
        if date else ''


def write_episodes(path, episodes, texts):
    """a podcast's episodes: [title, date, minutes, audio url, description] each"""
    path.parent.mkdir(parents=True, exist_ok=True)
    # (numbered by the page itself)
    path.write_text(json.dumps([[re.sub(r'^\d+\.\s+', '', episode.title or ''), texts['date'](episode.publication_date.date()),
                                 minutes(episode), audio_url(episode), description(episode, texts)]
                                for episode in episodes], ensure_ascii=False, separators=(',', ':')),
                    encoding='utf8')


def audio_url(episode):
    return episode.media.url if episode.media else ''


def description(episode, texts, limit=None):
    """the episode's own description as plain text, unless it's only its date, as many are"""
    summary = getattr(episode, 'original_summary', None)
    text = ' '.join(html.unescape(re.sub(r'<[^>]+>', ' ', html.unescape(summary or ''))).split())
    if text == texts['date'](episode.publication_date.date()):
        return ''
    return text[:limit] + '…' if limit and len(text) > limit else text


def minutes(episode):
    duration = episode.media.duration if episode.media else None
    return round(duration.total_seconds() / 60) if duration else None


def search_entry(series, episode, position, texts):
    """[series index, title, description (searched too), date, minutes, position in its series, audio url]"""
    return [series, getattr(episode, 'original_title', None) or episode.title or '',
            description(episode, texts, DESCRIPTION_LIMIT), texts['date'](episode.publication_date.date()),
            minutes(episode), position, audio_url(episode)]


def podcast_app_url(feed_url):
    """Pocket Casts (and some other apps) open feeds by the pcast:// scheme"""
    return 'pcast://' + feed_url.removeprefix(f'{urlparse(feed_url).scheme}://')


def apple_podcasts_url(feed_url):
    """the iPhone's Podcasts app opens feeds by the podcast:// scheme"""
    return 'podcast://' + feed_url.removeprefix(f'{urlparse(feed_url).scheme}://')
