"""Classify every feature on three axes, then cross-tab by shared / lost / made.

============================================================================
THIS EXPERIMENT FAILED ITS OWN CONTROL. NOTHING IN RESULTS.md USES IT.
Write-up: INCONCLUSIVE.md. Two reasons, either fatal on its own:

  * It judges features against the WHOLE SOURCE DOCUMENT. An activation
    sampled at one token position is not a claim about the whole document,
    so the question is aimed at the wrong object -- no prompt fixes that.
  * The PRESENT axis asks a plain yes/no, the exact prompt shape that scored
    a 78.3% false-positive rate in the matcher bake-off before being
    replaced. This one never went through that bake-off, and its own control
    judged 47.8% of labels present in unrelated documents.

Kept because INCONCLUSIVE.md states it still runs and still prints its
control, and because the guard at the end -- which refuses to report when
own-vs-control stops separating -- is a pattern worth keeping. It fired on a
real run.
============================================================================

THE QUESTION
Reading the labels by hand suggested that shared features name the document's
subject, lost features name the SPECIFIC things inside it (Nginx, "tomato",
temperature values, National Park), and made features are semantically adjacent
misfires (a "Black Americans" feature for a fantasy creature called Schwarzfell,
"Black Pelt"). That reading came from eyeballing ~50 activations and could
easily be a story imposed on noise. This measures it.

THREE AXES, per (feature, activation)
  type          GRAMMAR   the label describes only a position or part of speech
                CONTENT   it names subject matter
  specificity   GENERIC   a broad category ("climate conditions")
                SPECIFIC  a particular named thing ("Death Valley", "38 degrees")
  accuracy      is what this detector responds to ACTUALLY PRESENT in this text?

ACCURACY IS THE NEW ONE, and it is only possible because the n=50 rerun finally
saved the source text. The n=10 run stored a parquet row index, the parquet died
with its pod, and the rollout responses were generated unseeded -- so that text
is gone permanently and this check could not have been run on it.

It also measures something no earlier stage could: whether the SAE ITSELF is
right about the document. Every previous check took the feature sets as ground
truth. If lost features turn out to be systematically LESS accurate than shared
ones, then "loss" is partly the SAE firing spuriously rather than the round trip
destroying information -- a completely different story, and one that would
undercut the headline.

THE CONTROL IS MANDATORY
Each feature is judged against its OWN source text and against a DIFFERENT
activation's source text. A model asked "is this present?" will drift toward
yes; the control is what separates a real accuracy rate from that drift. If
accuracy does not fall on the wrong text, the axis carries no information and
must not be reported. This project has had three measurements collapse for
exactly this reason -- most recently a matcher that judged 78% of features
present in activations they never fired in.

Usage:
    python src/classify_features.py \
        --dir results \
        --out results/feature_classification.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

_PROMPT = """Below is an excerpt from a document, and a description of one detector that
responds to certain tokens.

DOCUMENT EXCERPT:
{text}

DETECTOR responds to:
  {label}

Answer three questions about the DETECTOR, on three lines exactly.

TYPE: is the detector defined by grammar or by subject matter?
  GRAMMAR  - it describes a position or part of speech only, e.g. "a noun
             following a preposition", "words after a colon". It would apply to
             writing about anything.
  CONTENT  - it names actual subject matter, e.g. "CPU components", "rainfall",
             "SQL keywords".

SPECIFICITY: how narrow is it?
  GENERIC  - a broad category: "climate conditions", "code keywords".
  SPECIFIC - a particular named thing or value: "Nginx", "the word tomato",
             "temperature values with degree symbols".

PRESENT: is what this detector responds to ACTUALLY IN the document excerpt
above? Judge only against the excerpt shown. Be strict — answer NO if the
excerpt does not contain it, even if it seems like the kind of document that
might contain it elsewhere.
  YES / NO

Reply exactly:
TYPE: <GRAMMAR|CONTENT>
SPECIFICITY: <GENERIC|SPECIFIC>
PRESENT: <YES|NO>"""


def batch_gen(model, tok, prompts, bs=12, max_new=24, log_every=20):
    out, t0 = [], time.time()
    for i in range(0, len(prompts), bs):
        texts = [tok.apply_chat_template([{"role": "user", "content": p}], tokenize=False,
                                          add_generation_prompt=True) for p in prompts[i:i + bs]]
        enc = tok(texts, return_tensors="pt", padding=True,
                  add_special_tokens=False).to(model.device)
        with torch.no_grad():
            g = model.generate(**enc, max_new_tokens=max_new, do_sample=False,
                               pad_token_id=tok.pad_token_id)
        out += [tok.decode(r[enc["input_ids"].shape[1]:], skip_special_tokens=True)
                for r in g]
        b = i // bs
        if b and b % log_every == 0:
            el = time.time() - t0
            print(f"    {len(out):>5}/{len(prompts)}  {el/60:>5.1f}m  "
                  f"eta {(el/len(out))*(len(prompts)-len(out))/60:>4.0f}m")
    return out


def parse(txt):
    t = re.search(r"TYPE:\s*(GRAMMAR|CONTENT)", txt, re.I)
    s = re.search(r"SPECIFICITY:\s*(GENERIC|SPECIFIC)", txt, re.I)
    p = re.search(r"PRESENT:\s*(YES|NO)", txt, re.I)
    return (t.group(1).upper() if t else None,
            s.group(1).upper() if s else None,
            (p.group(1).upper() == "YES") if p else None)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", required=True)
    ap.add_argument("--model", default="google/gemma-3-12b-it")
    ap.add_argument("--sae", default="l0_small")
    ap.add_argument("--text-chars", type=int, default=1100)
    ap.add_argument("--batch", type=int, default=12)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)
    D = Path(a.dir)

    L = json.loads((D / "feature_labels.json").read_text())
    val = {int(k): v for k, v in L.items() if v.get("reliable") and v.get("label")}
    O = json.loads((D / "feature_overlap.json").read_text())
    J = json.loads((D / f"feature_overlap_{a.sae}.json").read_text())
    src = O.get("source_text")
    assert src, ("no source_text in feature_overlap.json — this run predates the fix "
                 "that carries it through, and accuracy cannot be judged without it")

    # one run per activation: buckets differ per run, so mixing runs would make a
    # single row internally inconsistent
    rows, seen = [], set()
    for r in J["runs"]:
        if r["act"] in seen:
            continue
        seen.add(r["act"])
        for b, key in (("shared", "shared_features"), ("lost", "lost_features"),
                        ("made", "invented_features")):
            for f in r[key]:
                if f in val:
                    rows.append({"act": r["act"], "feature": f, "bucket": b,
                                  "label": val[f]["label"],
                                  "categories": val[f]["categories"]})
    acts = sorted(seen)
    print(f"[data] {len(acts)} activations, {len(rows)} labelled (feature, bucket) pairs")

    tok = AutoTokenizer.from_pretrained(a.model)
    tok.padding_side = "left"
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(a.model, dtype=torch.bfloat16).to("cuda").eval()

    rng = np.random.default_rng(a.seed)
    prompts, key = [], []
    for i, r in enumerate(rows):
        own = src[r["act"]][-a.text_chars:]
        other_act = int(rng.choice([x for x in acts if x != r["act"]]))
        prompts.append(_PROMPT.format(text=own, label=r["label"]))
        key.append((i, "own"))
        prompts.append(_PROMPT.format(text=src[other_act][-a.text_chars:], label=r["label"]))
        key.append((i, "control"))
    print(f"[work] {len(prompts)} judgements ({len(rows)} own + {len(rows)} control)")

    outs = batch_gen(model, tok, prompts, bs=a.batch)
    for (i, arm), txt in zip(key, outs):
        t, s, p = parse(txt)
        if arm == "own":
            rows[i].update({"type": t, "specificity": s, "present": p})
        else:
            rows[i]["present_control"] = p

    # ---------------- validation ----------------
    ok = [r for r in rows if r.get("present") is not None
          and r.get("present_control") is not None]
    own = float(np.mean([r["present"] for r in ok]))
    ctl = float(np.mean([r["present_control"] for r in ok]))
    print("\n" + "=" * 74)
    print("IS THE 'PRESENT' JUDGEMENT REAL?")
    print("=" * 74)
    print(f"  judged present in its OWN text        {100*own:>5.1f}%")
    print(f"  judged present in a DIFFERENT text    {100*ctl:>5.1f}%   <- control")
    print(f"  gap                                   {100*(own-ctl):>+5.1f}")
    if own - ctl < 0.15:
        print("\n  !! GAP TOO SMALL. The accuracy axis is not discriminating and must")
        print("     not be reported. Everything below inherits it.")

    # ---------------- results ----------------
    def block(title, keyfn, vals):
        print("\n" + "=" * 74)
        print(title)
        print("=" * 74)
        print(f"{'bucket':<10}{'n':>6}" + "".join(f"{v:>12}" for v in vals))
        for b in ("shared", "lost", "made"):
            sub = [r for r in ok if r["bucket"] == b]
            if not sub:
                continue
            c = Counter(keyfn(r) for r in sub)
            print(f"{b:<10}{len(sub):>6}" +
                  "".join(f"{100*c[v]/len(sub):>11.0f}%" for v in vals))

    block("GRAMMAR vs CONTENT", lambda r: r["type"], ["GRAMMAR", "CONTENT"])
    block("GENERIC vs SPECIFIC", lambda r: r["specificity"], ["GENERIC", "SPECIFIC"])

    print("\n" + "=" * 74)
    print("ACCURACY — is the feature actually present in the text?")
    print("   own vs control; only the GAP is meaningful")
    print("=" * 74)
    print(f"{'bucket':<10}{'n':>6}{'own':>9}{'control':>10}{'gap':>8}")
    for b in ("shared", "lost", "made"):
        sub = [r for r in ok if r["bucket"] == b]
        if not sub:
            continue
        o = np.mean([r["present"] for r in sub])
        c = np.mean([r["present_control"] for r in sub])
        print(f"{b:<10}{len(sub):>6}{100*o:>8.0f}%{100*c:>9.0f}%{100*(o-c):>+7.0f}")

    print("\n" + "=" * 74)
    print("THE CROSS-TAB — accuracy by bucket x type x specificity")
    print("=" * 74)
    print(f"{'bucket':<10}{'type':<9}{'specificity':<13}{'n':>6}{'present':>10}{'control':>10}")
    for b in ("shared", "lost", "made"):
        for t in ("CONTENT", "GRAMMAR"):
            for s in ("SPECIFIC", "GENERIC"):
                sub = [r for r in ok if r["bucket"] == b and r["type"] == t
                       and r["specificity"] == s]
                if len(sub) < 5:
                    continue
                o = np.mean([r["present"] for r in sub])
                c = np.mean([r["present_control"] for r in sub])
                print(f"{b:<10}{t:<9}{s:<13}{len(sub):>6}{100*o:>9.0f}%{100*c:>9.0f}%")

    Path(a.out).write_text(json.dumps(
        {"config": vars(a),
         "validation": {"present_own": own, "present_control": ctl, "gap": own - ctl},
         "rows": rows}, indent=2))
    print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()
