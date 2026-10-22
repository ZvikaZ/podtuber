import unittest
from types import SimpleNamespace

from podtuber.index_page import TEXTS, rav_cards, rav_summary


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


if __name__ == '__main__':
    unittest.main()
