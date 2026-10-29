import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from podtuber.index_page import PAGE, TEXTS, about, new_lessons, rav_cards, rav_summary, search_entry


class RabbiSummaryTest(unittest.TestCase):
    def test_counts_series_and_lessons(self):
        podcasts = [
            {'rav': 'הרב א', 'rav_image': 'https://example.com/a.jpg',
             'podcast': SimpleNamespace(episodes=[1, 2])},
            {'rav': 'הרב א', 'rav_image': 'https://example.com/a.jpg',
             'podcast': SimpleNamespace(episodes=[3])},
            {'rav': 'הרב ב', 'podcast': SimpleNamespace(episodes=[1, 2, 3, 4])},
        ]

        summary = rav_summary(podcasts, 'https://example.com/')

        self.assertEqual([('הרב א', 2, 3, 'a.jpg'), ('הרב ב', 1, 4, None)], summary)

    def test_cards_expose_sort_values(self):
        cards = rav_cards([('הרב א', 2, 3, 'a.jpg')], TEXTS['he'])

        self.assertIn('data-name="הרב א"', cards)
        self.assertIn('data-series="2"', cards)
        self.assertIn('data-lessons="3"', cards)
        self.assertIn('2 סדרות · 3 שיעורים', cards)


class LessonOriginTest(unittest.TestCase):
    def test_a_lessons_line_names_the_site_its_from(self):
        self.assertEqual('הלכות שבת · הרב א · ערוץ מאיר', about('הלכות שבת', 'הרב א', 'ערוץ מאיר'))
        self.assertEqual('הלכות שבת · הרב א', about('הלכות שבת', 'הרב א', ''))

    def test_the_newest_lessons_name_the_site_theyre_from(self):
        episode = SimpleNamespace(publication_date=datetime(2026, 10, 1, tzinfo=timezone.utc), original_title='שיעור',
                                  title='', media=SimpleNamespace(url='https://x/1.mp3'))
        line = new_lessons([(episode, 1, 'f', about('הלכות שבת', 'הרב א', 'ערוץ מאיר'))], TEXTS['he'])
        self.assertIn('<div class="meta">הלכות שבת · הרב א · ערוץ מאיר · ', line)

    def test_the_newest_lessons_can_be_shared(self):
        episode = SimpleNamespace(publication_date=datetime(2026, 10, 1, tzinfo=timezone.utc), original_title='שיעור "א"',
                                  title='', media=SimpleNamespace(url='https://x/1.mp3'))
        line = new_lessons([(episode, 7, 'feed-1', 'סדרה')], TEXTS['he'])
        self.assertIn('<button type="button" class="btn" data-share-lesson="feed-1/7" data-title="שיעור &quot;א&quot;">'
                      'שיתוף</button>', line)


class LessonDescriptionTest(unittest.TestCase):
    def episode(self, summary):
        return SimpleNamespace(publication_date=datetime(2026, 10, 1, tzinfo=timezone.utc), original_title='שו"ת',
                               title='', original_summary=summary, media=None)

    def test_all_of_a_description_is_searched(self):
        # a Kalner lesson's keywords, "תנועת נעם" last in them, past what the search index used to keep
        keywords = 'טז חשוון התשפז ' + 'תפילה על חברו והיענות, ' * 12 + 'תנועת נעם והבחירות'
        self.assertIn('תנועת נעם', search_entry(0, self.episode(keywords), 1, TEXTS['he'])[2])

    def test_addresses_in_a_description_arent_searched(self):
        summary = ("💻 לצפייה ביוטיוב: https://youtu.be/UgrL1phe9tE ראש מילין, אות ט': https://he.wikisource.org/wiki/x "
                   'לפניות: shiuryomi@beityehouda.co.il')
        self.assertEqual("💻 לצפייה ביוטיוב: ראש מילין, אות ט': לפניות:",
                         search_entry(0, self.episode(summary), 1, TEXTS['he'])[2])

    def test_long_addresses_in_a_description_wrap(self):
        # on a phone, a description's long addresses widened the page past the screen
        rule = PAGE[PAGE.index('  .description {'):PAGE.index('}', PAGE.index('  .description {'))]
        self.assertIn('overflow-wrap: anywhere', rule)
        self.assertIn('width: 100%', rule)


if __name__ == '__main__':
    unittest.main()
