"""Run with:  python -m unittest discover -s tests -v"""

import json
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

from kinga import db
from kinga.server import App, make_handler


class ConsentRules(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")

    def test_everything_starts_as_no_unless_ticked(self):
        code = db.add_member(self.conn, "Test", {"care"})
        c = db.consents_for(self.conn, code)
        self.assertTrue(c["care"])
        self.assertFalse(c["research"])
        self.assertFalse(c["ai_training"])

    def test_access_follows_consent(self):
        code = db.add_member(self.conn, "", {"care"})
        self.assertTrue(db.request_access(self.conn, code, "Nurse A", "care", "check-up"))
        self.assertFalse(db.request_access(self.conn, code, "Researcher B", "research", "study"))

    def test_withdrawal_takes_effect_immediately(self):
        code = db.add_member(self.conn, "", {"care", "research"})
        self.assertTrue(db.request_access(self.conn, code, "R", "research", "x"))
        db.set_consent(self.conn, code, "research", False)
        self.assertFalse(db.request_access(self.conn, code, "R", "research", "x"))

    def test_refused_requests_are_recorded_too(self):
        code = db.add_member(self.conn, "", set())
        db.request_access(self.conn, code, "R", "research", "x")
        kinds = [h["kind"] for h in db.history_for(self.conn, code)]
        self.assertIn("access_refused", kinds)

    def test_new_purpose_starts_as_no_for_existing_members(self):
        code = db.add_member(self.conn, "", {"care"})
        db.add_purpose(self.conn, "sms", "SMS reminders", "", actor="steward")
        self.assertFalse(db.consents_for(self.conn, code)["sms"])
        self.assertFalse(db.request_access(self.conn, code, "Clinic", "sms", "reminder"))

    def test_codes_can_be_typed_loosely(self):
        code = db.add_member(self.conn, "", set())
        loose = code.lower().replace("-", " ")
        self.assertIsNotNone(db.get_member(self.conn, loose))

    def test_unknown_member_is_rejected(self):
        with self.assertRaises(ValueError):
            db.request_access(self.conn, "KG-AAAA-BBBB", "X", "care", "")


class TamperEvidence(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        self.code = db.add_member(self.conn, "", {"care"})
        db.request_access(self.conn, self.code, "Nurse", "care", "visit")

    def test_untouched_record_verifies(self):
        self.assertEqual(db.verify_ledger(self.conn), (True, None))

    def test_editing_an_old_entry_is_detected(self):
        self.conn.execute("UPDATE ledger SET outcome='allowed', kind='access_allowed' WHERE seq=2")
        ok, seq = db.verify_ledger(self.conn)
        self.assertFalse(ok)
        self.assertEqual(seq, 2)

    def test_deleting_an_entry_is_detected(self):
        self.conn.execute("DELETE FROM ledger WHERE seq=3")
        ok, _ = db.verify_ledger(self.conn)
        self.assertFalse(ok)


class WebPages(unittest.TestCase):
    """Starts the real server on a free port and clicks through it."""

    @classmethod
    def setUpClass(cls):
        cls.app = App(":memory:", "1234")
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.app))
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def post(self, path, fields):
        data = urllib.parse.urlencode(fields, doseq=True).encode()
        try:
            with urllib.request.urlopen(self.base + path, data) as r:
                return r.status, r.geturl(), r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, None, e.read().decode()

    def get(self, path):
        with urllib.request.urlopen(self.base + path) as r:
            return r.read().decode()

    def test_every_page_loads(self):
        for p in ["/", "/join", "/me", "/access", "/ledger", "/rules", "/static/style.css"]:
            self.assertTrue(self.get(p))

    def test_join_then_refused_access_shows_on_my_page(self):
        status, url, _ = self.post("/join", {"alias": "<script>x</script>", "p": ["care"]})
        code = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["code"][0]
        _, _, page = self.post("/access", {"code": code, "actor": "Dr Test", "purpose": "research", "reason": "study"})
        self.assertIn("Refused", page)
        me = self.get("/me?code=" + code)
        self.assertIn("Access refused", me)
        self.assertNotIn("<script>x</script>", me)  # typed text is escaped, never run

    def test_wrong_pin_cannot_change_rules(self):
        status, _, page = self.post("/rules", {"pid": "x", "label": "X", "description": "", "pin": "0000"})
        self.assertEqual(status, 403)


if __name__ == "__main__":
    unittest.main()
