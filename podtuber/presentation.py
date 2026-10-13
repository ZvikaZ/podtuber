"""
How a podcast and its lessons are presented to listeners, in podcast apps (and in the car) and on the index page:
short names that tell podcasts apart when cut short, clean lesson titles, descriptions, and artwork.
"""
import hashlib
import re
from functools import cache
from pathlib import Path

from podtuber.hebrew_dates import gematria, number_name

FONTS = Path(__file__).parent / 'fonts'
ART_DIR = 'art'  # where each podcast's artwork is written, next to the feeds
ART_SIZE = 1000

# a Hebrew year, as the sites write it: 'התשסה', 'תשע"ב', '[תשע"ב]', '(תשס"ד)', "תשפ'ג", 'תש"ע'
YEAR = re.compile(r'''\[\s*ה?(ת[שר][א-ת]?["'׳״]?[א-ת]?)\s*\]|\(\s*ה?(ת[שר][א-ת]?["'׳״]?[א-ת]?)\s*\)|'''
                  r'''(?<![א-ת])ה?(ת[שר][א-ת]?["'׳״]?[א-ת]?)(?![א-ת])''')
# a lesson's duration in its title: '[1:11:40]', '[48:10]'
DURATION = re.compile(r'\s*\[\d{1,2}:\d{2}(?::\d{2})?\]')
SEPARATORS = ' -–|·,:'
SOURCE_LABELS = {'אתר הרב': 'האתר של הרב', 'פודקאסט': 'הפודקאסט של הרב'}  # sources' names, as listeners read them
SEPARATOR = '[' + ''.join(map(re.escape, SEPARATORS)) + ']'
# podcasts of lessons that don't follow each other (a rav's general lessons, holidays over the years), which apps
# should list newest first; all others are courses, to be heard in order
EPISODIC = re.compile(r'^(כללי|שיעורים נוספים|ימי עיון|חגים|שו"ת|קצרים|ראש השנה|יום כיפור|סוכות|חנוכה|ט"ו בשבט|פורים|'
                      r'פסח|ל"ג בעומר|ספירת העומר|יום השואה|יום העצמאות|יום הזיכרון|יום ירושלים|שבועות|תשעה באב|'
                      r'עשרה בטבת|אלול|שובבים)(?![א-ת])')


def year_of(text):
    """the first Hebrew year written in the text, as 'תשע"ג' (None if there's none)"""
    for match in YEAR.finditer(text):
        letters = re.sub('[^א-ת]', '', next(group for group in match.groups() if group))
        if 700 <= gematria(letters) < 800:  # 5700-5799
            return match, number_name(gematria(letters))
    return None, None


def short_name(name, rav):
    """
    A podcast's name without its rav (podcast apps show him as its author, and its artwork shows him too), and with
    its year written one way, last: 'אגדות פרק חלק - התשסה - הרב אורי שרקי' -> 'אגדות פרק חלק · תשס"ה'
    """
    if rav:
        first_names, surname = rav.split()[1:-1], rav.split()[-1]
        # 'הרב יוסף קלנר', 'הרב קלנר', or the rav's first name alone, as Bnei David names some series: 'חגים - הרב אוהד'
        name = re.sub(rf'(?:^|\s*{SEPARATOR}*\s*)הרב\s+(?:{"|".join(map(re.escape, first_names + [surname]))})'
                      rf'(?:\s+{re.escape(surname)})?(?![א-ת])(?:\s+(?:שליט"א|זצ"ל))?', ' ', name)
    match, year = year_of(name)
    if match:
        name = name[:match.start()] + ' ' + name[match.end():]
    name = re.sub(r'\(\s*', '(', re.sub(r'\s*\)', ')', ' '.join(name.split())))  # '(בני דוד )' -> '(בני דוד)'
    name = re.sub(r'\(\)|\[\]', '', name)
    name = re.sub(r'\s*[-–]\s*(?=[(\[])', ' ', name)  # 'מאמר הדור - (בני דוד)' -> 'מאמר הדור (בני דוד)'
    name = re.sub(r'\s*[-–|]\s*(?=[-–|]|$)', '', ' '.join(name.split()))  # separators left with nothing between
    name = name.strip(SEPARATORS + ' ') or name
    return f'{name} · {year}' if year else name


def is_course(name):
    """whether a podcast's lessons are meant to be heard in order (by its name, as short_name gives it)"""
    return not EPISODIC.match(name)


def episode_title(title, series_name, rav, number=None):
    """
    A lesson's title, cleaned for a podcast app's one line: no duration (the app shows it), no rav, no repeated
    series name after a '|'; and in a course, its number first: '2. התמודדות עם מערכת שכלית ללא אקסיומות'
    """
    title = DURATION.sub('', title)
    if rav:
        surname = rav.split()[-1]
        title = re.sub(rf'\s*[-–|]?\s*הרב\s+(?:\S+\s+){{0,2}}{re.escape(surname)}(?![א-ת])', '', title)
    *before, last = [part.strip() for part in title.split('|')]
    plain = lambda text: re.sub(r'[^א-ת0-9 ]', '', text)
    series = plain(series_name.split(' · ')[0])
    # 'subject | the series [2]': the subject
    if before and (re.search(r'\[\d+\]$', last) or series and plain(last).startswith(series[:12])):
        title = ' | '.join(before)
    if number:
        title = re.sub(rf'\s*\[{number}\]', '', title)  # the number is put first
    title = ' '.join(title.split()).strip(SEPARATORS + ' ') or title
    return f'{number}. {title}' if number else title


def channel_description(name, rav, source, website, count, missing, years, base_url):
    lines = [f'{count} שיעורים של {rav}' + (f', {years}' if years else '') + f'. מתוך {source}: {website}']
    if missing:
        lines.append(f'חסרים {missing} שיעורים, שאין להם הקלטה באתר המקור.')
    lines.append(f'עוד סדרות של {rav} ושל רבנים אחרים: {base_url}')
    return '\n'.join(lines)


def episode_note(number, count, name, rav, source):
    lesson = f'שיעור {number} מתוך {count}' if number else 'שיעור'
    return f'{lesson} בסדרה "{name}", {rav}. פורסם ב{source}.'


def years_span(dates):
    """'תשס"ה' or 'תשס"ה–תשע"ג', of the teaching years of the dates"""
    from podtuber.hebrew_dates import year_name
    years = sorted({year_name(date) for date in dates}, key=gematria)
    if not years:
        return ''
    return years[0] if len(years) == 1 else f'{years[0]}–{years[-1]}'


# artwork: the series' name, large, on the rav's color, with his name below, so that podcasts tell apart at a glance
PALETTE = ['#1f4e79', '#7a2e39', '#2e5e4e', '#5b3f86', '#8a5a14', '#24607a', '#6b3d2e', '#3e4f7a', '#55692a',
           '#7a3e66', '#2f6b6b', '#704f1f', '#4a3a6b', '#2d5f3a']


def rav_color(rav):
    return PALETTE[int(hashlib.sha1(rav.encode()).hexdigest(), 16) % len(PALETTE)]


def _shade(color, factor):
    """the color, darker"""
    return '#' + ''.join(f'{round(int(color[i:i + 2], 16) * factor):02x}' for i in (1, 3, 5))


@cache
def _font(name, size):
    from PIL import ImageFont
    font = ImageFont.truetype(str(FONTS / name), size)
    try:
        font.set_variation_by_name('Bold')
    except Exception:
        pass
    return font


def _visual(text):
    """Hebrew in visual order, for Pillow without a text-layout library"""
    from bidi import get_display
    # brackets in right-to-left text face the other way, which get_display leaves to the text-layout library
    return get_display(text, base_dir='R').translate(str.maketrans('()[]', ')(]['))


def _wrap(draw, text, font, width):
    lines, line = [], ''
    for word in text.split():
        candidate = f'{line} {word}'.strip()
        if draw.textlength(_visual(candidate), font=font) <= width or not line:
            line = candidate
        else:
            lines.append(line)
            line = word
    return lines + [line] if line else lines


def make_artwork(path, name, rav, source, portrait=None):
    """a square image: the series' name, as large as fits in up to four lines, the rav's portrait (when there is
    one) or a band of his color, and his name and the source below"""
    from PIL import Image, ImageDraw
    size = ART_SIZE
    color = rav_color(rav)
    image = Image.new('RGB', (size, size), color)
    draw = ImageDraw.Draw(image)
    top = 90
    if portrait and Path(portrait).is_file():
        face = Image.open(portrait).convert('RGB')
        side = min(face.size)
        face = face.crop(((face.width - side) // 2, 0, (face.width - side) // 2 + side, side)).resize((260, 260))
        mask = Image.new('L', (260, 260), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, 259, 259), fill=255)
        draw.ellipse(((size - 276) // 2, 62, (size + 276) // 2, 338), fill='#ffffff')
        image.paste(face, ((size - 260) // 2, 70), mask)
        top = 380
    title, year = (name.rsplit(' · ', 1) + [''])[:2] if ' · ' in name else (name, '')
    for font_size in (130, 112, 96, 84, 72, 62, 54):
        font = _font('FrankRuhlLibre.ttf', font_size)
        lines = _wrap(draw, title, font, size - 140)
        height = len(lines) * font_size * 1.18
        if len(lines) <= 4 and height <= size - top - 230:
            break
    y = top + (size - top - 230 - height) / 2
    for line in lines:
        draw.text((size / 2, y), _visual(line), font=font, fill='#ffffff', anchor='mt')
        y += font_size * 1.18
    if year:
        draw.text((size / 2, y + 10), _visual(year), font=_font('Heebo.ttf', 64), fill='#e6e6e6', anchor='mt')
    draw.rectangle((0, size - 190, size, size), fill=_shade(color, 0.7))
    draw.text((size / 2, size - 150), _visual(rav), font=_font('Heebo.ttf', 62), fill='#ffffff', anchor='mt')
    draw.text((size / 2, size - 72), _visual(SOURCE_LABELS.get(source, source)), font=_font('Heebo.ttf', 40), fill='#d0d0d0', anchor='mt')
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, quality=82, optimize=True)


def make_site_images(directory, title, tagline, podcasts, ravs):
    """the site's icons (for adding it to a phone's home screen) and its link preview image (for WhatsApp and the like)"""
    from PIL import Image, ImageDraw
    blue, paper = '#2f5d8a', '#fbfaf7'
    for size in (180, 192, 512):
        icon = Image.new('RGB', (size, size), blue)
        draw = ImageDraw.Draw(icon)
        k = size / 64  # the favicon's book and sound waves, drawn at this size
        draw.polygon([(10 * k, 27 * k), (21 * k, 25 * k), (32 * k, 29 * k), (43 * k, 25 * k), (54 * k, 27 * k),
                      (54 * k, 52 * k), (43 * k, 50 * k), (32 * k, 54 * k), (21 * k, 50 * k), (10 * k, 52 * k)], fill=paper)
        draw.line([(32 * k, 29 * k), (32 * k, 54 * k)], fill=blue, width=max(1, round(2.5 * k)))
        for radius, top in ((9, 13), (14, 7)):
            draw.arc([(32 - radius) * k, top * k, (32 + radius) * k, (top + 2 * radius) * k], 200, 340, fill=paper,
                     width=max(1, round(3.5 * k)))
        icon.save(directory / f'icon-{size}.png', optimize=True)
    image = Image.new('RGB', (1200, 630), blue)
    draw = ImageDraw.Draw(image)
    draw.text((600, 200), _visual(title), font=_font('FrankRuhlLibre.ttf', 120), fill=paper, anchor='mm')
    for number, line in enumerate(_wrap(draw, tagline, _font('Heebo.ttf', 44), 1000)):
        draw.text((600, 330 + number * 62), _visual(line), font=_font('Heebo.ttf', 44), fill='#dfe8f1', anchor='mm')
    draw.text((600, 530), _visual(f'{podcasts} סדרות · {ravs} רבנים'), font=_font('Heebo.ttf', 40), fill=paper,
              anchor='mm')
    image.save(directory / 'og.png', optimize=True)
