"""Web front end: talk to Gemma, get a trust report on every turn.

    python trust_tool/app.py --av $AV --ar $AR
    -> open http://localhost:8000

STDLIB ONLY, deliberately. `http.server` is enough for one local user and adds
no dependency to a repo whose requirements are already a long list of pinned ML
packages. There is no framework here to learn or to break.

The page is served from a single string below. State lives in the Session
object, in this process -- refreshing the page keeps the conversation, because
the models are loaded here, not in the browser.

WHAT THE PAGE SHOWS PER TURN
  your message, then Gemma's reply, then the trust report on the activation
  taken at the last token of your message (i.e. what the model was representing
  when it had finished reading you, with the whole conversation behind it).

  CONFIRMED   in the activation AND recovered by the AR from the explanation
  UNVERIFIED  the AR produced it; the SAE did not find it in the activation
  OMITTED     in the activation; the AR did not recover it

  The counts include latents with no validated label. Only labelled ones can be
  NAMED, and about half of all latents have one -- so a report showing "4 of 15"
  is telling you the truth about its own coverage, not hiding something.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from session import Session                                        # noqa: E402

SESSION: Session | None = None
LOCK = threading.Lock()          # one GPU; serialise turns

PAGE = """<!doctype html>
<meta charset="utf-8">
<title>NLA trust report</title>
<style>
  :root { --bg:#fbfaf9; --fg:#1a1a1a; --mut:#6b6b6b; --line:#e3e0dc;
          --ok:#1a7f4b; --un:#b7791f; --om:#6b6b6b; --acc:#2b5fd9; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#16171a; --fg:#e8e6e3; --mut:#9a9a9a; --line:#2c2e33;
            --ok:#4ade80; --un:#fbbf24; --om:#9a9a9a; --acc:#7aa2f7; }
  }
  * { box-sizing:border-box }
  body { margin:0; background:var(--bg); color:var(--fg); font:15px/1.6
         ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif; }
  header { padding:18px 24px; border-bottom:1px solid var(--line) }
  header h1 { margin:0; font-size:16px; font-weight:650 }
  header p { margin:4px 0 0; color:var(--mut); font-size:13px }
  main { max-width:1180px; margin:0 auto; padding:24px;
         display:grid; grid-template-columns:1fr 1fr; gap:24px }
  @media (max-width:900px) { main { grid-template-columns:1fr } }
  .col h2 { font-size:12px; text-transform:uppercase; letter-spacing:.07em;
            color:var(--mut); margin:0 0 12px; font-weight:600 }
  .turn { border:1px solid var(--line); border-radius:10px; padding:14px 16px;
          margin-bottom:14px; background:color-mix(in srgb,var(--bg) 92%,var(--fg)) }
  .you { font-weight:600; margin-bottom:6px }
  .reply { white-space:pre-wrap }
  .meta { color:var(--mut); font-size:12px; margin-top:10px;
          border-top:1px solid var(--line); padding-top:8px }
  .expl { font-style:italic; color:var(--mut); margin:0 0 12px;
          border-left:3px solid var(--line); padding-left:12px }
  .bucket { margin:0 0 12px }
  .bucket h3 { font-size:13px; margin:0 0 4px; font-weight:650 }
  .ok h3 { color:var(--ok) } .un h3 { color:var(--un) } .om h3 { color:var(--om) }
  .bucket ul { margin:4px 0 0; padding-left:18px }
  .bucket li { margin:2px 0; font-size:13px }
  code { font:12px ui-monospace,SFMono-Regular,Menlo,monospace; color:var(--mut) }
  form { max-width:1180px; margin:0 auto; padding:0 24px 32px; display:flex; gap:10px }
  textarea { flex:1; min-height:64px; padding:11px 13px; border:1px solid var(--line);
             border-radius:8px; background:var(--bg); color:var(--fg);
             font:inherit; resize:vertical }
  button { padding:0 22px; border:0; border-radius:8px; background:var(--acc);
           color:#fff; font:inherit; font-weight:600; cursor:pointer }
  button[disabled] { opacity:.5; cursor:default }
  .note { max-width:1180px; margin:0 auto; padding:0 24px 20px;
          color:var(--mut); font-size:12.5px }
  .warn { color:var(--un); font-weight:600 }
</style>
<header>
  <h1>NLA trust report</h1>
  <p>Talk to Gemma. Each turn is measured against a sparse autoencoder that reads
     the activation directly and never saw the NLA.</p>
</header>
<main>
  <div class="col"><h2>Conversation</h2><div id="chat"></div></div>
  <div class="col"><h2>What the activation supports</h2><div id="rep"></div></div>
</main>
<form id="f">
  <textarea id="q" placeholder="Ask Gemma something…" autofocus></textarea>
  <button id="b">Send</button>
</form>
<p class="note">
  The activation is taken at the <b>last token of your message</b> — what the
  model was representing when it had finished reading you, with the whole
  conversation behind it. Counts include latents with no validated label; only
  labelled ones are named, and about half of all latents have one.
</p>
<script>
const chat = document.getElementById('chat'), rep = document.getElementById('rep');
const f = document.getElementById('f'), q = document.getElementById('q'),
      b = document.getElementById('b');
const esc = s => s.replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

function bucket(cls, title, n, items) {
  const named = items.length, unnamed = n - named;
  let h = `<div class="bucket ${cls}"><h3>${title} — ${n}</h3>`;
  if (named) h += '<ul>' + items.map(i =>
      `<li><code>f${i.id}</code> ${esc(i.label)}</li>`).join('') + '</ul>';
  if (unnamed) h += `<div class="meta">${named} named, ${unnamed} counted but
      unlabelled</div>`;
  return h + '</div>';
}

function render(t) {
  chat.insertAdjacentHTML('beforeend',
    `<div class="turn"><div class="you">You</div><div class="reply">${esc(t.user)}</div>
     <div class="meta">Gemma</div><div class="reply">${esc(t.reply)}</div></div>`);
  rep.insertAdjacentHTML('beforeend',
    `<div class="turn">
       ${t.failed ? `<div class="warn">${esc(t.failed)}</div>` : ''}
       ${t.cjk ? '<div class="warn">CJK in the explanation — the injection may have failed. Do not trust this turn.</div>' : ''}
       <p class="expl">${esc(t.explanation)}</p>
       ${bucket('ok','CONFIRMED',t.n_confirmed,t.confirmed)}
       ${bucket('un','UNVERIFIED',t.n_unverified,t.unverified)}
       ${bucket('om','OMITTED',t.n_omitted,t.omitted)}
       <div class="meta">cos ${t.cos==null?'—':t.cos.toFixed(4)} ·
         token ${t.position} of ${t.n_context} · turn ${t.turn}</div>
     </div>`);
  window.scrollTo(0, document.body.scrollHeight);
}

f.onsubmit = async e => {
  e.preventDefault();
  const text = q.value.trim(); if (!text) return;
  q.value = ''; b.disabled = true; b.textContent = 'Thinking…';
  try {
    const r = await fetch('/ask', {method:'POST', body: JSON.stringify({text})});
    const t = await r.json();
    if (t.error) { rep.insertAdjacentHTML('beforeend',
        `<div class="turn warn">${esc(t.error)}</div>`); }
    else render(t);
  } finally { b.disabled = false; b.textContent = 'Send'; q.focus(); }
};
</script>
"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE.encode(), "text/html; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):
        if self.path != "/ask":
            return self._send(404, b"not found", "text/plain")
        n = int(self.headers.get("Content-Length", 0))
        text = json.loads(self.rfile.read(n) or b"{}").get("text", "")
        # One GPU, so turns are serialised. A second browser tab waits rather
        # than racing two forward passes onto the same device.
        with LOCK:
            try:
                t = SESSION.ask(text)
                out = {
                    "user": t.user, "reply": t.reply, "explanation": t.explanation,
                    "confirmed": t.confirmed, "unverified": t.unverified,
                    "omitted": t.omitted, "n_confirmed": t.n_confirmed,
                    "n_unverified": t.n_unverified, "n_omitted": t.n_omitted,
                    "cos": t.cos, "position": t.position,
                    "n_context": t.n_context, "cjk": t.cjk,
                    "failed": t.failed,
                    "turn": len(SESSION.turns),
                }
            except Exception as e:                       # surfaced in the page
                out = {"error": f"{type(e).__name__}: {e}"}
        self._send(200, json.dumps(out).encode(), "application/json")

    def log_message(self, *a):                            # quiet the access log
        pass


def main() -> None:
    global SESSION
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--av", required=True)
    ap.add_argument("--ar", required=True)
    ap.add_argument("--labels", default="results/feature_labels.json")
    ap.add_argument("--base", default="google/gemma-3-12b-it")
    ap.add_argument("--layer", type=int, default=32)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--max-new-tokens", type=int, default=400)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--phase", action="store_true",
                    help="load and release each model per turn. Needed under "
                         "~72GB; costs a minute or two of loading per reply")
    a = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)

    print(f"[load] models{' (phased per turn)' if a.phase else ''}…")
    SESSION = Session(a.av, a.ar, a.labels, base=a.base, layer=a.layer,
                      device=a.device, phase=a.phase,
                      max_new_tokens=a.max_new_tokens, seed=a.seed)
    print(f"[ready] http://localhost:{a.port}")
    HTTPServer(("", a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
