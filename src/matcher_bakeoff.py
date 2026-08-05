"""Pick a matcher prompt by measuring it, not by arguing about it.

THE PROBLEM THIS IS SOLVING
The first matcher asked "does this description plausibly contain what the
detector responds to? Yes/No" and answered YES to essentially everything: 97% of
margins above the cut, and — the clean measurement — 78% of features that
provably did NOT fire in an activation were still judged present. The two-null
rule correctly returned "unknown" for 96% of pairs, i.e. the measurement refused
itself. Diagnosis: a reflexive Yes-bias, not a reasoning failure. Two candidate
causes were tested and BOTH were wrong:

  * "grammatical labels make the question unanswerable" — measured: null_feat
    rate 0.78 for grammatical labels vs 0.79 for content-bearing ones. No
    difference. The failure is uniform.
  * "the threshold is in the wrong place" — a cut calibrated against the null
    fixes the false-positive rate at 5% BY CONSTRUCTION, so it manufactures the
    headline number instead of measuring it.

Hence a bake-off. Chance is known for both metrics, so no variant can produce a
flattering number by construction.

VARIANT B — the candidate MEASUREMENT
Judges one feature at a time, so it yields a per-pair verdict, which is what the
analysis needs. Four prompt changes, each aimed at a specific failure:

  1. "plausibly" is GONE. It invited yes — almost any text plausibly contains
     almost anything.
  2. THE BASE RATE IS STATED. An explanation is one or two sentences while the
     activation has ~20 features, so most features are genuinely NOT discussed.
     The model was never told this and defaulted to yes; saying it supplies the
     correct prior.
  3. UNCERTAINTY GETS ITS OWN ANSWER. A binary forces a coin-flip into "yes".
     UNCLEAR gives it somewhere else to go.
  4. THE TWO OBSERVED FAILURE MODES ARE NAMED AND BANNED — "loosely related"
     and "grammatical pattern that appears in all writing".

VARIANT C — a DIAGNOSTIC ONLY, not a candidate
Shows k features that fired and k that did not, in ONE prompt, and asks for a
ranking. Forcing a relative ordering removes a global Yes-bias structurally: the
model cannot rank everything first.

But it CANNOT be the measurement, and this is worth being explicit about. It
needs known-absent features mixed in — both to give the ranking something to
discriminate and to supply ground truth. In real use no such set exists; there
are only the activation's own features. So C answers one question only: **is
there any usable signal in this model's judgements at all?** If C separates real
from fake, the information exists and B's job is to expose it. If C fails too,
no prompt will work and that is the finding.

SCORING — identical for every variant, so the comparison is fair
  FPR    features that did NOT fire, judged present. Ground truth from the SAE.
         CAVEAT, previously overstated as "clean": a feature fires at ONE token
         position while the explanation describes the whole passage, so a
         non-firing feature can still be genuinely relevant. That inflates FPR
         somewhat. It does not explain 78% — three features drawn at random from
         353 are relevant a few percent of the time, not seventy.
  AUC    do real features score above non-firing ones. 0.5 = chance.

Usage:
    python src/matcher_bakeoff.py \
        --dirs results results/rollout \
               results/wildchat \
        --labels-json results/feature_labels.json \
        --n-units 40 --out results/bakeoff.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

# ---------------------------------------------------------------- variant A
_A = """Below is a description written by a model that was shown one position inside a
piece of text. It describes what that text is about.

DESCRIPTION:
{expl}

Separately, a feature detector is known to respond to:

  {content}

Question: is the DESCRIPTION above talking about that — does the text it
describes plausibly contain what the detector responds to?

Judge meaning, not wording. Answer only Yes or No."""

# ---------------------------------------------------------------- variant B
#
# NOTE ON WHAT THIS PROMPT MUST NOT SAY: it must never state or imply that the
# detector was active. That is true for real pairs and FALSE for the non-firing
# controls, and those controls are the entire false-positive measurement. Telling
# the model the detector fired would bias precisely the pairs that test it. The
# two conditions must be worded identically and neutrally.
_B = """CONTEXT — how this data was produced.

A language model was reading a piece of text. At one specific position, its
internal state was captured: a snapshot of what the model was representing at
that moment.

Two separate tools then read that same snapshot.

The DESCRIBER was asked to write a short summary of what the model appeared to
be representing there — the subject matter, entities, tone, genre, or structure
it had picked up from the text so far. This is what the describer wrote:

    {expl}

The DETECTOR is a separate probe. It responds to one specific thing:

    {content}

YOUR TASK.

Judging only from the DESCRIBER's summary above: does that summary cover the
thing the DETECTOR responds to?

Be strict. The summary is one or two sentences, while the text it came from
contains dozens of distinguishable things. Most detectors are therefore NOT
covered by it, and NO is the ordinary answer.

Answer yes only if a person reading the summary would come away knowing about
this specific thing. Do NOT answer yes merely because:
  - the summary concerns the same broad topic
  - the text could plausibly contain it
  - the detector describes a grammatical pattern found in all writing

Reply with exactly one word:
  CLEARLY   the summary explicitly covers it
  PROBABLY  not stated outright, but clearly implied by it
  UNCLEAR   genuinely cannot tell
  NO        the summary does not cover it"""

_OPTS = ["CLEARLY", "PROBABLY", "UNCLEAR", "NO"]

# ---------------------------------------------------------------- variant C
_C = """CONTEXT — how this data was produced.

A language model was reading a piece of text. At one specific position, its
internal state was captured. A DESCRIBER then read that snapshot and wrote a
short summary of what the model appeared to be representing there — subject
matter, entities, tone, genre, or structure:

    {expl}

Below are {n} DETECTORS. Each responds to one specific thing. Some of these were
active in that snapshot and some were not — you are not told which.

{items}

YOUR TASK.

Rank the detectors by how well the DESCRIBER's summary covers what each one
responds to — from best covered to least covered.

Reply with only the numbers, best covered first, comma-separated. Include every
number exactly once and add nothing else."""


@torch.no_grad()
def option_scores(model, tok, prompts, opt_ids, bs=16):
    """logprob of each option's first token at the answer position."""
    out = []
    for i in range(0, len(prompts), bs):
        texts = [tok.apply_chat_template([{"role": "user", "content": p}], tokenize=False,
                                          add_generation_prompt=True) for p in prompts[i:i + bs]]
        enc = tok(texts, return_tensors="pt", padding=True,
                  add_special_tokens=False).to(model.device)
        lg = model(**enc).logits[:, -1, :].float().log_softmax(-1)
        out += lg[:, opt_ids].tolist()
    return out


def auc(pos, neg):
    if not len(pos) or not len(neg):
        return float("nan")
    p, n = np.asarray(pos)[:, None], np.asarray(neg)[None, :]
    return float(((p > n).sum() + 0.5 * (p == n).sum()) / (len(pos) * len(neg)))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dirs", nargs="+", required=True)
    ap.add_argument("--names", nargs="+", default=None)
    ap.add_argument("--labels-json", required=True)
    ap.add_argument("--model", default="google/gemma-3-12b-it")
    ap.add_argument("--sae", default="l0_small")
    ap.add_argument("--n-units", type=int, default=40, help="explanations in the pilot")
    ap.add_argument("--n-feat", type=int, default=6, help="fired features per unit")
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)
    names = a.names or [Path(d).name or "fineweb" for d in a.dirs]

    L = json.loads(Path(a.labels_json).read_text())
    usable = {int(k): v for k, v in L.items() if v.get("reliable") and v.get("label")}

    units = []
    for d, nm in zip(a.dirs, names):
        d = Path(d)
        base = json.loads((d / "feature_overlap.json").read_text())
        small = json.loads((d / f"feature_overlap_{a.sae}.json").read_text())
        for i, r in enumerate(small["runs"]):
            e = (base["runs"][i].get("explanation") or "").strip()
            if e:
                units.append({"corpus": nm, "act": r["act"], "explanation": e[:1200],
                               "own": set(r["shared_features"]) | set(r["lost_features"])
                                      | set(r["invented_features"])})
    rng = np.random.default_rng(a.seed)
    sel = rng.choice(len(units), min(a.n_units, len(units)), replace=False)
    units = [units[int(i)] for i in sel]
    print(f"[data] {len(units)} explanations, {len(usable)} validated labels")

    tok = AutoTokenizer.from_pretrained(a.model)
    tok.padding_side = "left"
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(a.model, dtype=torch.bfloat16).to("cuda").eval()

    YES = [tok.encode(s, add_special_tokens=False)[0] for s in ("Yes", " Yes", "yes")]
    NO_ = [tok.encode(s, add_special_tokens=False)[0] for s in ("No", " No", "no")]
    OPT = [tok.encode(o, add_special_tokens=False)[0] for o in _OPTS]
    assert len(set(OPT)) == len(OPT), (
        f"variant B options share a first token {list(zip(_OPTS, OPT))} — the "
        f"argmax verdict would be meaningless. Reword them.")

    # ---- build the shared pair list, so A and B see IDENTICAL data ----
    pairs = []            # (unit_idx, feature, is_real)
    for i, u in enumerate(units):
        fired = sorted(u["own"] & usable.keys())
        absent = sorted(usable.keys() - u["own"])
        for f in rng.choice(fired, min(a.n_feat, len(fired)), replace=False):
            pairs.append((i, int(f), True))
        for f in rng.choice(absent, min(a.n_feat, len(absent)), replace=False):
            pairs.append((i, int(f), False))
    print(f"[pairs] {len(pairs)} = {sum(p[2] for p in pairs)} fired "
          f"+ {sum(not p[2] for p in pairs)} non-firing (ground truth)")

    res = {}
    t0 = time.time()

    # ---------------- variant A: baseline yes/no ----------------
    pr = [_A.format(expl=units[i]["explanation"], content=usable[f]["label"])
          for i, f, _ in pairs]
    sc = option_scores(model, tok, pr, YES + NO_, bs=a.batch)
    ny = len(YES)
    marg = [float(torch.logsumexp(torch.tensor(s[:ny]), 0)
                  - torch.logsumexp(torch.tensor(s[ny:]), 0)) for s in sc]
    real = [m for m, p in zip(marg, pairs) if p[2]]
    fake = [m for m, p in zip(marg, pairs) if not p[2]]
    res["A_baseline"] = {"fpr": float(np.mean([m > 0 for m in fake])),
                          "tpr": float(np.mean([m > 0 for m in real])),
                          "auc": auc(real, fake)}
    print(f"[A] {(time.time()-t0)/60:.1f}m  fpr={res['A_baseline']['fpr']:.3f} "
          f"tpr={res['A_baseline']['tpr']:.3f} auc={res['A_baseline']['auc']:.3f}")

    # ---------------- variant B: graded, strict ----------------
    t1 = time.time()
    pr = [_B.format(expl=units[i]["explanation"], content=usable[f]["label"])
          for i, f, _ in pairs]
    sc = option_scores(model, tok, pr, OPT, bs=a.batch)
    verd = [_OPTS[int(np.argmax(s))] for s in sc]
    # continuous score: says-yes mass vs says-no mass
    cont = [float(torch.logsumexp(torch.tensor(s[:2]), 0)
                  - torch.logsumexp(torch.tensor(s[2:]), 0)) for s in sc]
    pres = [v in ("CLEARLY", "PROBABLY") for v in verd]
    real = [c for c, p in zip(cont, pairs) if p[2]]
    fake = [c for c, p in zip(cont, pairs) if not p[2]]
    res["B_graded"] = {
        "fpr": float(np.mean([q for q, p in zip(pres, pairs) if not p[2]])),
        "tpr": float(np.mean([q for q, p in zip(pres, pairs) if p[2]])),
        "auc": auc(real, fake),
        "verdicts_on_real": dict(Counter(v for v, p in zip(verd, pairs) if p[2])),
        "verdicts_on_fake": dict(Counter(v for v, p in zip(verd, pairs) if not p[2]))}
    print(f"[B] {(time.time()-t1)/60:.1f}m  fpr={res['B_graded']['fpr']:.3f} "
          f"tpr={res['B_graded']['tpr']:.3f} auc={res['B_graded']['auc']:.3f}")
    print(f"    on REAL features: {res['B_graded']['verdicts_on_real']}")
    print(f"    on FAKE features: {res['B_graded']['verdicts_on_fake']}")

    # ---------------- variant C: ranking (diagnostic) ----------------
    t2 = time.time()
    aucs = []
    prompts, meta = [], []
    for i, u in enumerate(units):
        mine = [(f, r) for j, f, r in pairs if j == i]
        if len(mine) < 4:
            continue
        order = rng.permutation(len(mine))
        shown = [mine[int(k)] for k in order]
        items = "\n".join(f"  {n+1}. {usable[f]['label']}" for n, (f, _) in enumerate(shown))
        prompts.append(_C.format(expl=u["explanation"], n=len(shown), items=items))
        meta.append(shown)
    outs = []
    for i in range(0, len(prompts), 8):
        texts = [tok.apply_chat_template([{"role": "user", "content": p}], tokenize=False,
                                          add_generation_prompt=True) for p in prompts[i:i + 8]]
        enc = tok(texts, return_tensors="pt", padding=True,
                  add_special_tokens=False).to(model.device)
        with torch.no_grad():
            g = model.generate(**enc, max_new_tokens=90, do_sample=False,
                               pad_token_id=tok.pad_token_id)
        outs += [tok.decode(r[enc["input_ids"].shape[1]:], skip_special_tokens=True) for r in g]
    n_parsed = 0
    for shown, txt in zip(meta, outs):
        nums = [int(x) for x in re.findall(r"\d+", txt) if 1 <= int(x) <= len(shown)]
        seen, order = set(), []
        for x in nums:
            if x not in seen:
                seen.add(x); order.append(x)
        if len(order) < len(shown) // 2:
            continue
        n_parsed += 1
        rank = {x: k for k, x in enumerate(order)}
        # rank position: lower = judged more likely present
        rp = [(-rank.get(n + 1, len(shown)), r) for n, (_, r) in enumerate(shown)]
        aucs.append(auc([s for s, r in rp if r], [s for s, r in rp if not r]))
    res["C_ranking"] = {"auc": float(np.nanmean(aucs)) if aucs else None,
                         "n_prompts": len(prompts), "n_parsed": n_parsed}
    print(f"[C] {(time.time()-t2)/60:.1f}m  auc={res['C_ranking']['auc']} "
          f"({n_parsed}/{len(prompts)} parsed)")

    # ---------------- verdict ----------------
    print("\n" + "=" * 72)
    print(f"{'variant':<16}{'FPR':>8}{'TPR':>8}{'AUC':>8}   lower FPR + higher AUC wins")
    print("=" * 72)
    for k in ("A_baseline", "B_graded"):
        r = res[k]
        print(f"{k:<16}{r['fpr']:>8.3f}{r['tpr']:>8.3f}{r['auc']:>8.3f}")
    print(f"{'C_ranking':<16}{'-':>8}{'-':>8}{res['C_ranking']['auc'] or float('nan'):>8.3f}"
          f"   diagnostic only — needs known-absent features, so it cannot measure")
    print("\nFPR is the number that matters: features that did NOT fire, judged")
    print("present. Baseline A ran at 0.78 on the full set. If B is not far below")
    print("that, the prompt is not the problem and no rewording will fix it.")
    print("If C's AUC is near 0.5 too, the model cannot do this task at all and")
    print("that is the finding — stop rewording and report it.")

    Path(a.out).write_text(json.dumps({"config": vars(a), "results": res}, indent=2))
    print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()
