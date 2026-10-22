import io
import unittest
import xml.etree.ElementTree as ET
from datetime import timezone
from unittest.mock import patch

from podtuber.linked_feed import EpisodeParser, LinkedPodcastParser, get_parsers, matches_title


class LinkedPodcastParserTest(unittest.TestCase):
    @patch('podtuber.linked_feed.urllib.request.urlopen')
    def test_filters_and_splits_episodes_by_title(self, urlopen):
        urlopen.return_value = io.BytesIO('''
            <rss><channel>
                <title>Test feed</title>
                <item><title>הלכות שבת</title></item>
                <item><title>שיעור כללי</title></item>
                <item><title>Can a Jew become a &#x5D2;&#x5E8;?</title></item>
                <item><title>שיעור באידיש</title></item>
            </channel></rss>
        '''.encode())

        parsers = get_parsers('https://example.com/feed.xml', 'הרב אשר וייס', 'אוצר התורה',
                              title_exclude='אידיש|יידיש|Yiddish', title_language='he',
                              series=[{'name': 'שבת', 'pattern': 'שבת'}, {'name': 'כללי'}])

        self.assertEqual(['שבת - הרב אשר וייס', 'כללי - הרב אשר וייס'],
                         [parser.get_name() for parser in parsers])
        self.assertEqual([['הלכות שבת'], ['שיעור כללי']],
                         [[episode.get_title() for episode in parser.get_episodes()] for parser in parsers])

    def test_hebrew_language_uses_first_letter_not_any_hebrew_term(self):
        self.assertTrue(matches_title('שיעור בעברית | Rav Asher Weiss', language='he'))
        self.assertFalse(matches_title('Can a Jew become a גר?', language='he'))

    def test_series_name_has_stable_distinct_feed_id(self):
        channel = ET.fromstring('<channel><title>Test</title></channel>')
        first = LinkedPodcastParser('https://example.com/feed.xml', channel, 'הרב אשר וייס', 'מקור',
                                    name='שבת')
        second = LinkedPodcastParser('https://example.com/feed.xml', channel, 'הרב אשר וייס', 'מקור',
                                     name='מועדים')

        self.assertNotEqual(first.get_feed_id(), second.get_feed_id())
        self.assertEqual('שבת - הרב אשר וייס', first.get_name())

    def test_assumes_utc_when_feed_date_has_unknown_timezone(self):
        item = ET.fromstring('<item><pubDate>Mon, 19 Oct 2026 18:43:22 -0000</pubDate></item>')

        published = EpisodeParser(item, 'הרב אשר וייס').get_publication_date()

        self.assertEqual(timezone.utc, published.tzinfo)


if __name__ == '__main__':
    unittest.main()
