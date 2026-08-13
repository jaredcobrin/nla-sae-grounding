"""Does the AV's explanation cover what is actually in the activation?

THE PROMPT HERE WON A MEASURED BAKE-OFF. Do not "improve" it without re-running
matcher_bakeoff.py — the previous wording failed catastrophically and looked
fine while doing so.

    variant              FPR     TPR     AUC
    A  plain Yes/No    0.783   0.945   0.744
    B  graded (this)   0.075   0.292   0.767
    C  ranking             -       -   0.707   (diagnostic only)

Variant A said YES to 411 of 476 pairs, including 78% of features that provably
did NOT fire in the activation. Of its 411 yeses only 54% were real, against a
50% base rate — a "yes" carried essentially no information, and the two-null
rule correctly returned "unknown" for 96% of pairs. The measurement refused
itself.

What fixed it was NOT extra reasoning ability. AUC moved +0.023, which is 0.74
sigma — statistically nothing. The model could always rank real above fake; it
just would not say no. FPR moved 0.783 -> 0.075, about 20 sigma. The failure was
calibration, and the prompt below is what corrected it:

  1. "plausibly" removed — it invited yes; almost any text plausibly contains
     almost anything.
  2. The BASE RATE is stated. An explanation is one or two sentences while the
     activation holds ~20 features, so most features genuinely are not covered.
     The model was never told this and defaulted to yes.
  3. The SETUP is explained: a model read text, its internal state was captured,
     and BOTH the describer and the detector read that same snapshot. Without
     this the model does not know what it is being asked to compare.
  4. The three observed failure modes are named and banned outright.

  CRITICAL — the prompt must never state or imply that the detector was active.
  That is true for real pairs and FALSE for the non-firing controls, and those
  controls are the entire false-positive measurement. Both conditions are worded
  identically.

HONEST LIMIT OF THE GRADED SCALE: it did not work the way it was pitched. The
middle grades are barely used (PROBABLY 13/476, UNCLEAR 3/476), so this is not
really a 4-point scale — it is a better-calibrated binary. CLEARLY is 82% real
(+32 points over base rate); everything else is near or below base rate. Read it
as CLEARLY vs the rest.

WHAT THIS MEASURES
Loop over features and hand the matcher the WHOLE explanation. Three judgements
per pair:

  matched     this feature      vs its OWN explanation
  null_expl   this feature      vs N UNRELATED explanations
  null_feat   this explanation  vs N features that did NOT fire in it

Two nulls because the failure has two directions: null_expl catches a feature so
generic it matches any text, null_feat catches an explanation so broad that
anything matches it. A single control cannot tell those apart.

VERDICT PER (feature, explanation) — three-way, never two:
  covered, both null rates <= UNKNOWN_AT   -> PRESENT
  covered, either null rate  > UNKNOWN_AT  -> UNKNOWN
  not covered                              -> NOT_PRESENT

UNKNOWN is not a discard: the feature and its label stay valid everywhere else.
Collapsing unknown into "absent" would convert matcher failure into evidence
that the AV does not understand something.

"not present" is taken at face value. Justification: the measured failure mode
is over-matching, not under-matching. LIMIT: with NO at 43% real against a 50%
base rate, a "no" is only weakly informative, and the false-negative rate is not
measurable without ground truth for "the AV meant to mention this".

VALIDATION, using ground truth the SAE already provides
  FALSE-POSITIVE RATE  features that did NOT fire, judged covered. Every one is
                       an error. CAVEAT: a feature fires at ONE token position
                       while the explanation describes the whole passage, so a
                       non-firing feature can still be genuinely relevant. This
                       inflates FPR somewhat — it does not explain 78%.
  MATCHER AUC          same 0.5-1.0 scale as the label AUC, so the two stages are
                       directly comparable. A LOWER BOUND: a fired feature the AV
                       legitimately never mentioned counts against the matcher.
  SELF-CONSISTENCY     5 sampled explanations per activation should agree.

Usage:
    python src/judge_explanations.py \
        --dirs results results/rollout \
               results/wildchat \
        --names fineweb rollout wildchat \
        --labels-json results/feature_labels.json \
        --out results/grounding.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

N_NULL = 3            # unrelated explanations, and non-firing features, per pair
UNKNOWN_AT = 0.5      # a null rate above this makes the verdict UNKNOWN
OPTS = ["CLEARLY", "PROBABLY", "UNCLEAR", "NO"]
COVERED = {"CLEARLY", "PROBABLY"}

_PROMPT = """CONTEXT — how this data was produced.

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


@torch.no_grad()
def judge(model, tok, prompts, opt_ids, bs=24, log_every=40):
    """Logprob of each option's first token. One forward pass, no generation."""
    out, t0 = [], time.time()
    for i in range(0, len(prompts), bs):
        texts = [tok.apply_chat_template([{"role": "user", "content": p}], tokenize=False,
                                          add_generation_prompt=True) for p in prompts[i:i + bs]]
        enc = tok(texts, return_tensors="pt", padding=True,
                  add_special_tokens=False).to(model.device)
        lg = model(**enc).logits[:, -1, :].float().log_softmax(-1)
        out += lg[:, opt_ids].tolist()
        b = i // bs
        if b and b % log_every == 0:
            el = time.time() - t0
            print(f"    {len(out):>6}/{len(prompts)}  {el/60:>5.1f}m  "
                  f"eta {(el/len(out))*(len(prompts)-len(out))/60:>4.0f}m")
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
    ap.add_argument("--max-expl-chars", type=int, default=1200)
    ap.add_argument("--batch", type=int, default=24)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)
    names = a.names or [Path(d).name or "fineweb" for d in a.dirs]

    L = json.loads(Path(a.labels_json).read_text())
    usable = {int(k): v for k, v in L.items() if v.get("reliable") and v.get("label")}
    print(f"[labels] {len(L)} labelled | {len(usable)} validated and usable")

    units = []
    for d, nm in zip(a.dirs, names):
        d = Path(d)
        base = json.loads((d / "feature_overlap.json").read_text())
        small = json.loads((d / f"feature_overlap_{a.sae}.json").read_text())
        for i, r in enumerate(small["runs"]):
            e = (base["runs"][i].get("explanation") or "").strip()
            if not e:
                continue
            units.append({"corpus": nm, "act": r["act"], "run": i,
                           # Which paragraph-ablation variant this explanation is.
                           # Carried onto every judged row so conveyance can be
                           # reported per variant instead of averaging an
                           # explanation with two ablations of itself.
                           "variant": r.get("variant", "full"),
                           "explanation": e[:a.max_expl_chars],
                           "shared": set(r["shared_features"]),
                           "lost": set(r["lost_features"]),
                           "made": set(r["invented_features"])})
    print(f"[data] {len(units)} explanations across {len(a.dirs)} corpora")

    tok = AutoTokenizer.from_pretrained(a.model)
    tok.padding_side = "left"
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(a.model, dtype=torch.bfloat16).to("cuda").eval()
    OPT = [tok.encode(o, add_special_tokens=False)[0] for o in OPTS]
    assert len(set(OPT)) == len(OPT), f"options share a first token: {list(zip(OPTS, OPT))}"

    rng = np.random.default_rng(a.seed)
    prompts, key = [], []
    for i, u in enumerate(units):
        own = u["shared"] | u["lost"] | u["made"]
        # Controls must come from a different ACTIVATION, not merely a different
        # unit: when more than one explanation is sampled per activation they
        # share a feature set, so "different unit" would draw a null from the
        # same activation. Keying on (corpus, act) holds under any RUNS, and
        # since the corpus now yields one activation per conversation, a
        # different activation is also a different conversation.
        others = [j for j, w in enumerate(units)
                  if (w["corpus"], w["act"]) != (u["corpus"], u["act"])]
        absent = sorted(usable.keys() - own)     # ground truth for the FPR
        for f in sorted(own & usable.keys()):
            desc = usable[f]["label"]
            prompts.append(_PROMPT.format(expl=u["explanation"], content=desc))
            key.append((i, f, "matched"))
            for j in rng.choice(others, min(N_NULL, len(others)), replace=False):
                prompts.append(_PROMPT.format(expl=units[int(j)]["explanation"], content=desc))
                key.append((i, f, "null_expl"))
            for g in rng.choice(absent, min(N_NULL, len(absent)), replace=False):
                prompts.append(_PROMPT.format(expl=u["explanation"],
                                               content=usable[int(g)]["label"]))
                key.append((i, f, "null_feat"))
    n_pairs = sum(1 for k in key if k[2] == "matched")
    print(f"[work] {len(prompts)} judgements = {n_pairs} pairs x "
          f"(1 matched + {N_NULL} null_expl + {N_NULL} null_feat)")

    t0 = time.time()
    sc = judge(model, tok, prompts, OPT, bs=a.batch)
    print(f"[done] {(time.time()-t0)/60:.1f} min")

    grade = [OPTS[int(np.argmax(s))] for s in sc]
    cov = [g in COVERED for g in grade]
    # continuous score for AUC: covered-mass minus not-covered-mass
    cont = [float(torch.logsumexp(torch.tensor(s[:2]), 0)
                  - torch.logsumexp(torch.tensor(s[2:]), 0)) for s in sc]

    agg = defaultdict(lambda: {"matched": None, "grade": None,
                                "null_expl": [], "null_feat": []})
    for (i, f, arm), g, c, m in zip(key, grade, cov, cont):
        if arm == "matched":
            agg[(i, f)]["matched"] = m
            agg[(i, f)]["grade"] = g
        else:
            agg[(i, f)][arm].append(c)

    rows = []
    for (i, f), d in agg.items():
        ne = float(np.mean([x > 0 for x in d["null_expl"]])) if d["null_expl"] else 0.0
        nf = float(np.mean([x > 0 for x in d["null_feat"]])) if d["null_feat"] else 0.0
        u = units[i]
        bucket = "shared" if f in u["shared"] else "lost" if f in u["lost"] else "made"
        if d["grade"] not in COVERED:
            verdict = "not_present"
        elif ne > UNKNOWN_AT or nf > UNKNOWN_AT:
            verdict = "unknown"
        else:
            verdict = "present"
        rows.append({"unit": i, "corpus": u["corpus"], "act": u["act"],
                      "variant": u.get("variant", "full"), "feature": f,
                     "bucket": bucket, "verdict": verdict, "grade": d["grade"],
                     # The label itself, not just its id. Without it every reader
                     # has to join this file against feature_labels.json by hand
                     # to find out what any row is actually about.
                     "label": usable[f]["label"],
                     "matched": d["matched"], "null_expl_rate": ne, "null_feat_rate": nf,
                     "label_auc": usable[f].get("auc"), "categories": usable[f]["categories"]})

    # ================= VALIDATION =================
    print("\n" + "=" * 78)
    print("IS THE MATCHER TRUSTWORTHY?")
    print("=" * 78)
    mt = [c for (i, f, arm), c in zip(key, cont) if arm == "matched"]
    ne_ = [c for (i, f, arm), c in zip(key, cont) if arm == "null_expl"]
    nf_ = [c for (i, f, arm), c in zip(key, cont) if arm == "null_feat"]
    nf_cov = [q for (i, f, arm), q in zip(key, cov) if arm == "null_feat"]
    fpr = float(np.mean(nf_cov))
    print(f"FALSE-POSITIVE RATE   {100*fpr:>5.1f}%   features that did NOT fire, judged covered")
    print(f"                              (baseline prompt scored 78.3% here)")
    print(f"MATCHER AUC           {auc(mt, ne_):>5.3f}   vs unrelated explanations")
    print(f"                      {auc(mt, nf_):>5.3f}   vs non-firing features")
    byact = defaultdict(lambda: defaultdict(list))
    for r in rows:
        byact[(r["corpus"], r["act"])][r["feature"]].append(r["verdict"])
    agree = [Counter(v).most_common(1)[0][1] / len(v)
             for fs in byact.values() for v in fs.values() if len(v) > 1]
    if agree:
        print(f"SELF-CONSISTENCY      {100*np.mean(agree):>5.1f}%   across the 5 explanations "
              f"of one activation")

    print(f"\n{'grade':<10}{'on real':>9}{'on non-firing':>15}{'% real':>9}")
    gr_real = Counter(g for (i, f, arm), g in zip(key, grade) if arm == "matched")
    gr_fake = Counter(g for (i, f, arm), g in zip(key, grade) if arm == "null_feat")
    base = sum(gr_real.values()) / (sum(gr_real.values()) + sum(gr_fake.values()))
    for g in OPTS:
        r, k = gr_real[g], gr_fake[g]
        if r + k:
            print(f"{g:<10}{r:>9}{k:>15}{100*r/(r+k):>8.0f}%")
    print(f"base rate {100*base:.0f}%. Grades at or below base carry no information.")

    # ================= RESULTS =================
    print("\n" + "=" * 78)
    print("WHAT THE AV COVERS  (features actually IN the activation)")
    print("=" * 78)
    real = [r for r in rows if r["bucket"] in ("shared", "lost")]
    print(f"{'bucket':<12}{'n':>7}{'present':>10}{'not present':>13}{'unknown':>10}")
    for b in ("shared", "lost", "made", "ALL-real"):
        sub = real if b == "ALL-real" else [r for r in rows if r["bucket"] == b]
        if not sub:
            continue
        c = Counter(r["verdict"] for r in sub)
        print(f"{b:<12}{len(sub):>7}{100*c['present']/len(sub):>9.0f}%"
              f"{100*c['not_present']/len(sub):>12.0f}%{100*c['unknown']/len(sub):>9.0f}%")
    print(f"\nFPR floor is {100*fpr:.0f}%, so a present rate of p means roughly")
    print(f"(p - {fpr:.3f})/(1 - {fpr:.3f}) of features are genuinely covered.")

    print("\n" + "=" * 78)
    print("BY CATEGORY, WITH LABEL CONFIDENCE")
    print("=" * 78)
    print(f"{'category':<16}{'n':>6}{'present':>9}{'not pres':>10}{'unknown':>9}"
          f"{'AUC pres':>10}{'AUC not':>9}")
    bycat = defaultdict(list)
    for r in real:
        for c in r["categories"]:
            bycat[c].append(r)

    def mauc(sub, v):
        x = [r["label_auc"] for r in sub if r["verdict"] == v and r["label_auc"] is not None]
        return f"{np.mean(x):.3f}" if x else "  -  "

    for cat, sub in sorted(bycat.items(), key=lambda kv: -len(kv[1])):
        c = Counter(r["verdict"] for r in sub)
        print(f"{cat:<16}{len(sub):>6}{100*c['present']/len(sub):>8.0f}%"
              f"{100*c['not_present']/len(sub):>9.0f}%{100*c['unknown']/len(sub):>8.0f}%"
              f"{mauc(sub,'present'):>10}{mauc(sub,'not_present'):>9}")

    print("\n" + "=" * 78)
    print("DOES THE VERDICT TRACK LABEL QUALITY?")
    print("=" * 78)
    print(f"{'label AUC band':<18}{'n':>7}{'present':>10}{'not present':>13}{'unknown':>10}")
    for lo, hi in ((0.5, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)):
        sub = [r for r in real if r["label_auc"] is not None and lo <= r["label_auc"] < hi]
        if not sub:
            continue
        c = Counter(r["verdict"] for r in sub)
        print(f"{f'{lo:.1f}-{hi:.1f}':<18}{len(sub):>7}{100*c['present']/len(sub):>9.0f}%"
              f"{100*c['not_present']/len(sub):>12.0f}%{100*c['unknown']/len(sub):>9.0f}%")
    ga = defaultdict(list)
    for r in real:
        if r["label_auc"] is not None:
            ga[r["grade"]].append(r["label_auc"])
    print(f"\nmean label AUC by grade: " +
          "  ".join(f"{g} {np.mean(ga[g]):.3f} (n={len(ga[g])})" for g in OPTS if ga[g]))
    print("Rising present% with label AUC = better-labelled features are found")
    print("more often. That is the expected direction and a check on the pipeline.")

    Path(a.out).write_text(json.dumps({
        "config": vars(a),
        "validation": {"false_positive_rate": fpr,
                        "matcher_auc_vs_null_expl": auc(mt, ne_),
                        "matcher_auc_vs_null_feat": auc(mt, nf_),
                        "self_consistency": float(np.mean(agree)) if agree else None,
                        "grades_on_real": dict(gr_real), "grades_on_nonfiring": dict(gr_fake)},
        "rows": rows,
        "units": [{k: (sorted(v) if isinstance(v, set) else v) for k, v in u.items()}
                   for u in units]}, indent=2))
    print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()
