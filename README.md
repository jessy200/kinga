# Kinga

**A community-owned consent and access log for health data.
It runs on a laptop or Raspberry Pi in the clinic, with no internet and no cloud.**

*Kinga* is Swahili for protection.

In many clinics, patient data gets used for care, referrals, research, reporting and now
AI training. The people it describes rarely know who used it or why, and they have no
way to say no. Kinga gives them that say, and it keeps working when the power or
internet goes down.

## What it does

| Who | What they can do |
|---|---|
| **Community member** | Joins and chooses, purpose by purpose, what their data may be used for. Gets a short card code (`KG-XXXX-XXXX`) instead of giving their name. Can see every request for their data and withdraw consent at any time. |
| **Health worker** | Asks to use a member's data for a purpose. Kinga answers **Allowed** or **Refused** based on that member's choices, and records the request either way. |
| **Community steward** | Decides which purposes members are asked about (protected by a PIN). A new purpose starts as **NO** for everyone. |
| **Anyone** | Sees community totals (how many said yes to each purpose, and how many requests were allowed or refused) without seeing who anyone is. |

### Design choices

- **Opt-in only.** Anything a member doesn't tick is a NO.
- **Refusals are recorded too.** A refused request is still evidence of who tried.
- **Tamper-evident record.** Every entry stores a SHA-256 fingerprint of itself and of the
  entry before it. If someone edits or deletes an old entry, the Record page shows exactly
  where the chain breaks. A steward writes down each day's latest fingerprint, so even a
  full rebuild of the record can be caught.
- **Nothing to install.** It uses only the Python standard library and SQLite, so it runs
  fully offline on cheap hardware.
- **Works on any phone.** Plain HTML forms with no JavaScript, served over the clinic's
  local Wi-Fi.

## Run it

You need Python 3.10 or newer.

```bash
python -m kinga
```

Open http://localhost:8080. To use it from phones on the same Wi-Fi, open
`http://<this-computer's-IP>:8080`.

Set your own steward PIN first:

```bash
# Linux / Raspberry Pi / macOS
KINGA_STEWARD_PIN=your-pin python -m kinga
# Windows PowerShell
$env:KINGA_STEWARD_PIN="your-pin"; python -m kinga
```

Options: `--port 8080`, `--db kinga.db` (where the data file lives), `--host 127.0.0.1`
(this computer only).

## Test it

```bash
python -m unittest discover -s tests -v
```

The 13 tests cover the consent rules, withdrawal, tamper detection (edits and deletions),
safe display of typed text, and the steward PIN.

## Status: an early prototype

This is a working first version, built to test the idea with community health workers.
**It is not ready for real patient data yet.** Known gaps:

- No login for health workers. Anyone on the network can make a request (every request is recorded).
- Anyone holding a card code can view that member's page. The code works like a password, so keep the card private.
- Traffic is not encrypted (plain HTTP on the local network).
- No backup or sync between clinics yet.
- Kinga records consent and requests. It does not hold or block access to the medical record
  itself, so it has to be connected to the clinic's EMR to enforce decisions.

## Roadmap

1. Test with community health workers and members, and change the wording and purposes with them.
2. Health-worker accounts and HTTPS on the local network.
3. Plug-in check for open-source EMRs, so the EMR asks Kinga before releasing data.
4. Steward tools: printable daily fingerprint sheet, export for community meetings.
5. Offline sync between clinics without a central cloud.
6. Translations (Luganda, Runyankore, Swahili).

## License

MIT. See [LICENSE](LICENSE).
