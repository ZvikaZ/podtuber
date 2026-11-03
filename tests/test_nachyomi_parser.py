import unittest
from unittest.mock import patch

from podtuber import nachyomi_parser

SCRIPT = ('var x=1,s_=[[{book:"\\u05D9\\u05D4\\u05D5\\u05E9\\u05E2",chapter:"\\u05D0"},'  # יהושע א
          '{book:"\\u05D9\\u05D4\\u05D5\\u05E9\\u05E2",chapter:"\\u05D1"}],'  # יהושע ב
          '[{book:"\\u05D9\\u05D4\\u05D5\\u05E9\\u05E2",chapter:"\\u05D9"},'  # יהושע י
          '{book:"\\u05E8\\u05D5\\u05EA",chapter:"\\u05D0"}],'  # רות א
          '[{book:"\\u05E8\\u05D5\\u05EA",chapter:"\\u05D0",subChapter:[{letter:"\\u05D0",index:0}]}]],y=2;')


class NachYomiParserTest(unittest.TestCase):
    def test_schedule_chapters_are_read_from_the_script(self):
        self.assertEqual([('יהושע', 'א'), ('יהושע', 'ב'), ('יהושע', 'י'), ('רות', 'א'), ('רות', 'א')],
                         nachyomi_parser.schedule_chapters(SCRIPT))

    @patch('podtuber.nachyomi_parser.prefetch')
    @patch('podtuber.nachyomi_parser.read_script', return_value=SCRIPT)
    def test_a_podcast_per_book_with_its_chapters_in_order(self, _, __):
        parsers = nachyomi_parser.get_series_parsers('https://nachyomi.netlify.app/lessons', 'הרב מוטי פרנקו')

        self.assertEqual(['יהושע - הרב מוטי פרנקו', 'רות - הרב מוטי פרנקו'], [p.get_name() for p in parsers])
        self.assertEqual(['יהושע פרק א', 'יהושע פרק ב', 'יהושע פרק י'],
                         [lesson.title for lesson in parsers[0].lessons])
        self.assertEqual(1, len(parsers[1].lessons))  # a chapter learnt over several days is one lesson
        self.assertEqual('https://nachyomiapp.s3.eu-north-1.amazonaws.com/lessons/'
                         '%D7%99%D7%94%D7%95%D7%A9%D7%A2+%D7%A4%D7%A8%D7%A7+%D7%90.mp4',
                         parsers[0].lessons[0].audio_url)
        self.assertNotEqual(parsers[0].get_feed_id(), parsers[1].get_feed_id())
        # the files' dates are of their upload, not of the lessons: no years, nor a description of the date
        self.assertFalse(parsers[0].dated)
        self.assertEqual([1, 2], [parser.order for parser in parsers])  # the Bible's order, as the schedule's
        self.assertEqual('', next(parsers[0].get_episodes()).get_summary())


if __name__ == '__main__':
    unittest.main()
