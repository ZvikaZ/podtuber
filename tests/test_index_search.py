"""The index page's search, as the browser runs it: its script's search functions, run by Node."""
import json
import shutil
import subprocess
import unittest

from podtuber.index_page import SCRIPT, rav_options

START, END = '// searching:', '// the text, with the words searched for marked'


def run_search_script(test):
    """runs the page's search functions, then test (JavaScript that ends with a value), and returns that value"""
    search = SCRIPT[SCRIPT.index(START):SCRIPT.index(END)]
    program = ("const checkboxes = {}; const $ = id => checkboxes[id] = checkboxes[id] || {checked: false};\n"
               f"{search}\nconsole.log(JSON.stringify((() => {{ {test} }})()));")
    result = subprocess.run(['node', '-e', program], capture_output=True, text=True, encoding='utf8', check=True)
    return json.loads(result.stdout)


@unittest.skipUnless(shutil.which('node'), 'needs Node')
class SearchTest(unittest.TestCase):
    def test_a_space_typed_before_the_next_word_is_kept(self):
        # the address keeps the query trimmed; the box it's put back in mustn't lose the space typed after a word
        self.assertEqual('שבת ', run_search_script("return boxValue('שבת ', 'שבת');"))
        self.assertEqual('שבת אבינר', run_search_script("return boxValue('שבת', 'שבת אבינר');"))  # Back, say
        self.assertEqual('', run_search_script("return boxValue('שבת', '');"))

    def test_every_word_must_be_found(self):
        self.assertEqual([True, True, False], run_search_script(
            "const matches = matcher('הלכות שבת');"
            "return ['הלכות שבת', 'שבת: הלכות מוקצה', 'הלכות פסח'].map(matches);"))

    def test_a_lessons_words_may_be_in_its_series_or_rav(self):
        self.assertEqual([True, True, False], run_search_script(
            "const lesson = [0, 'האם מותר לטלטל?', '']; const series = ['f', 'שאלות ותשובות - שבת', 'הרב שלמה אבינר'];"
            "return ['אבינר טלטל', 'שבת לטלטל', 'אבינר פסח'].map(query => matcher(query)(lessonText(lesson, series)));"))

    def test_lessons_can_be_searched_for_of_one_rav(self):
        self.assertEqual([True, False, True], run_search_script(
            "const lesson = [0, 'הלכות שבת', '']; const aviner = ['a', 'שו\"ת', 'הרב שלמה אבינר'];"
            "const sherki = ['b', 'שיעורים', 'הרב אורי שרקי']; const matches = matcher('שבת');"
            "return [lessonFound(lesson, aviner, matches, 'הרב שלמה אבינר'),"
            "        lessonFound(lesson, sherki, matches, 'הרב שלמה אבינר'), lessonFound(lesson, sherki, matches, '')];"))


@unittest.skipUnless(shutil.which('node'), 'needs Node')
class ShareTest(unittest.TestCase):
    def share(self, app):
        """what shareLink('feed/3', title) does: in the app (app: its share sheet, or None), or a browser's"""
        start = SCRIPT.index('function shareLink(')
        function = SCRIPT[start:SCRIPT.index('\n}\n', start) + 2]
        program = ("const done = []; const location = {pathname: '/podtuber/', origin: 'https://zvikaz.github.io'};"
                   "const navigator = {share: data => { done.push(['navigator', data]); return Promise.resolve(); }};"
                   "const copy = text => done.push(['copy', text]); const TEXTS = {};"
                   f"const app = {app or 'undefined'};\n{function}\n"
                   "shareLink('feed/3', 'שיעור'); console.log(JSON.stringify(done));")
        result = subprocess.run(['node', '-e', program], capture_output=True, text=True, encoding='utf8', check=True)
        return json.loads(result.stdout)

    def test_the_app_shares_by_its_share_sheet(self):
        # its WebView has no navigator.share: a lesson's "share" only copied its link
        self.assertEqual([['app', 'שיעור', 'https://zvikaz.github.io/podtuber/#feed/3']],
                         self.share("{share: (title, url) => done.push(['app', title, url])}"))

    def test_a_browser_shares_by_its_own(self):
        self.assertEqual([['navigator', {'title': 'שיעור', 'url': 'https://zvikaz.github.io/podtuber/#feed/3'}]],
                         self.share(None))


@unittest.skipUnless(shutil.which('node'), 'needs Node')
class AppLinkTest(unittest.TestCase):
    def app_link(self, user_agent):
        start = SCRIPT.index('function appLink(')
        function = SCRIPT[start:SCRIPT.index('\n}\n', start) + 2]
        program = f"{function}\nconsole.log(appLink('pcast://zvikaz.github.io/podtuber/a.rss', {json.dumps(user_agent)}));"
        return subprocess.run(['node', '-e', program], capture_output=True, text=True, check=True).stdout.strip()

    def test_apples_devices_open_their_podcasts_app_by_its_own_scheme(self):
        # the Mac's Podcasts app opens pcast:// links, but fails to add their feed
        for user_agent in ['Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15',
                           'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15']:
            self.assertEqual('podcast://zvikaz.github.io/podtuber/a.rss', self.app_link(user_agent))

    def run_script(self, test):
        functions = ''
        for name in ('isMac', 'feedAddress'):
            start = SCRIPT.index(f'function {name}(')
            functions += SCRIPT[start:SCRIPT.index('\n}\n', start) + 2]
        program = f"{functions}\nconsole.log(JSON.stringify((() => {{ {test} }})()));"
        return json.loads(subprocess.run(['node', '-e', program], capture_output=True, text=True, check=True).stdout)

    def test_a_mac_copies_the_feeds_address_to_paste_in_its_app(self):
        # the Mac's Podcasts app, opened by podcast://, leaves its address box empty
        self.assertEqual([True, False, False], self.run_script(
            "return [isMac('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)', 0),"
            "        isMac('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)', 5),"  # an iPad, asking for a Mac's page
            "        isMac('Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)', 5)];"))
        self.assertEqual('https://zvikaz.github.io/podtuber/a.rss',
                         self.run_script("return feedAddress('podcast://zvikaz.github.io/podtuber/a.rss');"))

    def test_other_devices_open_other_apps(self):
        self.assertEqual('pcast://zvikaz.github.io/podtuber/a.rss',
                         self.app_link('Mozilla/5.0 (Linux; Android 15; Pixel 8) AppleWebKit/537.36 Chrome/130.0'))


class RavFilterTest(unittest.TestCase):
    def test_the_ravs_to_choose_from_are_by_surname(self):
        ravs = [('הרב אורי שרקי', 3, 10, None), ('הרב שלמה אבינר', 2, 5, None), ('הרב "x" <y>', 1, 1, None)]
        self.assertEqual('<option value="הרב &quot;x&quot; &lt;y&gt;">הרב &quot;x&quot; &lt;y&gt;</option>'
                         '<option value="הרב שלמה אבינר">הרב שלמה אבינר</option>'
                         '<option value="הרב אורי שרקי">הרב אורי שרקי</option>', rav_options(ravs))


if __name__ == '__main__':
    unittest.main()
