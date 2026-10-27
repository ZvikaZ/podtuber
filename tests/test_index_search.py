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


class RavFilterTest(unittest.TestCase):
    def test_the_ravs_to_choose_from_are_by_surname(self):
        ravs = [('הרב אורי שרקי', 3, 10, None), ('הרב שלמה אבינר', 2, 5, None), ('הרב "x" <y>', 1, 1, None)]
        self.assertEqual('<option value="הרב &quot;x&quot; &lt;y&gt;">הרב &quot;x&quot; &lt;y&gt;</option>'
                         '<option value="הרב שלמה אבינר">הרב שלמה אבינר</option>'
                         '<option value="הרב אורי שרקי">הרב אורי שרקי</option>', rav_options(ravs))


if __name__ == '__main__':
    unittest.main()
