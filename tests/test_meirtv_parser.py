import unittest
from unittest.mock import patch

from podtuber.meirtv_parser import get_series_parsers


class MeirTvParserTest(unittest.TestCase):
    @patch('podtuber.meirtv_parser.prefetch')
    @patch('podtuber.meirtv_parser.SITE')
    def test_does_not_repeat_an_own_series_lesson_in_a_mixed_series(self, site, _prefetch):
        lessons = [
            {'id': 1, 'date_gmt': '2026-01-01T00:00:00', 'link': 'lesson-1',
             'title': {'rendered': 'באר הגולה'}, 'shiurim-series': [10, 20], 'rabbis': [30]},
            {'id': 2, 'date_gmt': '2026-01-02T00:00:00', 'link': 'lesson-2',
             'title': {'rendered': 'נושא אחר'}, 'shiurim-series': [20], 'rabbis': [30]},
        ]
        site.get_term.return_value = {'id': 30, 'link': 'rabbi'}
        site.get_all.return_value = lessons
        site.get_terms.side_effect = [
            [{'id': 10, 'count': 1, 'name': 'באר הגולה', 'link': 'series-10'},
             {'id': 20, 'count': 10, 'name': 'סדרה מעורבת', 'link': 'series-20'}],
            [{'id': 30, 'name': 'הרב אורי שרקי'}],
        ]
        site.find_audio.side_effect = lambda _section, found, _finder: [
            lesson.update(audio='https://example.com/lesson.mp3') for lesson in found
        ]

        with patch('podtuber.meirtv_parser.lesson_audio_url',
                   side_effect=lambda lesson: lesson.get('audio')):
            parsers = get_series_parsers('https://meirtv.com/rabbis/example/', topics=('באר הגולה',))

        self.assertEqual(['meirtv-10', 'meirtv-rabbi-30-other'], [parser.feed_id for parser in parsers])
        self.assertEqual([[1], [2]], [[lesson.order for lesson in parser.lessons] for parser in parsers])

    @patch('podtuber.meirtv_parser.prefetch')
    @patch('podtuber.meirtv_parser.SITE')
    def test_splits_a_series_by_the_words_its_titles_name(self, site, _prefetch):
        titles = {1: 'האם מותר לטלטל בשבת?', 2: 'מה מברכים על "קרמבו"?', 3: 'דין מוקצה', 4: 'מהי אמונה?'}
        lessons = [{'id': id, 'date_gmt': f'2026-01-0{id}T00:00:00', 'link': f'lesson-{id}',
                    'title': {'rendered': title}, 'shiurim-series': [10], 'rabbis': [30]}
                   for id, title in titles.items()]
        site.get_term.return_value = {'id': 30, 'link': 'rabbi'}
        site.get_all.return_value = lessons
        site.get_terms.side_effect = [
            [{'id': 10, 'count': 4, 'name': 'שאלות ותשובות -', 'link': 'series-10'}],
            [{'id': 30, 'name': 'הרב שלמה אבינר'}],
        ]
        site.find_audio.side_effect = lambda _section, found, _finder: [
            lesson.update(audio='https://example.com/lesson.mp3') for lesson in found
        ]
        split = {'series': 'שאלות ותשובות', 'parts': [{'name': 'שבת', 'words': ['שבת', 'מוקצה']},
                                                       {'name': 'ברכות', 'words': ['ברכה', 'מברכים']},
                                                       {'name': 'שונות'}]}

        with patch('podtuber.meirtv_parser.lesson_audio_url',
                   side_effect=lambda lesson: lesson.get('audio')):
            parsers = get_series_parsers('https://meirtv.com/rabbis/example/', splits=[split])

        self.assertEqual(['שאלות ותשובות - שבת', 'שאלות ותשובות - ברכות', 'שאלות ותשובות - שונות'],
                         [parser.name for parser in parsers])
        self.assertEqual([[1, 3], [2], [4]], [sorted(lesson.order for lesson in parser.lessons) for parser in parsers])
        self.assertTrue(all(parser.feed_id.startswith('meirtv-10-part-') for parser in parsers))


if __name__ == '__main__':
    unittest.main()
