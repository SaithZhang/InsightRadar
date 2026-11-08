"""Synthetic single-file boundary tests; no live account, browser or network."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("zsxq_pdf", Path(__file__).parents[1] / "scripts/zsxq_pdf.py")
z = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(z)
URL = "https://wx.zsxq.com/group/123/topic/456"
NAME = "测试 单份纪要.pdf"
DATA = b"%PDF-1.4\nsynthetic verification bytes\n"
META = {"file_id": "789", "name": NAME, "size": len(DATA), "hash": hashlib.sha256(DATA).hexdigest()}


def payload(files=None):
    return {"success": True, "topic": {"topic_id": "456", "group": {"group_id": "123"},
                                      "files": [META] if files is None else files}}


class ZsxqPdfTests(unittest.TestCase):
    def failure(self, code, fn, *args):
        with self.assertRaises(z.Failure) as caught:
            fn(*args)
        self.assertEqual(caught.exception.code, code)

    def test_inputs_accept_exact_official_link_only(self):
        self.assertEqual(z.inputs(URL + "/", NAME), (URL, "123", "456"))
        for url in [URL + "?api_key=synthetic", URL.replace("https:", "http:"),
                    URL.replace("wx.zsxq.com", "wx.zsxq.com.evil.test"), URL + "/other", "file:///tmp/x"]:
            self.failure("INVALID_URL", z.inputs, url, NAME)

    def test_single_pdf_name_rejects_paths_patterns_and_controls(self):
        for name in ["../x.pdf", "*.pdf", "x.pdf\ny.pdf", "x.mp3", "", " x.pdf", "x\\y.pdf"]:
            self.failure("INVALID_FILENAME", z.inputs, URL, name)

    def test_metadata_exact_identity_and_unique_name(self):
        self.assertEqual(z.metadata(payload(), "123", "456", NAME), META)
        self.failure("TOPIC_MISMATCH", z.metadata, payload(), "999", "456", NAME)
        self.failure("ATTACHMENT_NOT_UNIQUE", z.metadata, payload([META, META]), "123", "456", NAME)
        self.failure("ATTACHMENT_NOT_UNIQUE", z.metadata, payload(), "123", "456", "另一份.pdf")

    def test_missing_hash_and_oversized_file_fail_before_browser(self):
        for f in [{**META, "hash": ""}, {**META, "size": z.MAX_BYTES + 1}]:
            self.failure("UNVERIFIABLE_ATTACHMENT", z.metadata, payload([f]), "123", "456", NAME)

    def test_oauth_failure_does_not_echo_raw_response(self):
        result = subprocess.CompletedProcess([], 1, "", "authentication failed (HTTP 401) synthetic-sensitive")
        with patch.object(z.subprocess, "run", return_value=result):
            with self.assertRaises(z.Failure) as caught:
                z.load_metadata("123", "456", NAME)
        self.assertEqual(caught.exception.code, "CLI_LOGIN_REQUIRED")
        self.assertNotIn("synthetic-sensitive", str(caught.exception))

    def test_chrome_disabled_setting_is_specific_and_no_setting_mutation(self):
        result = subprocess.CompletedProcess([], 1, "", "JavaScript 功能已关闭 (12)")
        with patch.object(z.subprocess, "run", return_value=result) as run:
            self.failure("BROWSER_SCRIPT_DISABLED", z.chrome, URL, "7", "read-only")
        self.assertEqual(run.call_count, 1)

    def test_login_state_stops_before_click(self):
        with patch.object(z, "chrome", return_value='{"state":"LOGIN_REQUIRED"}'):
            self.failure("LOGIN_REQUIRED", z.page, URL, "7", NAME)

    def test_exact_download_names_exclude_other_attachment_and_incomplete(self):
        with tempfile.TemporaryDirectory() as folder:
            d = Path(folder)
            for name in [NAME, NAME[:-4] + " (2).pdf", NAME + ".crdownload", "其他纪要.pdf"]:
                (d / name).write_bytes(DATA)
            self.assertEqual(len(z.snapshot(d, NAME)), 2)

    def test_old_manual_file_cannot_satisfy_new_download(self):
        with tempfile.TemporaryDirectory() as folder:
            d = Path(folder); (d / NAME).write_bytes(DATA)
            before = z.snapshot(d, NAME)
            with patch.object(z.time, "sleep"):
                self.failure("DOWNLOAD_TIMEOUT", z.wait_download, d, NAME, before, META, .01)

    def test_new_completed_file_requires_provider_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            d = Path(folder); (d / NAME).write_bytes(DATA)
            before = z.snapshot(d, NAME)
            new = d / (NAME[:-4] + " (1).pdf"); new.write_bytes(DATA)
            with patch.object(z.time, "sleep"):
                self.assertEqual(z.wait_download(d, NAME, before, META, 1), new)
            new.write_bytes(DATA.replace(b"verification", b"differentxxx"))
            self.failure("FILE_MISMATCH", z.verified_bytes, new, META)

    def test_cache_rerun_does_not_click_download(self):
        with tempfile.TemporaryDirectory() as folder:
            d = Path(folder); out = d / "output"
            key = hashlib.sha256((URL + "\n" + NAME).encode()).hexdigest()[:20]
            (out / key).mkdir(parents=True); (out / key / "source.pdf").write_bytes(DATA)
            parsed = {"page_count": 1, "pages": [{"page": 1, "text": "synthetic", "has_images": False}]}
            with patch.object(z, "OUTPUT", out), patch.object(z.sys, "platform", "darwin"), \
                    patch.object(z, "load_metadata", return_value=META), patch.object(z, "chrome", return_value="7"), \
                    patch.object(z, "ready", return_value="FILE_READY"), patch.object(z, "page") as page, \
                    patch.object(z, "extract", return_value=parsed):
                result = z.run(URL, NAME, d)
            self.assertTrue(result["cached"])
            page.assert_not_called()
            self.assertEqual((out / key / "text.txt").stat().st_mode & 0o777, 0o600)

    def test_corrupt_cache_never_silently_redownloads(self):
        with tempfile.TemporaryDirectory() as folder:
            d = Path(folder); out = d / "output"
            key = hashlib.sha256((URL + "\n" + NAME).encode()).hexdigest()[:20]
            (out / key).mkdir(parents=True); (out / key / "source.pdf").write_bytes(b"wrong")
            with patch.object(z, "OUTPUT", out), patch.object(z.sys, "platform", "darwin"), \
                    patch.object(z, "load_metadata", return_value=META), patch.object(z, "chrome", return_value="7"), \
                    patch.object(z, "ready", return_value="FILE_READY"), patch.object(z, "page") as page:
                self.failure("FILE_MISMATCH", z.run, URL, NAME, d)
            page.assert_not_called()

    def test_dom_does_not_download_other_file_or_while_logged_out(self):
        # Minimal synthetic DOM: exercise the browser program's safety decisions.
        fixture = r'''
const mode=process.argv[1];
function el(text,parent=null){return {textContent:text,children:[],parentElement:parent,
 getClientRects:()=>[1],click:()=>{throw Error('unexpected click')},
 contains:function(other){while(other){if(other===this)return true;other=other.parentElement;}return false;}};}
const body=el('body'); const panel=el('panel',body); const file=el('another.pdf',panel);
const detail=el('文件详情',panel);const download=el('下载文件',panel);
const wanted=el('测试 单份纪要.pdf',body);
const elements=mode==='login'?[el('扫码登录')]:[file,detail,download,wanted];
global.location={href:'https://wx.zsxq.com/group/123/topic/456'};
global.document={body,readyState:'complete',querySelectorAll:()=>elements};
'''
        for mode, expected in [("login", "LOGIN_REQUIRED"), ("other", "OTHER_FILE_DIALOG")]:
            code = fixture + "console.log(" + z.PAGE_JS + "(" + ",".join(map(json.dumps, [URL, NAME, "download"])) + "));"
            result = subprocess.run(["node", "-e", code, mode], text=True, capture_output=True, check=True)
            self.assertEqual(json.loads(result.stdout)["state"], expected)


if __name__ == "__main__":
    unittest.main()
