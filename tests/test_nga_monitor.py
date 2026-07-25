from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from stock_assist.data_sources.nga import clear_cookie, load_cookie, parse_board_topics, save_cookie
from stock_assist.workflows.nga_monitor import _title_sentiment


FIXTURE = """
<table>
  <tr>
    <td><a href="/read.php?tid=47186827">4</a>Winter昼夜 5分钟前</td>
    <td><a href="https://bbs.nga.cn/read.php?tid=47186827&amp;page=e">刚才</a></td>
    <td><a href="https://bbs.nga.cn/read.php?tid=47186827">存储半导体集体大跌！</a></td>
  </tr>
  <tr>
    <td><a href="/read.php?tid=44279886">157722</a>A1luren</td>
    <td><a href="https://bbs.nga.cn/read.php?tid=44279886">超短线交流贴</a></td>
    <td><a href="https://bbs.nga.cn/read.php?tid=44279886&amp;page=7887">7887</a></td>
  </tr>
</table>
"""


class NGAMonitorTests(unittest.TestCase):
    def test_parser_extracts_title_and_reply_count_without_page_numbers(self) -> None:
        topics = parse_board_topics(FIXTURE)
        self.assertEqual(2, len(topics))
        self.assertEqual("47186827", topics[0].thread_id)
        self.assertEqual("存储半导体集体大跌！", topics[0].title)
        self.assertEqual(4, topics[0].replies)
        self.assertEqual(157722, topics[1].replies)

    def test_cookie_store_is_local_file_and_never_echoed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nga_cookie.txt"
            save_cookie("ngaPassportUid=1; ngaPassportCid=secret", path)
            self.assertEqual("ngaPassportUid=1; ngaPassportCid=secret", load_cookie(path))
            self.assertTrue(clear_cookie(path))
            self.assertFalse(path.exists())

    def test_title_sentiment_is_a_proxy(self) -> None:
        self.assertEqual("bearish", _title_sentiment("半导体大跌，被套了"))
        self.assertEqual("bullish", _title_sentiment("科创50反弹机会"))
        self.assertEqual("neutral", _title_sentiment("今日市场讨论"))


if __name__ == "__main__":
    unittest.main()
