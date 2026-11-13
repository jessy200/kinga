"""Kinga data layer.

Everything Kinga knows lives in one SQLite file on the local machine.
No internet, no cloud, no outside service.

Four tables:
  purposes  - the uses of data the community has agreed to ask about
  members   - people who have joined (identified by a short code, not a name)
  consents  - each member's yes/no for each purpose
  ledger    - an append-only record of everything that happens

The ledger is "hash-chained": every entry stores a fingerprint (SHA-256 hash)
of its own contents plus the fingerprint of the entry before it. If anyone
edits or deletes an old entry, the fingerprints stop matching and
verify_ledger() reports exactly where the chain breaks.
"""

import hashlib
import json
import secrets
import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS purposes (
    id          TEXT PRIMARY KEY,
    label       TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    active      INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS members (
    code       TEXT PRIMARY KEY,
    alias      TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS consents (
    member_code TEXT NOT NULL REFERENCES members(code),
    purpose_id  TEXT NOT NULL REFERENCES purposes(id),
    granted     INTEGER NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (member_code, purpose_id)
);
CREATE TABLE IF NOT EXISTS ledger (
    seq         INTEGER PRIMARY KEY AUTOINCREMENT,
    at          TEXT NOT NULL,
    kind        TEXT NOT NULL,
    member_code TEXT,
    actor       TEXT,
    purpose_id  TEXT,
    outcome     TEXT,
    detail      TEXT,
    prev_hash   TEXT NOT NULL,
    hash        TEXT NOT NULL
);
"""

# The starting list of purposes. A community steward can add more from the
# Rules page; nothing here is fixed.
DEFAULT_PURPOSES = [
    ("care", "Care at this facility",
     "Health workers here may read my record to treat me."),
    ("referral", "Sharing for my referral",
     "My record may be sent to another facility when I am referred."),
    ("research", "Research",
     "A university or NGO may use my record for a study."),
    ("ai_training", "Training computer models (AI)",
     "My record may be used to build or train AI tools."),
    ("reporting", "Counts for health reporting",
     "My visit may be counted (without my name) in reports to the district or ministry."),
]

GENESIS = "0" * 64  # the "previous hash" of the very first ledger entry
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I/L: easy to read aloud


def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect(path):
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    if conn.execute("SELECT COUNT(*) FROM purposes").fetchone()[0] == 0:
        for pid, label, desc in DEFAULT_PURPOSES:
            conn.execute("INSERT INTO purposes(id, label, description) VALUES (?,?,?)",
                         (pid, label, desc))
        conn.commit()
    return conn


# ---------- the tamper-evident ledger ----------

def _fingerprint(prev_hash, at, kind, member_code, actor, purpose_id, outcome, detail):
    payload = json.dumps(
        [prev_hash, at, kind, member_code, actor, purpose_id, outcome, detail],
        ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _append(conn, kind, member_code=None, actor=None, purpose_id=None,
            outcome=None, detail=None):
    row = conn.execute("SELECT hash FROM ledger ORDER BY seq DESC LIMIT 1").fetchone()
    prev_hash = row["hash"] if row else GENESIS
    at = now()
    h = _fingerprint(prev_hash, at, kind, member_code, actor, purpose_id, outcome, detail)
    conn.execute(
        "INSERT INTO ledger(at, kind, member_code, actor, purpose_id, outcome, detail, prev_hash, hash)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (at, kind, member_code, actor, purpose_id, outcome, detail, prev_hash, h))
    return h


def verify_ledger(conn):
    """Re-compute every fingerprint. Returns (True, None) if the chain is intact,
    or (False, seq) with the first entry that does not match."""
    prev = GENESIS
    for r in conn.execute("SELECT * FROM ledger ORDER BY seq"):
        expected = _fingerprint(prev, r["at"], r["kind"], r["member_code"], r["actor"],
                                r["purpose_id"], r["outcome"], r["detail"])
        if r["prev_hash"] != prev or r["hash"] != expected:
            return False, r["seq"]
        prev = r["hash"]
    return True, None


# ---------- purposes ----------

def list_purposes(conn, include_inactive=False):
    sql = "SELECT * FROM purposes" + ("" if include_inactive else " WHERE active = 1")
    return conn.execute(sql + " ORDER BY rowid").fetchall()


def add_purpose(conn, pid, label, description, actor):
    pid = "".join(c for c in pid.lower().replace(" ", "_") if c.isalnum() or c == "_")[:40]
    if not pid or not label.strip():
        raise ValueError("A purpose needs a short id and a label.")
    if conn.execute("SELECT 1 FROM purposes WHERE id = ?", (pid,)).fetchone():
        raise ValueError(f"A purpose with id '{pid}' already exists.")
    with conn:
        conn.execute("INSERT INTO purposes(id, label, description) VALUES (?,?,?)",
                     (pid, label.strip(), description.strip()))
        _append(conn, "purpose_added", actor=actor, purpose_id=pid, detail=label.strip())
    return pid


# ---------- members and consent ----------

def _new_code(conn):
    while True:
        raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
        code = f"KG-{raw[:4]}-{raw[4:]}"
        if not conn.execute("SELECT 1 FROM members WHERE code = ?", (code,)).fetchone():
            return code


def normalize_code(code):
    """Accept 'kg-abcd-efgh', 'KG ABCD EFGH', 'abcdefgh' and so on."""
    c = "".join(ch for ch in (code or "").upper() if ch.isalnum())
    if c.startswith("KG") and len(c) == 10:
        c = c[2:]
    if len(c) != 8:
        return (code or "").strip().upper()
    return f"KG-{c[:4]}-{c[4:]}"


def add_member(conn, alias, granted_purposes, actor="self"):
    """Create a member. Every purpose starts as NO unless it is in granted_purposes
    (opt-in, never opt-out)."""
    code = _new_code(conn)
    t = now()
    with conn:
        conn.execute("INSERT INTO members(code, alias, created_at) VALUES (?,?,?)",
                     (code, alias.strip()[:60], t))
        _append(conn, "member_joined", member_code=code, actor=actor)
        for p in list_purposes(conn):
            g = 1 if p["id"] in granted_purposes else 0
            conn.execute("INSERT INTO consents VALUES (?,?,?,?)", (code, p["id"], g, t))
            _append(conn, "consent_set", member_code=code, actor=actor,
                    purpose_id=p["id"], outcome="yes" if g else "no")
    return code


def get_member(conn, code):
    return conn.execute("SELECT * FROM members WHERE code = ?", (normalize_code(code),)).fetchone()


def consents_for(conn, code):
    """Return {purpose_id: True/False}. A purpose added after the member joined
    has no row yet, which counts as NO."""
    rows = conn.execute("SELECT purpose_id, granted FROM consents WHERE member_code = ?",
                        (normalize_code(code),)).fetchall()
    have = {r["purpose_id"]: bool(r["granted"]) for r in rows}
    return {p["id"]: have.get(p["id"], False) for p in list_purposes(conn)}


def set_consent(conn, code, purpose_id, granted, actor="self"):
    code = normalize_code(code)
    if not get_member(conn, code):
        raise ValueError("No member with that code.")
    with conn:
        conn.execute(
            "INSERT INTO consents VALUES (?,?,?,?) "
            "ON CONFLICT(member_code, purpose_id) DO UPDATE SET granted = excluded.granted, "
            "updated_at = excluded.updated_at",
            (code, purpose_id, 1 if granted else 0, now()))
        _append(conn, "consent_changed", member_code=code, actor=actor,
                purpose_id=purpose_id, outcome="yes" if granted else "no")


# ---------- access requests ----------

def request_access(conn, code, actor, purpose_id, reason):
    """A health worker (actor) asks to use a member's data for a purpose.
    Allowed only if that member said YES to that purpose. Every request,
    allowed or refused, is written to the ledger."""
    code = normalize_code(code)
    actor = actor.strip()[:80]
    if not actor:
        raise ValueError("Say who is asking (name and role).")
    if not get_member(conn, code):
        raise ValueError("No member with that code. Check the card and try again.")
    allowed = consents_for(conn, code).get(purpose_id, False)
    outcome = "allowed" if allowed else "refused"
    with conn:
        _append(conn, "access_" + outcome, member_code=code, actor=actor,
                purpose_id=purpose_id, outcome=outcome, detail=reason.strip()[:300])
    return allowed


# ---------- reading the record ----------

def history_for(conn, code):
    return conn.execute("SELECT * FROM ledger WHERE member_code = ? ORDER BY seq DESC",
                        (normalize_code(code),)).fetchall()


def ledger(conn, limit=200):
    return conn.execute("SELECT * FROM ledger ORDER BY seq DESC LIMIT ?", (limit,)).fetchall()


def community_stats(conn):
    """Numbers the community can see without seeing anyone's identity."""
    members = conn.execute("SELECT COUNT(*) FROM members").fetchone()[0]
    per_purpose = []
    for p in list_purposes(conn):
        yes = conn.execute("SELECT COUNT(*) FROM consents WHERE purpose_id = ? AND granted = 1",
                           (p["id"],)).fetchone()[0]
        allowed = conn.execute("SELECT COUNT(*) FROM ledger WHERE kind='access_allowed' AND purpose_id=?",
                               (p["id"],)).fetchone()[0]
        refused = conn.execute("SELECT COUNT(*) FROM ledger WHERE kind='access_refused' AND purpose_id=?",
                               (p["id"],)).fetchone()[0]
        per_purpose.append({"purpose": p, "yes": yes, "allowed": allowed, "refused": refused})
    withdrawals = conn.execute(
        "SELECT COUNT(*) FROM ledger WHERE kind='consent_changed' AND outcome='no'").fetchone()[0]
    return {"members": members, "per_purpose": per_purpose, "withdrawals": withdrawals}
