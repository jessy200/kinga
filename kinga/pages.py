"""HTML for every Kinga page.

Plain HTML forms, no JavaScript needed, so it works on old phones and
cheap tablets over the clinic's local Wi-Fi. Every value shown on a page
goes through esc() so nobody can inject code by typing it into a form.
"""

from html import escape as esc

KIND_TEXT = {
    "member_joined": "Joined Kinga",
    "consent_set": "First choice recorded",
    "consent_changed": "Changed their choice",
    "access_allowed": "Access allowed",
    "access_refused": "Access refused",
    "purpose_added": "Community added a new purpose",
}


def layout(title, body, active=""):
    def nav(href, label, key):
        cur = ' aria-current="page"' if key == active else ""
        return f'<a href="{href}"{cur}>{label}</a>'
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} · Kinga</title>
<link rel="stylesheet" href="/static/style.css">
</head><body>
<header class="top"><div class="wrap">
  <a class="brand" href="/">Kinga</a>
  <nav>{nav('/join','Join','join')}{nav('/me','My data','me')}{nav('/access','Request access','access')}{nav('/ledger','Record','ledger')}{nav('/rules','Rules','rules')}</nav>
</div></header>
<main class="wrap">{body}</main>
<footer class="wrap muted">Runs on this machine only. No internet, no cloud. Your community holds the data.</footer>
</body></html>"""


def flash(msg, kind="info"):
    return f'<p class="flash {kind}">{esc(msg)}</p>' if msg else ""


def home(stats, ledger_ok, latest=None):
    rows = "".join(
        f"<tr><td>{esc(s['purpose']['label'])}</td>"
        f"<td class='num'>{s['yes']}</td>"
        f"<td class='num'>{s['allowed']}</td><td class='num'>{s['refused']}</td></tr>"
        for s in stats["per_purpose"])
    chain = ('<span class="ok">Intact. No entry has been changed.</span>' if ledger_ok
             else '<span class="bad">Broken. Someone changed the record. See the Record page.</span>')
    fingerprint = ""
    if latest:
        fingerprint = (
            '<div class="card"><b>Today\'s fingerprint</b>'
            f'<code class="code">{esc(latest["hash"][:16])}</code>'
            f'<span class="muted">Entry #{latest["seq"]}. A community steward should write this down '
            '(or post it on the clinic noticeboard) at the end of each day. If the record is ever '
            'rebuilt in secret, this fingerprint will no longer appear in it.</span></div>')
    return layout("Community view", f"""
<h1>Who uses our health data, and for what</h1>
<p class="lead">Members choose what their data may be used for. Every request is checked against
those choices and written to a record nobody can quietly change.</p>
<div class="tiles">
  <div><b>{stats['members']}</b>members</div>
  <div><b>{sum(s['allowed'] for s in stats['per_purpose'])}</b>requests allowed</div>
  <div><b>{sum(s['refused'] for s in stats['per_purpose'])}</b>requests refused</div>
  <div><b>{stats['withdrawals']}</b>consents withdrawn</div>
</div>
<h2>By purpose</h2>
<div class="scroll"><table>
<thead><tr><th>Purpose</th><th class="num">Members who said yes</th><th class="num">Allowed</th><th class="num">Refused</th></tr></thead>
<tbody>{rows}</tbody></table></div>
<p>Record check: {chain}</p>
{fingerprint}
<div class="actions"><a class="btn primary" href="/join">Add a member</a><a class="btn" href="/access">Request access to a record</a></div>
""", "home")


def join_form(purposes, msg=""):
    boxes = "".join(
        f"""<label class="choice"><input type="checkbox" name="p" value="{esc(p['id'])}">
        <span><b>{esc(p['label'])}</b><small>{esc(p['description'])}</small></span></label>"""
        for p in purposes)
    return layout("Join", f"""
<h1>Join Kinga</h1>
{flash(msg, 'bad')}
<p class="lead">Tick only what you agree to. Anything you leave unticked is a NO.
You can change your mind at any time.</p>
<form method="post" action="/join" class="card">
  <label class="field">A name or nickname <small>Optional. Stays on this machine. You can leave it blank.</small>
    <input name="alias" maxlength="60" autocomplete="off"></label>
  <fieldset><legend>My data may be used for:</legend>{boxes}</fieldset>
  <button class="btn primary" type="submit">Join and get my card code</button>
</form>""", "join")


def joined(code):
    return layout("Your code", f"""
<h1>Welcome. Here is your code.</h1>
<div class="card code-card"><span class="muted">Kinga card</span><b class="code">{esc(code)}</b>
<span class="muted">Write this on your card. Use it to see who has looked at your data,
or to change your choices.</span></div>
<div class="actions"><a class="btn primary" href="/me?code={esc(code)}">See my data and choices</a><a class="btn" href="/join">Add another member</a></div>
""", "join")


def me_lookup(msg=""):
    return layout("My data", f"""
<h1>My data</h1>
{flash(msg, 'bad')}
<form method="get" action="/me" class="card inline">
  <label class="field">Your Kinga code<input name="code" placeholder="KG-XXXX-XXXX" required autocomplete="off"></label>
  <button class="btn primary" type="submit">Open</button>
</form>""", "me")


def me_page(member, purposes, consents, history, msg=""):
    code = member["code"]
    rows = []
    for p in purposes:
        on = consents.get(p["id"], False)
        rows.append(f"""<li class="consent {'yes' if on else 'no'}">
  <span><b>{esc(p['label'])}</b><small>{esc(p['description'])}</small></span>
  <form method="post" action="/me/consent">
    <input type="hidden" name="code" value="{esc(code)}"><input type="hidden" name="purpose" value="{esc(p['id'])}">
    <input type="hidden" name="granted" value="{'0' if on else '1'}">
    <span class="state">{'YES' if on else 'NO'}</span>
    <button class="btn small" type="submit">{'Withdraw' if on else 'Allow'}</button>
  </form></li>""")
    labels = {p["id"]: p["label"] for p in purposes}
    hist = "".join(
        f"""<li class="ev {esc(h['kind'])}"><time>{esc(h['at'].replace('T', ' ')[:16])}</time>
        <span><b>{esc(KIND_TEXT.get(h['kind'], h['kind']))}</b>
        {(' · ' + esc(labels.get(h['purpose_id'], h['purpose_id']))) if h['purpose_id'] else ''}
        {(' · ' + esc(h['outcome'].upper())) if h['kind'] in ('consent_set', 'consent_changed') else ''}
        <small>{esc(h['actor'] or '')}{(' — ' + esc(h['detail'])) if h['detail'] else ''}</small></span></li>"""
        for h in history) or "<li class='muted'>Nothing yet.</li>"
    who = f" ({esc(member['alias'])})" if member["alias"] else ""
    return layout("My data", f"""
<h1>My data <span class="muted">{esc(code)}{who}</span></h1>
{flash(msg, 'ok')}
<h2>My choices</h2>
<ul class="consents">{''.join(rows)}</ul>
<h2>Who has asked for my data</h2>
<ul class="timeline">{hist}</ul>""", "me")


def access_form(purposes, msg="", result=None, prefill=None):
    prefill = prefill or {}
    opts = "".join(
        f'<option value="{esc(p["id"])}"{" selected" if prefill.get("purpose") == p["id"] else ""}>{esc(p["label"])}</option>'
        for p in purposes)
    res = ""
    if result is not None:
        res = ('<div class="result ok"><b>Allowed.</b> This member said yes to this purpose. The request has been recorded.</div>'
               if result else
               '<div class="result bad"><b>Refused.</b> This member has not agreed to this purpose. Do not use their data for it. The request has been recorded.</div>')
    return layout("Request access", f"""
<h1>Request access to a record</h1>
<p class="lead">For health workers. Every request is recorded, including refused ones, and the member can see it.</p>
{flash(msg, 'bad')}{res}
<form method="post" action="/access" class="card">
  <label class="field">Member's Kinga code<input name="code" required value="{esc(prefill.get('code', ''))}" placeholder="KG-XXXX-XXXX" autocomplete="off"></label>
  <label class="field">Your name and role<input name="actor" required maxlength="80" value="{esc(prefill.get('actor', ''))}" placeholder="e.g. Sr. Nakato, nurse"></label>
  <label class="field">Purpose<select name="purpose">{opts}</select></label>
  <label class="field">Reason <small>Short and specific. The member will read this.</small><input name="reason" maxlength="300" value="{esc(prefill.get('reason', ''))}"></label>
  <button class="btn primary" type="submit">Check and record</button>
</form>""", "access")


def ledger_page(entries, ok, bad_seq, purposes):
    labels = {p["id"]: p["label"] for p in purposes}
    broken = ' class="broken"'
    rows = "".join(
        f"<tr{broken if bad_seq == e['seq'] else ''}><td class='num'>{e['seq']}</td>"
        f"<td>{esc(e['at'].replace('T', ' ')[:16])}</td><td>{esc(KIND_TEXT.get(e['kind'], e['kind']))}</td>"
        f"<td>{esc(e['member_code'] or '')}</td><td>{esc(e['actor'] or '')}</td>"
        f"<td>{esc(labels.get(e['purpose_id'], e['purpose_id'] or ''))}</td><td>{esc(e['outcome'] or '')}</td>"
        f"<td class='hash' title='{esc(e['hash'])}'>{esc(e['hash'][:10])}…</td></tr>"
        for e in entries)
    status = ('<div class="result ok"><b>Record intact.</b> Every entry matches its fingerprint and the one before it.</div>'
              if ok else
              f'<div class="result bad"><b>Record broken at entry {bad_seq}.</b> That entry, or one before it, was changed or deleted outside Kinga.</div>')
    return layout("Record", f"""
<h1>The record</h1>
<p class="lead">Every join, choice and request, newest first. Each entry carries a fingerprint of itself
and of the entry before it, so a quiet edit breaks the chain.</p>
{status}
<div class="scroll"><table class="ledger">
<thead><tr><th class="num">#</th><th>When (UTC)</th><th>What</th><th>Member</th><th>Who</th><th>Purpose</th><th>Result</th><th>Fingerprint</th></tr></thead>
<tbody>{rows}</tbody></table></div>""", "ledger")


def rules_page(purposes, msg="", err=""):
    rows = "".join(f"<li><b>{esc(p['label'])}</b> <code>{esc(p['id'])}</code><small>{esc(p['description'])}</small></li>"
                   for p in purposes)
    return layout("Rules", f"""
<h1>Community rules</h1>
<p class="lead">The purposes members are asked about. The community decides this list, not the software maker.
A new purpose starts as NO for everyone until each member says yes.</p>
{flash(msg, 'ok')}{flash(err, 'bad')}
<ul class="purposes">{rows}</ul>
<h2>Add a purpose</h2>
<form method="post" action="/rules" class="card">
  <label class="field">Short id<input name="pid" required maxlength="40" placeholder="e.g. sms_reminders"></label>
  <label class="field">Label<input name="label" required maxlength="80" placeholder="e.g. SMS appointment reminders"></label>
  <label class="field">What it means, in plain words<input name="description" maxlength="200"></label>
  <label class="field">Steward PIN<input name="pin" type="password" required autocomplete="off"></label>
  <button class="btn primary" type="submit">Add purpose</button>
</form>""", "rules")


def not_found():
    return layout("Not found", "<h1>Page not found</h1><p><a href='/'>Back to the community view</a></p>")
