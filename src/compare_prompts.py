"""Compare matcher prompts on the same pairs, and pick one by measurement.

NOT the ranking variant. matcher_bakeoff.py once tested a "Variant C" that showed
several latents in one prompt and asked for a ranking; it was rejected as a
measurement because it cannot produce a per-pair verdict. This file does the
SAME per-pair judgement judge_explanations.py does -- one latent, one
explanation, one question, answered CLEARLY / PROBABLY / UNCLEAR / NO -- and
varies only the prompt text.

WHY THIS EXISTS, SEPARATELY FROM matcher_bakeoff.py
That file chose the CURRENT prompt (A0) and measured the two things anyone
thought to check at the time: false-positive rate and AUC. A0 won on both, and
it deserved to -- it took FPR from 78.3% to 7.2%.

It was never checked for a third property, and that is where it fails.

    `full` is literally `no_final` + `final_only`. The paragraph split is a cut,
    not a rewrite. So anything a part covers, the whole must cover.

Measured on the 200-conversation run: 435 of 2,047 latents were judged covered
under the SUBSET and not covered under the SUPERSET, against 128 the legal way
round -- a 21.3% violation rate. Adding text makes "covered" LESS likely, so the
question A0 actually answers is salience within the text, not containment. That
makes conveyance rates incomparable across explanations of different lengths,
which is exactly the comparison the paragraph ablation needs.

A FOURTH BAR, ALSO NEW
FPR must not merely be low, it must be STABLE ACROSS VARIANTS. A0 gave 5.0% on
no_final, 5.4% on full and 11.5% on final_only. A judge whose error floor
doubles depending on which text it reads is reading style, not content -- and
paragraph 3 is where the AV lists ~7 candidate continuations, so there is simply
more surface for an accidental match.

WHAT IS HELD CONSTANT
Every prompt sees the SAME sampled activations, the SAME latents, the SAME
labels and the SAME null partners. The model is loaded once and reused. So the
only thing varying is the prompt text.

The null pool is stratified by variant here, as it now is in
judge_explanations.py: a null must differ from the matched arm in exactly one
respect -- that the latent does not belong to it -- and a mixed pool also varies
the text distribution, which inflates the floor of the stingy variants and
deflates the generous one's.

Usage:
    python src/compare_prompts.py --dirs results \
        --labels-json results/feature_labels.json --acts 60 --prompts A0 A B
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

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
from judge_explanations import (PROMPTS, OPTS, COVERED, N_NULL,  # noqa: E402
                                 UNKNOWN_AT, judge, auc)


def build(units, usable, seed, n_null=N_NULL):
    """The workload, built ONCE and reused for every prompt.

    Returns (key, spec) where spec carries the two texts each judgement needs.
    Identical across prompts, so any difference in the results is the prompt.
    """
    rng = np.random.default_rng(seed)
    key, spec = [], []
    for i, u in enumerate(units):
        own = u["shared"] | u["lost"] | u["made"]
        v = u.get("variant", "full")
        # same variant AND a different activation -- see the module docstring
        others = [j for j, w in enumerate(units)
                  if (w["corpus"], w["act"]) != (u["corpus"], u["act"])
                  and w.get("variant", "full") == v]
        absent = sorted(usable.keys() - own)
        for f in sorted(own & usable.keys()):
            desc = usable[f]["label"]
            key.append((i, f, "matched")); spec.append((u["explanation"], desc))
            for j in rng.choice(others, min(n_null, len(others)), replace=False):
                key.append((i, f, "null_expl"))
                spec.append((units[int(j)]["explanation"], desc))
            for gg in rng.choice(absent, min(n_null, len(absent)), replace=False):
                key.append((i, f, "null_feat"))
                spec.append((u["explanation"], usable[int(gg)]["label"]))
    return key, spec


def score_one(model, tok, opt_ids, tpl, spec, bs):
    return judge(model, tok, [tpl.format(expl=e, content=c) for e, c in spec],
                 opt_ids, bs=bs)


def evaluate(key, cont, units):
    """The four bars, from one prompt's raw option-logprobs."""
    grade = [OPTS[int(np.argmax(c))] for c in cont]
    cov = [g in COVERED for g in grade]
    margin = [c[0] - c[3] for c in cont]          # CLEARLY minus NO

    # per (unit, feature): matched grade + the two null rates
    d = defaultdict(lambda: {"matched": None, "null_expl": [], "null_feat": []})
    for (i, f, arm), g, cv, m in zip(key, grade, cov, margin):
        if arm == "matched":
            d[(i, f)]["matched"] = (g, cv)
        else:
            d[(i, f)][arm].append(cv)

    rows = []
    for (i, f), v in d.items():
        if v["matched"] is None:
            continue
        g, cv = v["matched"]
        ne = float(np.mean(v["null_expl"])) if v["null_expl"] else 0.0
        nf = float(np.mean(v["null_feat"])) if v["null_feat"] else 0.0
        verdict = ("not_present" if not cv
                   else "unknown" if (ne > UNKNOWN_AT or nf > UNKNOWN_AT)
                   else "present")
        u = units[i]
        rows.append({"act": u["act"], "feature": f,
                     "variant": u.get("variant", "full"),
                     "grade": g, "verdict": verdict,
                     "null_expl": ne, "null_feat": nf})

    mt = [m for (i, f, arm), m in zip(key, margin) if arm == "matched"]
    ne_ = [m for (i, f, arm), m in zip(key, margin) if arm == "null_expl"]
    nf_ = [m for (i, f, arm), m in zip(key, margin) if arm == "null_feat"]

    out = {"n_rows": len(rows),
           "auc_vs_null_expl": auc(mt, ne_), "auc_vs_null_feat": auc(mt, nf_),
           "by_variant": {}}
    for v in sorted({r["variant"] for r in rows}):
        s = [r for r in rows if r["variant"] == v]
        out["by_variant"][v] = {
            "n": len(s),
            "covered": sum(1 for r in s if r["grade"] in COVERED) / len(s),
            "present": sum(1 for r in s if r["verdict"] == "present") / len(s),
            "fpr": float(np.mean([r["null_feat"] for r in s])),
            "null_expl": float(np.mean([r["null_expl"] for r in s])),
        }

    # MONOTONICITY: full contains final_only verbatim, so covered(final_only)
    # must imply covered(full). Counted on grades, before the null rule, because
    # the rule is a separate stage and the contradiction lives in the grade.
    seen = defaultdict(dict)
    for r in rows:
        seen[(r["act"], r["feature"])][r["variant"]] = r["grade"] in COVERED
    both = [x for x in seen.values() if "full" in x and "final_only" in x]
    if both:
        viol = sum(1 for x in both if x["final_only"] and not x["full"])
        legal = sum(1 for x in both if x["full"] and not x["final_only"])
        out["monotonicity"] = {"n": len(both), "violations": viol, "legal": legal,
                                "violation_rate": viol / len(both)}
    fprs = [d_["fpr"] for d_ in out["by_variant"].values()]
    out["fpr_spread"] = (max(fprs) - min(fprs)) if fprs else None
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dirs", nargs="+", required=True)
    ap.add_argument("--names", nargs="+", default=None)
    ap.add_argument("--labels-json", required=True)
    ap.add_argument("--sae", default="l0_small")
    ap.add_argument("--acts", type=int, default=60, help="activations to sample")
    ap.add_argument("--prompts", nargs="+", default=["A0", "A", "B"])
    ap.add_argument("--model", default="google/gemma-3-12b-it")
    ap.add_argument("--max-expl-chars", type=int, default=1200)
    ap.add_argument("--batch", type=int, default=24)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="results/prompt_comparison.json")
    a = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)
    names = a.names or [Path(d).name for d in a.dirs]

    lab = json.loads(Path(a.labels_json).read_text())
    usable = {int(k): v for k, v in lab.items()
              if isinstance(v, dict) and v.get("reliable") and v.get("label")}
    print(f"[data] {len(usable)} validated labels")

    units = []
    for d, nm in zip(a.dirs, names):
        j = json.loads((Path(d) / f"feature_overlap_{a.sae}.json").read_text())
        for i, r in enumerate(j["runs"]):
            e = r.get("explanation")
            if not e:
                continue
            units.append({"corpus": nm, "act": r["act"], "run": i,
                           "variant": r.get("variant", "full"),
                           "explanation": e[:a.max_expl_chars],
                           "shared": set(r["shared_features"]),
                           "lost": set(r["lost_features"]),
                           "made": set(r["invented_features"])})
    keep = set(sorted({u["act"] for u in units})[:a.acts])
    units = [u for u in units if u["act"] in keep]
    print(f"[data] {len(units)} units over {len(keep)} activations, "
          f"variants {sorted({u['variant'] for u in units})}")

    key, spec = build(units, usable, a.seed)
    print(f"[work] {len(spec)} judgements PER PROMPT, {len(a.prompts)} prompts "
          f"= {len(spec)*len(a.prompts)} total\n")

    tok = AutoTokenizer.from_pretrained(a.model)
    tok.padding_side = "left"
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        a.model, dtype=torch.bfloat16).to("cuda").eval()
    opt_ids = [tok.encode(o, add_special_tokens=False)[0] for o in OPTS]
    assert len(set(opt_ids)) == len(opt_ids)

    res = {}
    for name in a.prompts:
        print(f"--- prompt {name} ---")
        t0 = time.time()
        cont = score_one(model, tok, opt_ids, PROMPTS[name], spec, a.batch)
        res[name] = evaluate(key, cont, units)
        print(f"    done in {(time.time()-t0)/60:.1f} min\n")

    print("=" * 78)
    print("RESULTS — the same pairs, judged under each prompt")
    print("=" * 78)
    print("\n%-6s %12s %10s %10s %11s %11s" %
          ("prompt", "MONOTONIC", "FPR spread", "AUC expl", "AUC feat", "n"))
    for n, r in res.items():
        m = r.get("monotonicity") or {}
        print("%-6s %11s %10.3f %10.3f %11.3f %11d" %
              (n, ("%.1f%% viol" % (100*m.get("violation_rate", float('nan')))),
               r["fpr_spread"], r["auc_vs_null_expl"], r["auc_vs_null_feat"],
               r["n_rows"]))
    print("\nper-variant covered rate / its own FPR:")
    for n, r in res.items():
        print("  %-4s " % n + "  ".join(
            "%s %.1f%%/%.1f%%" % (v, 100*d["covered"], 100*d["fpr"])
            for v, d in sorted(r["by_variant"].items())))
    print("\nBARS: monotonicity violations -> 0 | FPR spread across variants -> 0")
    print("      | AUC must not collapse (A0 measured 0.797 / 0.826)")

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(
        {"config": vars(a), "n_judgements_per_prompt": len(spec), "results": res},
        indent=2))
    print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()
