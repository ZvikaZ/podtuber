import unittest

from podtuber.lessons import strip_rav_name

WISHLITZKY = 'הרב אלישע וישליצקי'


class StripRavNameTest(unittest.TestCase):
    def test_the_rav_named_after_a_series(self):
        self.assertEqual('כוזרי [תשע"ז]', strip_rav_name('כוזרי [תשע"ז] - הרב קלנר', 'הרב יוסף קלנר'))
        self.assertEqual('לחנוכה', strip_rav_name('הרב אלישע וישליצקי זצ"ל - לחנוכה', WISHLITZKY))

    def test_the_ravs_lessons_named_before_it(self):
        # Meir TV's series of Rav Wishlitzky's were named "שיעורי לשבועות", "שיעורי - ט"ו בשבט"
        self.assertEqual('לשבועות', strip_rav_name('שיעורי הרב אלישע וישליצקי זצ"ל לשבועות', WISHLITZKY))
        self.assertEqual('ט"ו בשבט', strip_rav_name('שיעורי הרב אלישע וישליצקי זצ"ל - ט"ו בשבט', WISHLITZKY))

    def test_the_rav_by_his_first_name(self):
        self.assertEqual('פורים', strip_rav_name('הרב אלישע פורים', WISHLITZKY, series=True))
        self.assertEqual('הרב אלישע', strip_rav_name('הרב אלישע', WISHLITZKY, series=True))  # nothing but that: kept
        # a lesson's title may name another rav of his first name
        self.assertEqual('הרב יוסף קאפח על הרמב"ם', strip_rav_name('הרב יוסף קאפח על הרמב"ם', 'הרב יוסף קלנר'))

    def test_another_rav_named_is_kept(self):
        self.assertEqual('דברי הרב צבי יהודה', strip_rav_name('דברי הרב צבי יהודה', WISHLITZKY))


if __name__ == '__main__':
    unittest.main()
