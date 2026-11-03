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

    @patch('podtuber.linked_feed.urllib.request.urlopen')
    def test_merges_feeds_skipping_copies_of_the_same_file(self, urlopen):
        def item(title, date, size, duration):
            return (f'<item><title>{title}</title><pubDate>{date}</pubDate><enclosure url="https://a/{size}.mp3" '
                    f'length="{size}"/><itunes:duration>{duration}</itunes:duration></item>')
        feed = '<rss xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"><channel><title>{}</title>{}</channel></rss>'
        urlopen.side_effect = [
            io.BytesIO(feed.format('First', item('הכנה לשבועות', 'Mon, 03 Jun 2024 10:00:00 +0000', 100, '24:07')).encode()),
            io.BytesIO(feed.format('Second', ''.join([
                item('שיחת הכנה לחג השבועות (עברית)', 'Wed, 24 May 2023 10:00:00 +0000', 100, '24:07'),
                item('מצוות הלוואה (עברית)', 'Fri, 13 Feb 2026 10:00:00 +0000', 200, '10:00'),
                item('The Mitzvah to Lend Money (EN)', 'Fri, 13 Feb 2026 11:00:00 +0000', 300, '12:00'),
            ])).encode()),
        ]

        parsers = get_parsers(['https://example.com/first.xml', 'https://example.com/second.xml'],
                              'הרב אשר וייס', 'מקור', title_language='he', series=[{'name': 'כללי'}])

        self.assertEqual(1, len(parsers))
        self.assertEqual(['מצוות הלוואה (עברית)', 'הכנה לשבועות'],
                         [episode.get_title() for episode in parsers[0].get_episodes()])
        self.assertEqual(LinkedPodcastParser('https://example.com/first.xml', ET.fromstring('<channel/>'),
                                             'הרב אשר וייס', 'מקור', name='כללי').get_feed_id(),
                         parsers[0].get_feed_id())  # the first feed's, as before the second was added

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
