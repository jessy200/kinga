# Understanding Kinga: a walkthrough for its builder

Read this until you can explain every part in your own words. Mozilla's reviewers, and
anyone you demo to, will ask *why* it works the way it does.

## 1. The four files that matter

| File | What it does | Lines |
|---|---|---|
| `kinga/db.py` | All the rules and all the data. The heart of the project. | ~230 |
| `kinga/server.py` | Receives web requests and calls the right `db` function. | ~150 |
| `kinga/pages.py` | Turns data into HTML pages. | ~200 |
| `tests/test_kinga.py` | Proves the rules hold. | ~130 |

Start with `db.py`. If you understand it, you understand Kinga.

## 2. The data (db.py, top of file)

Four tables in one SQLite file:

- `purposes`: the list the community asks about (care, referral, research, ...)
- `members`: one row per person, keyed by their card code. The alias is optional.
- `consents`: one row per (member, purpose) with `granted` = 1 or 0
- `ledger`: every event, never edited and never deleted

**Exercise:** run `python -m kinga`, join once, then open `kinga.db` with
[DB Browser for SQLite](https://sqlitebrowser.org) and look at the four tables.

## 3. The consent rule (`request_access`)

```python
allowed = consents_for(conn, code).get(purpose_id, False)
```

That one line is the whole decision. Note the `False` default: if there is no row (for
example, a purpose added after the member joined), the answer is **no**. That is what
"opt-in" means in code.

Then, allowed or not, the request is written to the ledger. **Question to answer
yourself:** why record refusals? (Hint: what would the community learn if the same
researcher is refused 40 times in a week?)

## 4. The tamper-evident ledger (`_fingerprint`, `_append`, `verify_ledger`)

Each entry stores:
- `prev_hash`: the fingerprint of the entry before it
- `hash`: SHA-256 of (prev_hash + all of this entry's fields)

So entry 5's fingerprint depends on entry 4's, which depends on entry 3's, and so on.
Change one letter in entry 2 and its fingerprint no longer matches what is stored, and
every entry after it points at the wrong parent. `verify_ledger` walks the chain and
reports the first entry that doesn't match.

**What it can't stop:** someone with the file who rebuilds *every* fingerprint from
scratch. That is why the home page shows "today's fingerprint" for a steward to write
down. If the chain is rebuilt, yesterday's written fingerprint won't appear in it anymore.
This is the same idea as Git commits and certificate-transparency logs.

**Exercise:** run the tests, then read `test_editing_an_old_entry_is_detected`. Try
editing the database yourself with DB Browser and reload `/ledger`.

## 5. The web part (server.py)

- `do_GET` shows pages; `do_POST` changes things.
- After a change it **redirects** (`303`) so refreshing the page doesn't submit twice.
- `app.lock` lets only one write happen at a time, so two requests can't both claim to be
  "the next entry" in the chain.
- `--host 0.0.0.0` means phones on the same Wi-Fi can connect.

## 6. Safety details worth knowing

- `esc()` in `pages.py` turns `<script>` into harmless text. There's a test for it.
- Card codes use 8 characters from 31 letters and digits, about 850 billion combinations,
  and skip characters that look alike (0/O, 1/I/L).
- The steward PIN is compared with `hmac.compare_digest`, which takes the same time whether
  the guess is close or not, so nobody can guess it from timing.
- The server never prints member codes to the console (`log_message` is silenced).

## 7. Talking about it (for the Mozilla letter and interviews)

Be ready to answer, in your own words:
1. Why opt-in rather than opt-out?
2. What does a hash chain prove, and what doesn't it prove?
3. Why run locally instead of in the cloud? (Power cuts, internet cuts, and who controls the server.)
4. What would it take to make an EMR *enforce* Kinga's answer? (README roadmap, item 3.)
5. What did the health workers you showed it to say? (Fill this in after you test it.)

## 8. Putting it on GitHub

1. Create a free account at github.com if you don't have one.
2. Create a new **public** repository called `kinga` (no README, since you already have one).
3. In this folder:

```bash
git init
git add .
git commit -m "Kinga v0.1: community consent and access log"
git branch -M main
git remote add origin https://github.com/<your-username>/kinga.git
git push -u origin main
```

4. Add 3 screenshots to the README: Join, My data, and the Record page showing a caught edit.
