"""Kinga's web server, using only Python's standard library.

Start it with:   python -m kinga
Then open:       http://localhost:8080  (or http://<this-computer's-IP>:8080 from a phone
                 on the same Wi-Fi)
"""

import argparse
import hmac
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import db, pages

STATIC = Path(__file__).parent / "static"


class App:
    def __init__(self, db_path, steward_pin):
        self.conn = db.connect(db_path)
        self.lock = threading.Lock()  # one write at a time keeps the hash chain in order
        self.steward_pin = steward_pin


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        def send_html(self, html, status=200):
            body = html.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'")
            self.end_headers()
            self.wfile.write(body)

        def redirect(self, location):
            self.send_response(303)
            self.send_header("Location", location)
            self.end_headers()

        def form(self):
            length = min(int(self.headers.get("Content-Length") or 0), 20_000)
            data = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
            return data

        # ---------- GET ----------
        def do_GET(self):
            url = urlparse(self.path)
            q = parse_qs(url.query)
            path = url.path
            conn = app.conn
            if path == "/":
                ok, _ = db.verify_ledger(conn)
                latest = conn.execute("SELECT seq, hash FROM ledger ORDER BY seq DESC LIMIT 1").fetchone()
                return self.send_html(pages.home(db.community_stats(conn), ok, latest))
            if path == "/join":
                return self.send_html(pages.join_form(db.list_purposes(conn)))
            if path == "/joined":
                return self.send_html(pages.joined(q.get("code", [""])[0]))
            if path == "/me":
                code = q.get("code", [""])[0]
                if not code:
                    return self.send_html(pages.me_lookup())
                m = db.get_member(conn, code)
                if not m:
                    return self.send_html(pages.me_lookup("No member with that code. Check your card."), 404)
                msg = "Your choice was saved." if q.get("saved") else ""
                return self.send_html(pages.me_page(m, db.list_purposes(conn), db.consents_for(conn, m["code"]),
                                                    db.history_for(conn, m["code"]), msg))
            if path == "/access":
                return self.send_html(pages.access_form(db.list_purposes(conn)))
            if path == "/ledger":
                ok, bad = db.verify_ledger(conn)
                return self.send_html(pages.ledger_page(db.ledger(conn), ok, bad, db.list_purposes(conn, True)))
            if path == "/rules":
                return self.send_html(pages.rules_page(db.list_purposes(conn)))
            if path == "/static/style.css":
                body = (STATIC / "style.css").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/css; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                return self.wfile.write(body)
            return self.send_html(pages.not_found(), 404)

        # ---------- POST ----------
        def do_POST(self):
            path = urlparse(self.path).path
            f = self.form()
            get = lambda k: (f.get(k) or [""])[0]
            conn = app.conn
            with app.lock:
                if path == "/join":
                    code = db.add_member(conn, get("alias"), set(f.get("p", [])))
                    return self.redirect(f"/joined?code={code}")
                if path == "/me/consent":
                    try:
                        db.set_consent(conn, get("code"), get("purpose"), get("granted") == "1")
                    except ValueError as e:
                        return self.send_html(pages.me_lookup(str(e)), 400)
                    return self.redirect(f"/me?code={db.normalize_code(get('code'))}&saved=1")
                if path == "/access":
                    prefill = {k: get(k) for k in ("code", "actor", "purpose", "reason")}
                    try:
                        allowed = db.request_access(conn, get("code"), get("actor"), get("purpose"), get("reason"))
                    except ValueError as e:
                        return self.send_html(pages.access_form(db.list_purposes(conn), str(e), None, prefill), 400)
                    return self.send_html(pages.access_form(db.list_purposes(conn), "", allowed, prefill))
                if path == "/rules":
                    if not hmac.compare_digest(get("pin"), app.steward_pin):
                        return self.send_html(pages.rules_page(db.list_purposes(conn), err="Wrong steward PIN."), 403)
                    try:
                        db.add_purpose(conn, get("pid"), get("label"), get("description"), actor="steward")
                    except ValueError as e:
                        return self.send_html(pages.rules_page(db.list_purposes(conn), err=str(e)), 400)
                    return self.send_html(pages.rules_page(db.list_purposes(conn), msg="Purpose added. Everyone starts at NO."))
            return self.send_html(pages.not_found(), 404)

        def log_message(self, fmt, *args):  # keep the console quiet and free of member codes
            pass

    return Handler


def main():
    ap = argparse.ArgumentParser(description="Kinga: community-owned consent and access log")
    ap.add_argument("--host", default="0.0.0.0", help="0.0.0.0 lets phones on the same Wi-Fi connect")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--db", default="kinga.db", help="where the data file is kept")
    args = ap.parse_args()
    pin = os.environ.get("KINGA_STEWARD_PIN", "")
    if not pin:
        pin = "change-me"
        print("WARNING: no KINGA_STEWARD_PIN set. Using 'change-me'. Set your own before real use.")
    app = App(args.db, pin)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(app))
    print(f"Kinga is running. Open http://localhost:{args.port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
