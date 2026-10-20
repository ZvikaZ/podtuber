"""
Writes the speed button's icons (res/drawable/ic_speed_*.xml): the speed itself, "1.5×", in Rubik SemiBold, as
vector paths, since the car draws a custom action's icon from a drawable and a drawable can't hold text.

    uv run --with fonttools python android/tools/speed_icons.py
"""
import urllib.request
from io import BytesIO
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

FONT = 'https://github.com/google/fonts/raw/main/ofl/rubik/Rubik%5Bwght%5D.ttf'
WEIGHT = 600
SPEEDS = ['0.8', '1', '1.2', '1.5', '1.8', '2']  # as the button shows them (PlaybackService.SPEEDS)
SIZE = 24  # the drawable's viewport
WIDTH = 22  # the most the text may take of it
HEIGHT = 11  # the digits' height, at most
TIMES = 0.7  # the ×, by the digits

DRAWABLES = Path(__file__).parent.parent / 'app/src/main/res/drawable'


def draw(font, text, pen, scale=1.0, dx=0.0, dy=0.0):
    """the text, and a smaller ×, onto the pen: in font units scaled, flipped (y down) and moved, when given"""
    glyphs = font.getGlyphSet()
    cmap = font.getBestCmap()
    x = 0
    for char in text + '×':
        name = cmap[ord(char)]
        size = TIMES if char == '×' else 1
        glyphs[name].draw(TransformPen(pen, (size * scale, 0, 0, -size * scale, x * scale + dx, dy)))
        x += glyphs[name].width * size


def bounds(font, text):
    pen = BoundsPen(font.getGlyphSet())
    draw(font, text, pen)
    return pen.bounds[0], pen.bounds[2]


def drawable(font, text, scale):
    x0, x1 = bounds(font, text)
    cap = font['OS/2'].sCapHeight
    # centered: across by the text's bounds, down by the digits' height
    path = SVGPathPen(font.getGlyphSet(), ntos=lambda n: f'{n:.2f}'.rstrip('0').rstrip('.'))
    draw(font, text, path, scale, (SIZE - (x1 - x0) * scale) / 2 - x0 * scale, (SIZE + cap * scale) / 2)
    return f'''<?xml version="1.0" encoding="utf-8"?>
<!-- the speed, {text}×, for the player's speed button: written by tools/speed_icons.py -->
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="24dp" android:height="24dp" android:viewportWidth="{SIZE}" android:viewportHeight="{SIZE}">
    <path android:fillColor="#FFFFFFFF" android:pathData="{path.getCommands()}" />
</vector>
'''


def main():
    font = instantiateVariableFont(TTFont(BytesIO(urllib.request.urlopen(FONT).read())), {'wght': WEIGHT})
    # one size for all, so the speed doesn't change size as it changes: the widest fits
    widest = max(x1 - x0 for x0, x1 in (bounds(font, text) for text in SPEEDS))
    scale = min(HEIGHT / font['OS/2'].sCapHeight, WIDTH / widest)
    for text in SPEEDS:
        (DRAWABLES / f'ic_speed_{text.replace(".", "_")}.xml').write_text(drawable(font, text, scale), encoding='utf8')
        print(text)


if __name__ == '__main__':
    main()
