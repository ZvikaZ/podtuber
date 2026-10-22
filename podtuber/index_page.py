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
CATALOG_FILENAME = 'catalog.json'  # the app's (android/), see write_catalog
CATALOG_VERSION = 1  # raised when the catalog changes in a way an installed app can't read
NEWEST_IN_CATALOG = 50
APK = 'shiurim.apk'  # the app (android/), as built, published from static_dir
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
        'tagline': 'שיעורי תורה כפודקאסטים, שמתעדכנים מעצמם.',
        'summary': '{count} סדרות · {ravs} רבנים · עודכן {updated}',
        'stale': 'שיעורי {sites} מעודכנים עד {date}.',
        'howto': 'איך מאזינים?',
        'howto_body': (
            '<ul><li>כאן: <b>האזנה</b>, ליד כל שיעור.</li>'
            '<li><b>באנדרואיד:</b> האפליקציה שלנו מציעה נגן מלא, המשך האזנה וסימון שיעורים שנשמעו, ופועלת גם ב־Android Auto. '
            '<button type="button" class="btn" id="car-open">הורדת האפליקציה</button></li>'
            '<li>באפליקציית פודקאסטים אחרת, עם שיעורים חדשים מעצמם: <b>הוספה לאפליקציה</b> (מומלצת '
            '<a href="{pocketcasts}">Pocket Casts</a>). לא נפתחה? <b>העתקת הכתובת</b>, ובאפליקציה: הוספה לפי כתובת.</li></ul>'
            # how to install the app, and optionally let Android Auto show it (it isn't from Google Play); in the
            # app (where this page is its screen), without the download
            '<dialog id="car"><h2>האפליקציה לאנדרואיד</h2><ol>'
            '<li class="download"><a class="btn primary" href="{apk}" download>הורדת האפליקציה</a><br>'
            'פותחים את הקובץ שירד ומתקינים. אם הטלפון שואל, מאשרים התקנה ממקור זה.</li>'
            '<li>פותחים את <b>שיעורים לדרך</b> ומאזינים בטלפון. להאזנה גם ברכב, ממשיכים לשלבים הבאים:</li>'
            '<li>פותחים את ההגדרות של Android Auto (בהגדרות הטלפון, חיפוש: Android Auto), גוללים לסוף, '
            'ולוחצים 10 פעמים על <b>גרסה</b>, עד שמופיעה הודעה על מצב מפתחים.</li>'
            '<li>באותו מסך: בתפריט <b>⋮</b> למעלה, <b>הגדרות מפתחים</b>, ומסמנים <b>מקורות לא ידועים</b>.</li>'
            '<li>ברכב, האפליקציה <b>שיעורים לדרך</b> מופיעה עם שאר האפליקציות. לא מופיעה? בהגדרות Android Auto, '
            '<b>התאמה אישית של מרכז האפליקציות</b>, ומסמנים אותה.</li></ol>'
            '<form method="dialog"><button class="btn">סגירה</button></form></dialog>'),
        'ravs_title': 'הרבנים',
        'rav_sort': 'מיון רבנים:',
        'rav_sort_name': 'שם משפחה (א–ת)',
        'rav_sort_series': 'מספר סדרות',
        'rav_sort_lessons': 'מספר שיעורים',
        'series_count': '{count} סדרות',
        'rav_counts': '{series} סדרות · {lessons} שיעורים',
        'new_title': 'שיעורים חדשים',
        'scope': 'סינון לפי {rav} – ביטול',
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
        'missing': lambda count: 'חסר שיעור' if count == 1 else f'חסרים {count} שיעורים',
        'missing_title': 'שיעורים שאין להם הקלטה באתר המקור',
        'source': {'אתר הרב': 'האתר של הרב', 'פודקאסט': 'פודקאסט רשמי'},
        'open': 'הוספה לאפליקציה',
        'lessons_button': 'השיעורים ({count})',
        'copy': 'העתקת הכתובת',
        'share': 'שיתוף',
        'footer': ('אתר ואפליקציה לא רשמיים, שפותחו ומתוחזקים על־ידי צביקה הרמתי. '
                   'השיעורים מגיעים מ{sources}, וכל הזכויות שמורות לבעלי התוכן. '
                   'הצעות ודיווח על בעיות: <a href="{issues}">כאן</a>.'),
        'script': {
            'close': 'סגירה',
            'car_instructions': 'איך מפעילים',
            'hide_lessons': 'סגירת השיעורים',
            'back': 'חזרה',
            'listen': 'האזנה',
            'continue_title': 'המשך',
            'heard': 'נשמע ✓',
            'mark_heard': 'סימון כנשמע',
            'mark_unheard': 'סימון כלא נשמע',
            'mark_series_heard': 'סימון כל הסדרה כנשמעה',
            'mark_series_unheard': 'סימון כל הסדרה כלא נשמעה',
            'remove_continue': 'הסרה מהמשך',
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
            'no_app': 'לא נפתחה אפליקציה? אפשר להעתיק את הכתובת ולהוסיף אותה באפליקציה.',
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
  :root { color-scheme: light dark;  /* the browser's own controls (checkbox, select) in the page's mode */
          --bg: #fbfaf7; --fg: #1d1c1a; --muted: #595650; --line: #e4e1da; --accent: #2f5d8a; --on-accent: #ffffff;
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
  #car-open { min-height: 36px; padding-block: .2rem; margin-inline-start: .25rem; }
  dialog#car { max-width: min(32rem, calc(100vw - 32px)); border: 1px solid var(--line); border-radius: .75rem;
               background: var(--bg); color: var(--fg); padding: 1rem 1.25rem; }
  dialog#car::backdrop { background: rgb(0 0 0 / .45); }
  dialog#car h2 { margin-top: 0; }
  dialog#car li { margin-bottom: .6rem; }
  dialog#car .download .btn { margin-bottom: .35rem; }
  .bar { position: sticky; top: env(safe-area-inset-top, 0px); z-index: 2; background: var(--bg);
         max-width: 46rem; margin: 0 auto; padding: .6rem 16px; border-bottom: 1px solid var(--line); }
  input[type=search] { width: 100%; padding: .7rem .8rem; font: inherit; color: inherit; background: var(--bg);
         border: 1px solid var(--muted); border-radius: .5rem; min-height: 44px; }
  .option { display: inline-flex; align-items: center; gap: .4rem; margin-top: .35rem; color: var(--muted);
            font-size: .9rem; cursor: pointer; min-height: 32px; }
  .option input { width: 1.1rem; height: 1.1rem; }
  #scope { margin-inline-start: 1rem; padding: .2rem .7rem; border-radius: 99px; min-height: 32px; font-size: .85rem;
           text-decoration: none; background: var(--accent); color: var(--on-accent); }
  .ravs { display: grid; grid-template-columns: repeat(auto-fill, minmax(6.75rem, 1fr)); gap: .5rem; padding: 0;
          list-style: none; }
  .ravs button { width: 100%; background: transparent; display: flex; flex-direction: column; align-items: center; gap: .25rem; padding: .6rem .25rem;
                 border: 1px solid var(--line); border-radius: .6rem; text-decoration: none; color: var(--fg);
                 min-height: 44px; }
  .ravs img, .avatar { width: 52px; height: 52px; border-radius: 50%; object-fit: cover; }
  .avatar { display: grid; place-items: center; color: #fff; font-size: 1.25rem; font-weight: 600; }
  .ravs .who { font-weight: 600; font-size: .9rem; text-align: center; line-height: 1.25; }
  .ravs .count { color: var(--muted); font-size: .8rem; }
  ul.plain { list-style: none; margin: 0; padding: 0; }
  .series > li { display: grid; grid-template-columns: 72px 1fr; gap: .25rem .9rem; padding: .9rem 0;
                 border-top: 1px solid var(--line); scroll-margin-top: 9rem; }
  .series > li > * { min-width: 0; }
  .series .art { width: 72px; height: 72px; border-radius: .4rem; grid-row: span 2; }
  li.chosen { background: color-mix(in srgb, var(--accent) 8%, transparent); }
  /* what opens when tapped: a rav, a series in a list, a lesson found or new */
  .go, button { cursor: pointer; }
  .go:hover:not(:has(.episodes:not([hidden]))), .ravs button:hover {
    background: color-mix(in srgb, var(--accent) 7%, transparent); }
  .ravs button:hover { border-color: var(--accent); }
  .btn:hover { background: color-mix(in srgb, var(--accent) 10%, transparent); }
  .btn.primary:hover { background: var(--accent); filter: brightness(1.12); }
  .name { font-weight: 600; }
  .meta, .source { color: var(--muted); font-size: .875rem; }
  .badge { display: inline-block; font-size: .78rem; padding: .05rem .5rem; border-radius: 99px; margin-inline-start: .3rem; }
  .badge.missing { color: var(--warn); background: var(--warn-soft); }
  .badge.ongoing { color: var(--good); background: var(--good-soft); }
  .actions { grid-column: 1 / -1; display: flex; gap: .5rem; flex-wrap: wrap; align-items: center; margin-top: .4rem; }
  .btn { display: inline-flex; align-items: center; justify-content: center; min-height: 44px;
         padding: .45rem .9rem; border-radius: .5rem; border: 1px solid var(--line); font: inherit; font-size: .95rem;
         color: var(--accent); background: transparent; text-decoration: none; cursor: pointer; }
  .btn.primary { background: var(--accent); border-color: var(--accent); color: var(--on-accent); font-weight: 600; }
  .btn.quiet { border-color: transparent; padding-inline: .5rem; }  /* secondary: copying and sharing */
  .secondary { display: flex; margin-inline-start: auto; }  /* together, at the row's end, or wrapped below */
  .episodes { grid-column: 1 / -1; margin-top: .5rem; }
  .episodes-bar { display: flex; gap: .5rem; align-items: center; flex-wrap: wrap; position: sticky; z-index: 1;
                  top: calc(env(safe-area-inset-top, 0px) + var(--bar, 0px)); background: var(--bg);
                  padding-block: .4rem; border-bottom: 1px solid var(--line); }
  .episodes-bar .name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  li.chosen .episodes-bar { background: color-mix(in srgb, var(--accent) 8%, var(--bg)); }
  .episodes ol { list-style: none; margin: .25rem 0 0; padding: 0; }
  .episodes ol > li, #lessons li, #new li { padding: .6rem 0; border-top: 1px solid var(--line); }
  #continue-list li { padding: .6rem 0; border-top: 1px solid var(--line); }
  li.heard > .name::after { content: " ✓"; color: var(--good); }
  li.started > .name::after { content: " ◔"; color: var(--accent); }
  .links .heard-action[disabled] { color: var(--good); border-color: transparent; opacity: 1; cursor: default; }
  .num { color: var(--muted); font-variant-numeric: tabular-nums; margin-inline-end: .35rem; }
  .description { display: block; text-align: start; color: var(--muted); font: inherit; font-size: .9rem; background: none;
                 border: 0; padding: 0; cursor: pointer; display: -webkit-box; -webkit-box-orient: vertical;
                 -webkit-line-clamp: 3; overflow: hidden; }
  .description[aria-expanded=true] { -webkit-line-clamp: unset; }
  #browse .rav-name { display: none; }  /* the rav's page names him once, as its title */
  .row { display: flex; gap: .25rem .5rem; flex-wrap: wrap; align-items: center; justify-content: space-between; }
  .links { display: flex; gap: .4rem; }
  .links .btn { min-height: 34px; padding: .15rem .7rem; font-size: .875rem; }
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
<button type="button" id="scope" hidden></button>
</div>
<main id="content">
<p id="status" class="note" aria-live="polite"></p>
<section id="home">
<div id="continue-home" hidden><h2>%CONTINUE_TITLE%</h2><ul class="plain" id="continue-list"></ul></div>
<div class="group-head"><h2>%RAVS_TITLE%</h2>
<label class="sort">%RAV_SORT% <select id="rav-sort"><option value="name">%RAV_SORT_NAME%</option><option value="series">%RAV_SORT_SERIES%</option><option value="lessons">%RAV_SORT_LESSONS%</option></select></label></div>
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

ITEM = """<li id="{feed_id}" class="go" data-go="{feed_id}" data-rav="{rav}" data-name="{name}" data-search="{name} {rav} {source}" data-group="{group}"
    data-order="{order}" data-updated="{updated}" data-size="{size}">
  <img class="art" src="{art}" alt="" loading="lazy" width="72" height="72">
  <div class="name" dir="auto">{name}</div>
  <div class="meta">{meta}{badges}<br><span class="source">{source_label}</span></div>
  <div class="actions">
    {open}
    <button type="button" class="btn" data-episodes aria-expanded="false" aria-controls="ep-{feed_id}">{lessons_button}</button>
    <span class="secondary"><button type="button" class="btn quiet" data-copy="{url}">{copy}</button>
    <button type="button" class="btn quiet" data-share data-title="{share_title}" data-text="{share_text}">{share}</button></span>
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
const car = $('car');
$('car-open').onclick = () => car.showModal();
car.onclick = event => {  // a tap outside it
  const box = car.getBoundingClientRect();
  if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom)
    car.close();
};

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

// opening a podcast app: the iPhone's own by podcast://, any other by pcast:// (Pocket Casts, Podcast Addict...);
// if the page is still in view a moment later, none opened
const iphone = /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
for (const link of document.querySelectorAll('a[data-app]')) {
  if (iphone) link.href = link.href.replace(/^pcast:/, 'podcast:');
  link.addEventListener('click', () => {
    let left = false;
    const away = () => left = true;
    document.addEventListener('visibilitychange', away, {once: true});
    setTimeout(() => { if (!left && document.visibilityState === 'visible') toast(TEXTS.no_app); }, 1800);
  });
}
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

function listenLink(url, lesson) {  // lesson: "<series id>/<its number>", which the app plays (see below)
  const link = element('a', TEXTS.listen, 'btn');
  link.href = url;
  link.target = '_blank';
  link.rel = 'noopener';
  link.dataset.lesson = lesson;
  return link;
}
const app = window.ShiurimApp;
function decorateLesson(item, lesson) {
  if (!app || !item) return item;
  item.dataset.lessonKey = lesson;
  const state = app.state(lesson);
  item.classList.toggle('heard', state === 'heard');
  item.classList.toggle('started', state === 'started');
  const links = item.querySelector(':scope > .row > .links');
  if (!links) return item;
  let button = links.querySelector('.heard-action');
  if (!button) {
    button = element('button', null, 'btn quiet heard-action');
    button.type = 'button';
    button.onclick = () => {
      if (app.state(lesson) === 'heard') app.markUnheard(lesson);
      else app.markHeard(lesson);
      decorateLesson(item, lesson);
      showContinue();
    };
    links.append(button);
  }
  button.textContent = state === 'heard' ? TEXTS.mark_unheard : TEXTS.mark_heard;
  button.disabled = false;
  return item;
}
// in the Android app (android/), whose screen is this page: a lesson is played by its player (as in the car, where
// it can be continued)
if (app) {
  document.addEventListener('click', event => {
    const link = event.target.closest('a[data-lesson]');
    if (!link) return;
    event.preventDefault();
    app.play(link.dataset.lesson);
  }, true);
  // the app is here already: only how to have it in the car
  car.querySelector('.download').remove();
  $('car-open').textContent = TEXTS.car_instructions;
  for (const link of document.querySelectorAll('a[data-lesson]'))
    decorateLesson(link.closest('li'), link.dataset.lesson);
}
function row(meta, links) {  // a lesson's date and length, and its buttons beside them
  const line = element('div', null, 'row');
  line.append(element('div', meta.join(' · '), 'meta'), links);
  return line;
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
  if (open === !box.hidden) return;
  // closed, it's back where it was on the screen when it opened (however far its lessons were scrolled through)
  if (open) li.dataset.top = li.getBoundingClientRect().top;
  if (open && !box.childElementCount) {
    const episodes = await (await fetch(`lessons/${encodeURIComponent(li.id)}.json`)).json();
    const list = element('ol');
    list.append(...episodes.map(([title, date, minutes, url, text], index) => {
      const lesson = `${li.id}/${index + 1}`;
      const item = element('li');
      item.id = lesson;
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
      links.append(listenLink(url, lesson), share);
      item.append(row(meta, links));
      return decorateLesson(item, lesson);
    }));
    // the series' name, closing and the lessons' order, kept in view (under the search bar) through the lessons
    const bar = element('div', null, 'episodes-bar');
    const name = element('span', li.dataset.name, 'name');
    name.dir = 'auto';
    const order = element('button', TEXTS.from_last, 'btn quiet');
    order.type = 'button';
    order.onclick = () => {
      list.append(...[...list.children].reverse());
      order.textContent = order.textContent === TEXTS.from_last ? TEXTS.from_first : TEXTS.from_last;
    };
    const close = element('button', `${TEXTS.close} ✕`, 'btn');
    close.type = 'button';
    close.onclick = () => closeEpisodes(li);
    bar.append(name);
    if (app) {
      const heard = element('button', null, 'btn quiet');
      heard.type = 'button';
      const update = () => {
        const complete = [...list.children].every(item => app.state(item.dataset.lessonKey) === 'heard');
        heard.textContent = complete ? TEXTS.mark_series_unheard : TEXTS.mark_series_heard;
      };
      heard.onclick = () => {
        const complete = [...list.children].every(item => app.state(item.dataset.lessonKey) === 'heard');
        if (complete) app.markSeriesUnheard(li.id, episodes.length);
        else app.markSeriesHeard(li.id, episodes.length);
        for (const item of list.children) decorateLesson(item, item.dataset.lessonKey);
        update();
        showContinue();
      };
      update();
      bar.append(heard);
    }
    if (episodes.length > 1) bar.append(order);
    bar.append(close);
    box.append(bar, list);
  }
  box.hidden = !open;
  if (!open && li.dataset.top) window.scrollBy(0, li.getBoundingClientRect().top - li.dataset.top);
  button.setAttribute('aria-expanded', open);
  button.dataset.label = button.dataset.label || button.textContent;
  button.textContent = open ? TEXTS.hide_lessons : button.dataset.label;
}
function closeEpisodes(li) {
  toggleEpisodes(li, false);
}
// the sticky lessons' bar sits under the sticky search bar, whatever its height
const searchBar = document.querySelector('.bar');
const barHeight = () => document.documentElement.style.setProperty('--bar', `${searchBar.offsetHeight}px`);
barHeight();
window.addEventListener('resize', barHeight);
for (const button of document.querySelectorAll('button[data-episodes]'))
  button.onclick = () => toggleEpisodes(button.closest('li'));

// the views: home (the rabbis and the newest lessons), a rav's series (?rav=), search results (?q=), a series
// alone (#feed, or #feed/n for one of its lessons); the address is kept up to date, so any view can be shared,
// and Back returns to the one before
let rav = '';
const scope = $('scope');  // shown while a rav is chosen: his series, and searching only them; tapped, all ravs
scope.onclick = () => { rav = ''; typed(true); };
for (const card of document.querySelectorAll('.ravs button'))
  card.onclick = () => { rav = card.dataset.rav; typed(true); window.scrollTo({top: 0}); };
const ravList = document.querySelector('.ravs');
const ravSort = $('rav-sort');
ravSort.value = store.get('rav-sort') || 'series';
function sortRavs() {
  const key = ravSort.value;
  const cards = [...ravList.children];
  const bySurname = (a, b) => a.dataset.name.trim().split(/\s+/).at(-1).localeCompare(
    b.dataset.name.trim().split(/\s+/).at(-1), 'he') || a.dataset.name.localeCompare(b.dataset.name, 'he');
  cards.sort((a, b) => key === 'series' ? b.dataset.series - a.dataset.series || bySurname(a, b)
    : key === 'lessons' ? b.dataset.lessons - a.dataset.lessons || bySurname(a, b)
    : bySurname(a, b));
  ravList.append(...cards);
}
ravSort.onchange = () => { store.set('rav-sort', ravSort.value); sortRavs(); };
sortRavs();
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
  const lesson = `${feedId}/${position}`;
  const li = element('li', null, 'go');
  li.dataset.go = lesson;
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
  links.append(listenLink(url, lesson), link);
  li.append(row(meta, links));
  return decorateLesson(li, lesson);
}

async function showContinue() {
  if (!app) return;
  await loadLessons();
  let recent = [];
  try { recent = JSON.parse(app.recent()); } catch {}
  const entries = new Map(lessons.lessons.map(entry => {
    const [series, , , , , position] = entry;
    return [`${lessons.series[series][0]}/${position}`, entry];
  }));
  const rows = recent.map(key => {
    const slash = key.lastIndexOf('/');
    const position = Number(key.slice(slash + 1));
    const target = app.state(key) === 'heard' ? `${key.slice(0, slash)}/${position + 1}` : key;
    const entry = entries.get(target);
    if (!entry) return null;
    const item = lessonResult(entry, '');
    const remove = element('button', TEXTS.remove_continue, 'btn quiet');
    remove.type = 'button';
    remove.onclick = () => {
      app.removeFromContinue(key);
      showContinue();
    };
    item.querySelector(':scope > .row > .links').append(remove);
    return item;
  }).filter(Boolean);
  $('continue-list').replaceChildren(...rows);
  $('continue-home').hidden = !rows.length;
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

function typed(push) {  // choosing a rav, or leaving him, is a new page in the history; typing isn't
  const url = new URL(location.href);
  url.hash = '';
  const query = input.value.trim();
  for (const [key, value] of [['q', query], ['rav', rav], ['w', wholeWords.checked ? '1' : '']])
    if (value) url.searchParams.set(key, value); else url.searchParams.delete(key);
  if (push) history.pushState(null, '', url); else history.replaceState(null, '', url);
  show();
}

async function show() {
  const url = new URL(location.href);
  input.value = url.searchParams.get('q') || '';
  rav = url.searchParams.get('rav') || '';
  wholeWords.checked = url.searchParams.get('w') === '1';
  scope.hidden = !rav;
  scope.textContent = TEXTS.scope.replace('{rav}', rav);
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
// a series in a list, or a lesson found or new, opens when tapped anywhere but its buttons (and not when its
// text is being selected)
document.addEventListener('click', event => {
  const row = event.target.closest('.go');
  if (!row || event.target.closest('a, button, .episodes') || getSelection().toString()) return;
  const lessons = row.querySelector(':scope > .episodes');
  if (lessons && !lessons.hidden) return closeEpisodes(row);  // open: tapped again, it closes
  if (row.parentElement.id === 'series') return toggleEpisodes(row, true);  // the series alone, its lessons closed
  history.pushState(null, '', location.pathname + location.search + '#' + row.dataset.go);
  show();
});
window.onpopstate = show;
window.onhashchange = show;
show();
if (app) showContinue();

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
    items, series, lessons, newest, catalog = [], [], [], [], []
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
            badges += (f' <span class="badge missing" title="{texts["missing_title"]}">'
                       f'{texts["missing"](podcast.missing)}</span>')
        group, order = group_of(name)
        items.append(ITEM.format(
            feed_id=escape(feed_id), rav=escape(rav), name=escape(name), source=escape(source), group=group, order=order,
            updated=latest.isoformat(), size=len(episodes),
            art=escape((podcast.image or '').removeprefix(base_url)), meta=' · '.join(meta), badges=badges,
            source_label=f'<span class="rav-name">{escape(rav)}{" · " if source else ""}</span>'
                         + escape(texts['source'].get(source, source)),
            open=f'<a class="btn primary" data-app href="{escape(podcast_app_url(podcast.feed_url))}">{texts["open"]}</a>',
            lessons_button=texts['lessons_button'].format(count=len(episodes)),
            url=escape(podcast.feed_url), copy=texts['copy'],
            share=texts['share'], share_title=escape(name),
            share_text=escape(texts['script']['share_text'].format(name=name, rav=rav, count=len(episodes))),
        ))
        series.append([feed_id, name, rav])
        catalog.append({'id': feed_id, 'name': name, 'rav': rav, 'group': group, 'order': order,
                        'lessons': len(episodes), 'updated': latest.isoformat(), 'years': getattr(podcast, 'years', ''),
                        'course': bool(getattr(podcast, 'course', False)), 'source': source, 'feed': podcast.feed_url,
                        'art': (podcast.image or '').removeprefix(base_url)})
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
    write_catalog(path.parent / CATALOG_FILENAME, now, ravs, catalog, newest, texts, lessons_file)
    sources = sorted({entry['source'] for entry in podcasts if entry['source']})
    replacements = {
        'LANG': escape(lang), 'DIR': texts['dir'], 'TITLE': escape(title), 'TAGLINE': escape(texts['tagline']),
        'BASE': escape(base_url), 'FAVICON': FAVICON.replace('#', '%23').replace('"', "'"),
        'SKIP': texts['skip'],
        'SUMMARY': texts['summary'].format(count=len(items), ravs=len(ravs), updated=texts['date'](now.date())),
        'STALE': stale_note(stale, texts),
        'HOWTO': texts['howto'], 'HOWTO_BODY': texts['howto_body'].format(pocketcasts=POCKET_CASTS, apk=APK),
        'FILTER': texts['filter'], 'FILTER_LABEL': texts['filter_label'], 'WHOLE_WORDS': texts['whole_words'],
        'CONTINUE_TITLE': texts['script']['continue_title'],
        'RAVS_TITLE': texts['ravs_title'], 'RAV_CARDS': rav_cards(ravs, texts),
        'RAV_SORT': texts['rav_sort'], 'RAV_SORT_NAME': texts['rav_sort_name'],
        'RAV_SORT_SERIES': texts['rav_sort_series'], 'RAV_SORT_LESSONS': texts['rav_sort_lessons'],
        'NEW_TITLE': texts['new_title'], 'NEW': new_lessons(newest, texts),
        'SORT': texts['sort'], 'SORT_NAME': texts['sort_name'], 'SORT_UPDATED': texts['sort_updated'],
        'SORT_SIZE': texts['sort_size'],
        'ITEMS': '\n'.join(items),
        'FOOTER': texts['footer'].format(sources=', '.join(sources), issues=ISSUES_URL),
        'TEXTS': json.dumps({**texts['script'], 'groups': texts['groups'], 'scope': texts['scope']}, ensure_ascii=False),
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


def write_catalog(path, now, ravs, series, newest, texts, search):
    """
    What the app (android/) browses, at a name that doesn't change: the ravs (by number of series), their series, and
    the newest lessons; a series' lessons are in its own file (lessons/<id>.json), as the page's are, and every lesson
    is in the page's search index (search). Paths of images are relative to the site.
    """
    images = {}
    for rav, series_count, lessons_count, portrait in ravs:  # without a portrait, the page shows a letter
        images[rav] = portrait or f'{presentation.ART_DIR}/rav-{hashlib.sha1(rav.encode()).hexdigest()[:8]}.png'
        if not portrait:
            presentation.make_avatar(path.parent / images[rav], rav)
    path.write_text(json.dumps({
        'version': CATALOG_VERSION,
        'updated': now.isoformat(timespec='seconds'),
        'groups': texts['groups'],
        'search': search,  # the page's search index, of every lesson
        'ravs': [{'name': rav, 'series': series_count, 'lessons': lessons_count, 'image': images[rav]}
                 for rav, series_count, lessons_count, portrait in ravs],
        'series': series,
        'newest': [{'series': feed_id, 'position': position, 'title': episode.original_title or episode.title or '',
                    'date': episode.publication_date.isoformat(), 'minutes': minutes(episode),
                    'url': audio_url(episode)}
                   for episode, position, feed_id, name, rav in sorted(newest, key=lambda item: item[0].publication_date,
                                                                       reverse=True)[:NEWEST_IN_CATALOG]],
    }, ensure_ascii=False, separators=(',', ':')), encoding='utf8')


def group_of(name):
    """a podcast's group on its rav's page ('course', 'holiday' or 'general'), and its order among holidays"""
    plain = name.split(' · ')[0]
    if plain in HOLIDAYS:
        return 'holiday', HOLIDAYS.index(plain)
    return ('general' if GENERAL.match(plain) else 'course'), 0


def rav_summary(podcasts, base_url):
    """each rav, with his podcast and lesson counts and portrait (only one of this site's own: the others are logos)"""
    counts = collections.Counter(entry['rav'] for entry in podcasts)
    lessons = collections.Counter()
    portraits = {}
    for entry in podcasts:
        lessons[entry['rav']] += len(entry['podcast'].episodes)
        image = entry.get('rav_image') or ''
        if image.startswith(base_url) and not image.endswith('bneidavid.png'):
            portraits.setdefault(entry['rav'], image.removeprefix(base_url))
    return [(rav, count, lessons[rav], portraits.get(rav)) for rav, count in counts.most_common()]


def rav_cards(ravs, texts):
    cards = []
    for rav, series_count, lessons_count, portrait in ravs:
        picture = (f'<img src="{escape(portrait)}" alt="" loading="lazy" width="72" height="72">' if portrait else
                   f'<span class="avatar" style="background:{presentation.rav_color(rav)}">'
                   f'{escape(rav.split()[-1][0])}</span>')
        cards.append(f'<li data-name="{escape(rav)}" data-series="{series_count}" data-lessons="{lessons_count}">'
                     f'<button type="button" data-rav="{escape(rav)}">{picture}'
                     f'<span class="who">{escape(rav)}</span>'
                     f'<span class="count">{texts["rav_counts"].format(series=series_count, lessons=lessons_count)}'
                     f'</span></button></li>')
    return ''.join(cards)


def new_lessons(newest, texts):
    lines = []
    for episode, position, feed_id, name, rav in sorted(newest, key=lambda item: item[0].publication_date,
                                                         reverse=True)[:NEW_LESSONS]:
        url = escape(audio_url(episode))
        lines.append(
            f'<li class="go" data-go="{escape(feed_id)}/{position}">'
            f'<div class="name" dir="auto">{escape(episode.original_title or episode.title or "")}</div>'
            f'<div class="row"><div class="meta">{escape(name)} · {escape(rav)} · '
            f'{texts["date"](episode.publication_date.date())}</div>'
            f'<div class="links"><a class="btn" href="{url}" target="_blank" rel="noopener" '
            f'data-lesson="{escape(feed_id)}/{position}">{texts["script"]["listen"]}</a>'
            f'<a class="btn" href="#{escape(feed_id)}/{position}">{texts["script"]["to_series"]}</a></div></div></li>')
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
    """Pocket Casts (and some other apps) open feeds by the pcast:// scheme; the page makes it podcast:// on iPhones"""
    return 'pcast://' + feed_url.removeprefix(f'{urlparse(feed_url).scheme}://')
