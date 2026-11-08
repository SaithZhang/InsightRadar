"""Cookie transport tests use synthetic credentials and responses only."""
from contextlib import closing, contextmanager
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

SPEC = importlib.util.spec_from_file_location("zsxq_pdf", Path(__file__).parents[1] / "scripts/zsxq_pdf.py")
z = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(z)
URL = "https://wx.zsxq.com/group/123/topic/456"
NAME = "synthetic.pdf"
DATA = b"%PDF-1.4\nsynthetic data\n"
META = {"file_id": "789", "name": NAME, "size": len(DATA), "hash": hashlib.sha256(DATA).hexdigest()}
COOKIE = {"name": z.COOKIE_NAME, "value": "synthetic-secret", "domain": ".zsxq.com", "path": "/",
          "secure": True, "expires": None}
FILE_URL = "https://files.zsxq.com/synthetic?signature=synthetic-private"


class Response:
    def __init__(self, body, status=200):
        self.status_code = status
        self.body = json.dumps(body).encode() if isinstance(body, dict) else body

    def iter_content(self, size):
        yield self.body


class CookieDownloadTests(unittest.TestCase):
    def expect_failure(self, code, fn, *args):
        with self.assertRaises(z.Failure) as caught:
            fn(*args)
        self.assertEqual(caught.exception.code, code)
        self.assertNotIn("synthetic-secret", str(caught.exception))
        self.assertNotIn("synthetic-private", str(caught.exception))

    def transport(self, responses):
        calls = []

        @contextmanager
        def get(url, seconds, cookies=None):
            calls.append((url, cookies))
            yield responses[len(calls) - 1]

        return get, calls

    def api(self, url=FILE_URL):
        return Response({"succeeded": True, "resp_data": {"download_url": url}})

    def test_cookie_scope_injection_and_expiry(self):
        self.assertEqual(z.validate_cookie(COOKIE), COOKIE["value"])
        for change in [{"domain": ".evil.test"}, {"name": "other"}, {"value": "secret\nCookie:x"},
                       {"value": "secret;other=x"}, {"value": ""}, {"path": "/other"}, {"secure": False}]:
            self.expect_failure("COOKIE_FILE_INVALID", z.validate_cookie, {**COOKIE, **change})
        for expiry in [0, time.time() - 1, "later", float("nan")]:
            self.expect_failure("COOKIE_LOGIN_REQUIRED", z.validate_cookie, {**COOKIE, "expires": expiry})

    def test_cookie_file_permissions_and_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "cookie.json"
            z.save(p, json.dumps(COOKIE).encode())
            self.assertEqual(z.load_cookie(p), COOKIE["value"])
            p.chmod(0o644)
            self.expect_failure("COOKIE_FILE_PERMISSIONS", z.load_cookie, p)
            link = Path(tmp) / "link"; link.symlink_to(p)
            self.expect_failure("COOKIE_FILE_INVALID", z.load_cookie, link)
            self.expect_failure("COOKIE_FILE_MISSING", z.load_cookie, Path(tmp) / "missing")

    def test_import_reads_only_target_cookie_without_database_copy(self):
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            from cryptography.hazmat.primitives.padding import PKCS7
        except ImportError:
            self.skipTest("optional zsxq-cookie dependency is not installed")
        password = b"synthetic-password"
        host = ".zsxq.com"
        key = hashlib.pbkdf2_hmac("sha1", password, b"saltysalt", 1003, 16)
        pad = PKCS7(128).padder()
        plain = hashlib.sha256(host.encode()).digest() + COOKIE["value"].encode()
        padded = pad.update(plain) + pad.finalize()
        cipher = Cipher(algorithms.AES(key), modes.CBC(b" " * 16)).encryptor()
        encrypted = b"v10" + cipher.update(padded) + cipher.finalize()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            dbpath = home / "Library/Application Support/Google/Chrome/Default/Cookies"
            dbpath.parent.mkdir(parents=True)
            with closing(sqlite3.connect(dbpath)) as db:
                db.execute("CREATE TABLE meta (key TEXT, value TEXT)")
                db.execute("INSERT INTO meta VALUES ('version','24')")
                db.execute("CREATE TABLE cookies (host_key TEXT,path TEXT,expires_utc INTEGER,encrypted_value BLOB,name TEXT,is_secure INTEGER)")
                db.executemany("INSERT INTO cookies VALUES (?,?,?,?,?,1)", [
                    (host, "/", 0, encrypted, z.COOKIE_NAME),
                    (".unrelated.test", "/", 0, b"must not decrypt", z.COOKIE_NAME),
                    (host, "/", 0, b"must not decrypt", "unrelated")])
                db.commit()
            before = dbpath.read_bytes()
            destination = home / "private/cookie.json"
            result = subprocess.CompletedProcess([], 0, password + b"\n", b"")
            with patch.object(z.Path, "home", return_value=home), patch.object(z.sys, "platform", "darwin"), \
                    patch.object(z.subprocess, "run", return_value=result):
                receipt = z.import_chrome_cookie(destination)
            self.assertEqual(z.load_cookie(destination), COOKIE["value"])
            self.assertNotIn(COOKIE["value"], json.dumps(receipt))
            self.assertEqual(dbpath.read_bytes(), before)
            self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
            self.assertEqual(list(home.rglob("Cookies")), [dbpath])

    def test_cookie_only_sent_to_metadata_api_not_file_cdn(self):
        get, calls = self.transport([self.api(), Response(DATA)])
        with patch.object(z, "http_get", get):
            self.assertEqual(z.download_cookie(META, COOKIE["value"], 60), DATA)
        self.assertEqual(calls[0], ("https://api.zsxq.com/v2/files/789/download_url", {z.COOKIE_NAME: COOKIE["value"]}))
        self.assertEqual(calls[1], (FILE_URL, None))

    def test_redirects_and_unexpected_hosts_never_receive_cookie_or_request(self):
        for url in ["http://files.zsxq.com/x", "https://files.zsxq.com.evil.test/x",
                    "https://user:pass@files.zsxq.com/x", "https://files.zsxq.com:443/x",
                    "https://files.zsxq.com/x#fragment", "https://evil.test/x"]:
            get, calls = self.transport([self.api(url)])
            with patch.object(z, "http_get", get):
                self.expect_failure("DOWNLOAD_API_CHANGED", z.download_cookie, META, COOKIE["value"], 60)
            self.assertEqual(len(calls), 1)
        get, calls = self.transport([Response(b"redirect", 302)])
        with patch.object(z, "http_get", get):
            self.expect_failure("DOWNLOAD_API_CHANGED", z.download_cookie, META, COOKIE["value"], 60)
        self.assertEqual(len(calls), 1)

    def test_revoked_cookie_permissions_and_rate_limits_do_not_retry(self):
        cases = [(Response({}, 401), "COOKIE_LOGIN_REQUIRED"),
                 (Response({"succeeded": False, "code": 401}), "COOKIE_LOGIN_REQUIRED"),
                 (Response({}, 403), "DOWNLOAD_ACCESS_DENIED"),
                 (Response({}, 429), "DOWNLOAD_ACCESS_DENIED"),
                 (Response({"succeeded": False, "code": 1059}), "DOWNLOAD_ACCESS_DENIED")]
        for response, code in cases:
            get, calls = self.transport([response])
            with patch.object(z, "http_get", get):
                self.expect_failure(code, z.download_cookie, META, COOKIE["value"], 60)
            self.assertEqual(len(calls), 1)

    def test_invalid_file_and_oversized_stream_fail(self):
        for data, code in [(b"%PDF-wrong", "FILE_MISMATCH"), (DATA + b"extra", "DOWNLOAD_TOO_LARGE")]:
            get, _ = self.transport([self.api(), Response(data)])
            with patch.object(z, "http_get", get):
                self.expect_failure(code, z.download_cookie, META, COOKIE["value"], 60)

    def test_network_failure_is_redacted_and_http_disables_redirects_netrc(self):
        session = MagicMock()
        session.get.side_effect = z.requests.Timeout(FILE_URL + " synthetic-secret")
        with patch.object(z.requests, "Session") as factory, \
                patch.object(z.requests.utils, "get_environ_proxies", return_value={}):
            factory.return_value.__enter__.return_value = session
            with self.assertRaises(z.Failure) as caught:
                with z.http_get(FILE_URL, 10):
                    pass
        self.assertEqual(caught.exception.code, "DOWNLOAD_NETWORK_FAILED")
        self.assertNotIn("synthetic", str(caught.exception))
        self.assertFalse(session.trust_env)
        self.assertFalse(session.get.call_args.kwargs["allow_redirects"])
        self.assertEqual(session.get.call_args.kwargs["cookies"], {})

    def test_default_download_and_cached_rerun_never_call_browser(self):
        parsed = {"page_count": 1, "pages": [{"page": 1, "text": "synthetic", "has_images": False}]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(z, "OUTPUT", root / "output"), patch.object(z.sys, "platform", "darwin"), \
                    patch.object(z, "load_metadata", return_value=META), \
                    patch.object(z, "load_cookie", return_value=COOKIE["value"]), \
                    patch.object(z, "download_cookie", return_value=DATA) as download, \
                    patch.object(z, "chrome") as browser, patch.object(z, "extract", return_value=parsed):
                first = z.run(URL, NAME, root / "nonexistent-downloads")
                repeat = z.run(URL, NAME, root / "nonexistent-downloads")
            self.assertFalse(first["cached"])
            self.assertTrue(repeat["cached"])
            self.assertEqual(first["transport"], "cookie")
            download.assert_called_once()
            browser.assert_not_called()
            self.assertEqual(Path(first["pdf"]).read_bytes(), DATA)

    def test_batch_validates_all_entries_before_any_download(self):
        valid = {"topic_url": URL, "attachment_name": NAME}
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "batch.json"
            for tasks in [[], [valid] * 21, [valid, valid], [valid, {**valid, "topic_url": "https://evil.test"}],
                          [valid, {**valid, "attachment_name": 123}], [valid, {**valid, "topic_url": None}]]:
                manifest.write_text(json.dumps(tasks))
                with patch.object(z, "run") as run:
                    self.expect_failure("INVALID_BATCH", z.run_batch, manifest, Path(tmp), 60, z.COOKIE_FILE)
                run.assert_not_called()

    def test_batch_stops_on_first_error_and_preserves_completed_receipts(self):
        tasks = [{"topic_url": URL, "attachment_name": f"{i}.pdf"} for i in range(3)]
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "batch.json"; manifest.write_text(json.dumps(tasks))
            with patch.object(z, "run", side_effect=[{"status": "ok"}, z.Failure("COOKIE_LOGIN_REQUIRED", "reimport")]) as run, \
                    patch.object(z.time, "sleep"):
                result = z.run_batch(manifest, Path(tmp), 60, z.COOKIE_FILE)
            self.assertEqual(run.call_count, 2)
            self.assertEqual(result["completed"], [{"status": "ok"}])
            self.assertEqual(result["failed_index"], 1)
            self.assertEqual(result["remaining_not_started"], 1)

    def test_batch_succeeds_serially_in_list_order(self):
        tasks = [{"topic_url": URL, "attachment_name": f"{i}.pdf"} for i in range(2)]
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "batch.json"; manifest.write_text(json.dumps(tasks))
            with patch.object(z, "run", return_value={"status": "ok"}) as run, patch.object(z.time, "sleep") as sleep:
                result = z.run_batch(manifest, Path(tmp), 60, z.COOKIE_FILE)
            self.assertEqual(result["count"], 2)
            self.assertEqual([call.args[1] for call in run.call_args_list], ["0.pdf", "1.pdf"])
            sleep.assert_called_once_with(2)


if __name__ == "__main__":
    unittest.main()
