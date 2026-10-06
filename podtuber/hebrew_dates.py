import re

from pyluach.dates import HebrewDate

LETTERS = dict(zip('אבגדהוזחטיכלמנסעפצקרשת',
                   [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 200, 300, 400]))
MONTHS = {'ניסן': 1, 'אייר': 2, 'סיון': 3, 'סיוון': 3, 'תמוז': 4, 'אב': 5, 'מנחם אב': 5, 'אלול': 6, 'תשרי': 7,
          'חשון': 8, 'חשוון': 8, 'מרחשון': 8, 'מרחשוון': 8, 'כסלו': 9, 'כסליו': 9, 'טבת': 10, 'שבט': 11}


def gematria(letters):
    return sum(LETTERS.get(letter, 0) for letter in letters)


def parse_hebrew_date(text):
    """
    A Hebrew date as written on the sites, such as 'ל שבט התשפג', 'טז באדר תשעז', 'כד באדר ב תשעד' or
    'ה אדר-א התשפד', as a datetime.date; None when it isn't one.
    """
    text = re.sub(r'["\'׳״]', '', text.replace('-', ' ')).strip()
    match = re.fullmatch(r'(\S{1,2})\s+ב?(.+?)\s+ה?(ת\S{2,3})', text)
    if not match:
        return None
    day, month_name, year = gematria(match.group(1)), match.group(2).strip(), 5000 + gematria(match.group(3))
    if month_name.startswith('אדר'):
        month = 13 if month_name.replace(' ', '') == 'אדרב' and _is_leap(year) else 12
    else:
        month = MONTHS.get(month_name)
    if not month or not 1 <= day <= 30:
        return None
    try:
        return HebrewDate(year, month, day).to_pydate()
    except ValueError:
        return None


def _is_leap(year):
    try:  # only leap years have month 13, Adar II
        HebrewDate(year, 13, 1)
        return True
    except ValueError:
        return False
