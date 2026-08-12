"""Compute every number reported in RESULTS.md, from the artefacts, in one place.

WHY THIS EXISTS
The reported numbers used to be produced by ad-hoc one-liners at analysis time.
That is how four errors reached the write-up before being caught by hand:

  * a false-positive correction applied in the WRONG DIRECTION (43% quoted where
    the corrected figure was 38.7%, because correcting *lowers* the number)
  * P(conveyed | shared) reported as if it were P(shared | conveyed) -- the
    backwards conditional, which supports a different claim entirely
  * an FVE-vs-cosine multiplier borrowed from a run with a different `rawvar`
  * pooled significance over 3,032 pairs that actually come from 50 activations,
    overstating confidence by ~2.5x

Every one of those was a number that looked right. So the numbers now come from
one script that is read once and reused, and the two output files are the only
place the write-up should ever quote from.

WHAT IT WRITES
  summary.json   machine-readable: every reported quantity, keyed and nested
  SUMMARY.md     the same numbers as tables, to paste or check against

STATISTICAL CHOICES, MADE ONCE HERE
  * bucket comparisons are computed PER ACTIVATION and then compared across
    activations (paired t over ~50 numbers), never pooled over pairs. Pairs from
    one activation are not independent draws -- see METHODOLOGY.md section 5.
  * conveyance rates are corrected for the judge's measured false-positive rate
    as (p - fpr) / (1 - fpr), which always LOWERS the figure.
  * no test is run on the two SAE rows: they are the same pairs read twice.

Usage:
    python src/summarize_results.py --dir results
"""

from __future__ import annotations

import argparse
import json
import math
import statistics as st
from collections import defaultdict
from pathlib import Path


# ---------------------------------------------------------------- small stats

def mean_ci(xs: list[float], z: float = 1.96) -> dict:
    """Mean, standard error, t, and a 95% CI over a list of per-activation values."""
    n = len(xs)
    if n < 2:
        return {"n": n, "mean": xs[0] if xs else None, "ci": None, "t": None}
    m, sd = st.mean(xs), st.stdev(xs)
    se = sd / math.sqrt(n)
    return {
        "n": n,
        "mean": m,
        "sd": sd,
        "se": se,
        "t": m / se if se else None,
        "ci_low": m - z * se,
        "ci_high": m + z * se,
        "significant": bool(se and abs(m / se) > z),
    }


def two_prop_z(k1: int, n1: int, k2: int, n2: int) -> float | None:
    """Pooled two-proportion z. Reported ONLY to show how much pooling inflates."""
    if not n1 or not n2:
        return None
    p1, p2 = k1 / n1, k2 / n2
    p = (k1 + k2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    return (p1 - p2) / se if se else None


# ---------------------------------------------------------------- the sections

def reconstruction(ov: dict) -> dict:
    """Section 1: the four FVE comparisons, plus the cosine/L0 they imply."""
    fve, rawvar = ov["fve"], ov["rawvar"]
    # FVE = 1 - 2(1-cos)/rawvar, so cos is FIXED once FVE is known. Reported for
    # readability only -- it is NOT independent evidence.
    cos = {k: 1 - (1 - v) * rawvar / 2 for k, v in fve.items()}
    t = ov["totals"]

    # THE MEAN FVE IS NOT THE TYPICAL FVE. rawvar is ~0.028 here, so FVE
    # multiplies any cosine gap by ~71x, and the mean inherits every outlier at
    # that weight. In one run the mean was 0.688 while the median was 0.774 --
    # the whole difference was three activations out of fifty whose cosine was
    # 0.978 instead of 0.997. Reporting only the mean makes a handful of hard
    # cases look like a systematically worse model. Both go in the summary.
    b = sorted(r["fve_B"] for r in ov.get("runs", []) if r.get("fve_B") is not None)
    dist = None
    if b:
        q = lambda p: b[min(int(p * len(b)), len(b) - 1)]
        dist = {
            "n": len(b),
            "mean": st.mean(b),
            "median": st.median(b),
            "p10": q(0.10), "p25": q(0.25), "p75": q(0.75), "p90": q(0.90),
            "min": b[0], "max": b[-1],
            "n_below_zero": sum(x < 0 for x in b),
            "trimmed_mean_5pct": st.mean(b[max(1, len(b) // 20):
                                           len(b) - max(1, len(b) // 20)]),
        }
    # THE CONTROL FOR ROW B. Every other section reports its measurement against
    # a null; section 1 used to be the exception, and an FVE with nothing beside
    # it gives no way to tell "the round trip preserved this activation" from
    # "any activation from this corpus scores about this well". The control is
    # the AR's reconstruction scored against a DIFFERENT activation, offset half
    # the set away, the same mismatch the latent-overlap control uses.
    # Absent from artefacts written before roundtrip.py computed it.
    ctl = [r["fve_B_control_wrong_expl"] for r in ov.get("runs", [])
           if r.get("fve_B_control_wrong_expl") is not None]
    control = None
    if ctl:
        control = {
            "fve_B_control": st.mean(ctl),
            "gap_B_minus_control": fve["B_ar_vs_orig"] - st.mean(ctl),
            "n": len(ctl),
        }

    return {
        "fve": fve,
        "cos_implied": cos,
        "rawvar": rawvar,
        "fve_multiplier": 2 / rawvar,        # 0.001 of cosine moves FVE by this/1000
        "mismatched_control": control,
        "fve_B_distribution": dist,
        "gap_B_minus_A": fve["B_ar_vs_orig"] - fve["A_sae_orig_vs_orig"],
        "gap_C_minus_A": fve["C_sae_ar_vs_ar"] - fve["A_sae_orig_vs_orig"],
        "L0_orig": t["n_orig"],
        "L0_ar": t["n_ar"],
        "sae_used": "l0_big",
    }


def overlap(sm: dict, bg: dict) -> dict:
    """Section 2: latent counts and the mismatched control, per SAE."""
    out = {}
    for j in (sm, bg):
        runs = j["runs"]
        sh = sum(len(r["shared_features"]) for r in runs)
        lo = sum(len(r["lost_features"]) for r in runs)
        md = sum(len(r["invented_features"]) for r in runs)
        tot = sh + lo + md
        t = j["totals"]
        out[j["sae"]] = {
            "n_pairs": len(runs),
            "n_activations": len({r["act"] for r in runs}),
            "totals": {"shared": sh, "lost": lo, "made": md, "all": tot},
            "mean_per_pair": {"shared": sh / len(runs), "lost": lo / len(runs),
                              "made": md / len(runs)},
            "share_of_all": {"shared": sh / tot, "lost": lo / tot, "made": md / tot},
            "kept": sh / (sh + lo),
            "jaccard_matched": t["jaccard"],
            "jaccard_control": t["control"],
            "separation_ratio": t["jaccard"] / t["control"],
        }
    return out


def labels(lab: dict) -> dict:
    """Section 3 preamble: how many labels survive validation, and at what AUC."""
    vals = [v for v in lab.values() if isinstance(v, dict)]
    auc = [v["auc"] for v in vals if v.get("auc") is not None]
    null = [x for v in vals for x in (v.get("auc_null") or [])
            if isinstance(x, (int, float))]
    kept = [v["auc"] for v in vals if v.get("reliable")]
    return {
        "attempted": len(vals),
        "validated": len(kept),
        "validated_frac": len(kept) / len(vals) if vals else None,
        "mean_auc_all": st.mean(auc) if auc else None,
        "mean_auc_validated": st.mean(kept) if kept else None,
        "median_auc_validated": st.median(kept) if kept else None,
        "mean_auc_wrong_label_null": st.mean(null) if null else None,
        "n_perfect": sum(1 for a in kept if a >= 0.999),
    }


def conveyance(rows: list[dict], fpr: float) -> dict:
    """Section 3: does the explanation cover each latent?

    Bucket comparisons are computed PER ACTIVATION and compared across them.
    The pooled z is also reported, solely to document how much pooling inflates.
    """
    by_bucket, per_act = {}, defaultdict(list)
    for r in rows:
        per_act[r["act"]].append(r)

    for b in ("shared", "lost", "made"):
        s = [r for r in rows if r["bucket"] == b]
        k = sum(1 for r in s if r["verdict"] == "present")
        aucs = [r["label_auc"] for r in s if r.get("label_auc") is not None]
        # Each bucket gets its OWN chance rate, not just the global one. If
        # `shared` latents happened to be more generic than `lost` ones, an
        # arbitrary explanation would match them more often by accident, and the
        # shared-vs-lost gap computed below would be that artefact rather than a
        # result. So both nulls are broken out per bucket, and the gap is only
        # interpretable if they come back flat:
        #   null_feat -- a latent that did NOT fire, judged against the real
        #     explanation. The judge's own false-positive floor.
        #   null_expl -- a latent that DID fire, judged against three unrelated
        #     explanations. The chance-match floor.
        nf = [r["null_feat_rate"] for r in s if r.get("null_feat_rate") is not None]
        ne = [r["null_expl_rate"] for r in s if r.get("null_expl_rate") is not None]
        m_ne = st.mean(ne) if ne else None
        by_bucket[b] = {
            "n": len(s),
            "conveyed": k,
            "rate": k / len(s) if s else None,
            "mean_label_auc": st.mean(aucs) if aucs else None,
            "null_feat_rate": st.mean(nf) if nf else None,
            "null_expl_rate": m_ne,
            "over_null_expl": (k / len(s)) / m_ne if s and m_ne else None,
        }

    # The bucket comparison is only meaningful if chance does not itself vary by
    # bucket. Recorded as a number so a later run cannot quietly violate it.
    _ne = [d["null_expl_rate"] for d in by_bucket.values()
           if d["null_expl_rate"] is not None]
    null_spread = (max(_ne) - min(_ne)) if _ne else None

    # REAL = shared + lost = latents genuinely in the original activation.
    # `made` is excluded because those are not in the original at all.
    real = [r for r in rows if r["bucket"] in ("shared", "lost")]
    k_real = sum(1 for r in real if r["verdict"] == "present")
    p_real = k_real / len(real) if real else None
    # Correcting for the judge's false positives REMOVES its mistaken hits, so
    # this always goes DOWN. An earlier write-up quoted a corrected figure that
    # was higher than the raw one, which is arithmetically impossible.
    corrected = (p_real - fpr) / (1 - fpr) if p_real is not None else None

    comparisons = {}
    for b1, b2 in (("shared", "lost"), ("shared", "made"), ("made", "lost")):
        diffs = []
        for rs in per_act.values():
            x = [r for r in rs if r["bucket"] == b1]
            y = [r for r in rs if r["bucket"] == b2]
            if not x or not y:
                continue
            diffs.append(sum(1 for r in x if r["verdict"] == "present") / len(x)
                         - sum(1 for r in y if r["verdict"] == "present") / len(y))
        clustered = mean_ci(diffs)
        pooled = two_prop_z(by_bucket[b1]["conveyed"], by_bucket[b1]["n"],
                            by_bucket[b2]["conveyed"], by_bucket[b2]["n"])
        comparisons[f"{b1}_vs_{b2}"] = {
            "clustered": clustered,          # <- the figure to report
            "pooled_z": pooled,              # <- for the inflation note only
            "inflation": (abs(pooled / clustered["t"])
                          if pooled and clustered.get("t") else None),
        }

    # The 2x2 of mentioned x outcome. Every cell is derivable from the bucket
    # rates above, so it is stored but NOT reported as a separate finding.
    cs = sum(1 for r in real if r["verdict"] == "present" and r["bucket"] == "shared")
    cl = sum(1 for r in real if r["verdict"] == "present" and r["bucket"] == "lost")
    us = sum(1 for r in real if r["verdict"] != "present" and r["bucket"] == "shared")
    ul = sum(1 for r in real if r["verdict"] != "present" and r["bucket"] == "lost")

    return {
        "n_pairs": len(rows),
        "n_activations": len(per_act),
        "by_bucket": by_bucket,
        "real": {"n": len(real), "rate": p_real,
                 "rate_corrected_for_fpr": corrected, "fpr_used": fpr},
        "shared_over_fpr_floor": (by_bucket["shared"]["rate"] / fpr) if fpr else None,
        "null_expl_spread_across_buckets": null_spread,
        "comparisons": comparisons,
        "mentioned_x_outcome": {
            "mentioned_shared": cs, "mentioned_lost": cl,
            "unmentioned_shared": us, "unmentioned_lost": ul,
            "p_shared_given_mentioned": cs / (cs + cl) if cs + cl else None,
            "p_shared_given_unmentioned": us / (us + ul) if us + ul else None,
            "frac_of_shared_unmentioned": us / (cs + us) if cs + us else None,
        },
    }


def judge_validation(g: dict) -> dict:
    """The judge's own error rates -- the floor everything in section 3 sits on."""
    v = dict(g.get("validation") or {})
    grades = defaultdict(lambda: {"real": 0, "null": 0})
    for r in g["rows"]:
        if r.get("grade"):
            grades[r["grade"]]["real"] += 1
    v["grades_on_real"] = {k: x["real"] for k, x in grades.items()}
    return v


# ---------------------------------------------------------------- rendering

def render_md(s: dict) -> str:
    r, o, l, c = s["reconstruction"], s["overlap"], s["labels"], s["conveyance"]
    L = ["# Summary of results",
         "",
         "Generated by `src/summarize_results.py`. **Every number quoted in "
         "`RESULTS.md` should come from here.**",
         "",
         f"- {s['meta']['n_activations']} activations x "
         f"{s['meta']['runs_per_activation']} explanations = "
         f"{s['meta']['n_pairs']} pairs",
         (f"- **{s['meta']['n_documents']} distinct conversations** — "
          + ("one activation each, so the activations are independent samples"
             if s["meta"]["independent"] else
             f"**{s['meta']['n_activations'] - s['meta']['n_documents']} "
             f"activations share a conversation with another, so they are NOT "
             f"independent and every interval below is too narrow**")
          if s["meta"]["n_documents"] else
          "- *(no doc_id in this run — independence unverifiable)*"),
         "",
         "## 1. Reconstruction (SAE: l0_big)", "",
         "| | FVE | implied cosine |", "|---|---:|---:|"]
    names = {"A_sae_orig_vs_orig": "A  SAE vs original",
             "B_ar_vs_orig": "B  NLA round trip vs original",
             "C_sae_ar_vs_ar": "C  SAE vs AR output",
             "D_sae_ar_vs_orig": "D  SAE(AR) vs original"}
    for k, nm in names.items():
        L.append(f"| {nm} | {r['fve'][k]:.4f} | {r['cos_implied'][k]:.5f} |")
    if r.get("mismatched_control"):
        mc = r["mismatched_control"]
        L.append(f"| *B control — AR vs a DIFFERENT activation* | "
                 f"*{mc['fve_B_control']:.4f}* | |")
    L += ["",
          f"- **B - A = {r['gap_B_minus_A']:+.4f}**",]
    if r.get("mismatched_control"):
        mc = r["mismatched_control"]
        L += [f"- **B - control = {mc['gap_B_minus_control']:+.4f}** — row B is "
              f"scored against the activation it came from; the control scores the "
              f"same reconstruction against an unrelated one. If these were close, "
              f"row B would be measuring the corpus rather than the round trip."]
    L += [
          f"- **C - A = {r['gap_C_minus_A']:+.4f}**",
          f"- L0: original {r['L0_orig']:.1f}, AR output {r['L0_ar']:.1f}",
          f"- `rawvar` {r['rawvar']:.4f}, so FVE = 1 - "
          f"{r['fve_multiplier']:.1f}x(1-cos)"]
    if r.get("fve_B_distribution"):
        b = r["fve_B_distribution"]
        L += ["",
              "### How row B is distributed across the individual pairs", "",
              "The mean above is not the typical pair. With a "
              f"{r['fve_multiplier']:.0f}x multiplier a single activation whose "
              "cosine is a couple of points low drags the mean a long way, so "
              "the median is the better summary of what happens to a typical "
              "activation.", "",
              "| min | p10 | p25 | **median** | mean | p75 | p90 | max |",
              "|---:|---:|---:|---:|---:|---:|---:|---:|",
              f"| {b['min']:+.3f} | {b['p10']:+.3f} | {b['p25']:+.3f} | "
              f"**{b['median']:+.3f}** | {b['mean']:+.3f} | {b['p75']:+.3f} | "
              f"{b['p90']:+.3f} | {b['max']:+.3f} |", "",
              f"- {b['n']:,} pairs; **{b['n_below_zero']}** score below 0 "
              f"(worse than predicting the corpus mean)",
              f"- 5% trimmed mean **{b['trimmed_mean_5pct']:+.4f}**"]
    L += ["", "## 2. Latent overlap", "",
          "| | " + " | ".join(o) + " |", "|---|" + "---:|" * len(o)]
    for row, fmt in (("shared", "{:,}"), ("lost", "{:,}"), ("made", "{:,}")):
        L.append(f"| {row} (total) | " + " | ".join(
            fmt.format(o[k]["totals"][row]) for k in o) + " |")
    for row in ("shared", "lost", "made"):
        L.append(f"| {row} (share) | " + " | ".join(
            f"{100*o[k]['share_of_all'][row]:.1f}%" for k in o) + " |")
    for lbl, key, f in (("kept", "kept", "{:.1%}"),
                        ("Jaccard matched", "jaccard_matched", "{:.3f}"),
                        ("Jaccard control", "jaccard_control", "{:.4f}"),
                        ("separation", "separation_ratio", "{:.0f}x")):
        L.append(f"| **{lbl}** | " + " | ".join(f.format(o[k][key]) for k in o) + " |")

    L += ["", "## 3. Labels", "",
          f"- attempted **{l['attempted']:,}**, validated **{l['validated']:,}** "
          f"({l['validated_frac']:.0%})",
          f"- mean AUC over all attempts **{l['mean_auc_all']:.3f}**, "
          f"validated only **{l['mean_auc_validated']:.3f}**",
          f"- wrong-label null **{l['mean_auc_wrong_label_null']:.3f}**",
          "", "## 4. Conveyance", "",
          "| bucket | n | conveyed | null_feat | null_expl | vs null_expl | mean label AUC |",
          "|---|---:|---:|---:|---:|---:|---:|"]
    for b in ("shared", "made", "lost"):
        d = c["by_bucket"][b]
        L.append(f"| {b} | {d['n']:,} | {d['rate']:.1%} | {d['null_feat_rate']:.1%} | "
                 f"{d['null_expl_rate']:.1%} | {d['over_null_expl']:.1f}x | "
                 f"{d['mean_label_auc']:.3f} |")
    L += [f"| **REAL** (shared+lost) | {c['real']['n']:,} | "
          f"{c['real']['rate']:.1%} | | | | |",
          "",
          f"- corrected for the judge's {c['real']['fpr_used']:.2%} false-positive "
          f"rate: **{c['real']['rate_corrected_for_fpr']:.1%}** "
          f"(correcting always lowers the raw {c['real']['rate']:.1%})",
          f"- `shared` is **{c['shared_over_fpr_floor']:.1f}x** the "
          f"false-positive floor",
          "",
          "**The two null columns are the check on the bucket comparison below.** "
          "`null_feat` is a latent that did not fire, judged against the real "
          "explanation; `null_expl` is a latent that did fire, judged against "
          "unrelated explanations. If chance were higher for `shared` than for "
          "`lost`, the gap below would be an artefact of `shared` latents simply "
          "being more generic. Spread across buckets here: "
          f"**{100 * c['null_expl_spread_across_buckets']:.1f} pts** "
          f"({'flat -- the comparison stands' if c['null_expl_spread_across_buckets'] < 0.05 else 'NOT FLAT -- the bucket comparison below is confounded, do not quote it'}).",
          "",
          "### Bucket comparisons (per activation, then across activations)", "",
          "| comparison | difference | 95% CI | t | n acts | pooled z |",
          "|---|---:|---|---:|---:|---:|"]
    for k, d in c["comparisons"].items():
        cl = d["clustered"]
        ci = (f"[{100*cl['ci_low']:+.1f}, {100*cl['ci_high']:+.1f}]"
              if cl.get("ci_low") is not None else "-")
        L.append(f"| {k.replace('_', ' ')} | {100*cl['mean']:+.1f} pts | {ci} | "
                 f"{cl['t']:.2f} | {cl['n']} | {d['pooled_z']:.1f} |")
    m = c["mentioned_x_outcome"]
    L += ["",
          "*Pooled z is shown only to document the inflation; the clustered "
          "figures are the ones to quote.*",
          "",
          "### Mentioned x outcome (derivable from the rates above)", "",
          "| | shared | lost |", "|---|---:|---:|",
          f"| mentioned | {m['mentioned_shared']:,} | {m['mentioned_lost']:,} |",
          f"| not mentioned | {m['unmentioned_shared']:,} | {m['unmentioned_lost']:,} |",
          "",
          f"- **{m['frac_of_shared_unmentioned']:.0%} of `shared` latents were "
          f"never mentioned** in the explanation",
          "", "## 5. Judge validation", ""]
    for k, v in s["judge"].items():
        if isinstance(v, (int, float)):
            L.append(f"- {k}: **{v:.3f}**")
    return "\n".join(L) + "\n"


def render_by_bucket(ov: dict, sm: dict, lab: dict, gr: list | None = None) -> str:
    """Per-activation dump: the explanation, the source text, and every labelled
    latent grouped by what the round trip did with it.

    Nothing here is inferred. The labels are what each detector responds to, and
    they are simply listed under the bucket the set arithmetic put them in. This
    is the file to read when a number looks surprising and you want to see the
    actual case behind it.

    Each latent also carries the matcher's verdict -- whether the AV's
    explanation actually STATES that latent. Bucket and verdict answer different
    questions, and the interesting rows are the ones where they disagree: a
    SHARED latent the explanation never mentioned survived on the AR's inference
    rather than on anything the AV wrote.

    It used to be produced by hand, which meant it could not be regenerated with
    the rest of the results. Now it comes out of the same run as everything else.
    """
    val = {int(k): v for k, v in lab.items()
           if isinstance(v, dict) and v.get("reliable") and v.get("label")}
    # one explanation per activation -- buckets differ per sampled explanation,
    # so mixing them would put one latent in two buckets on the same page
    first, seen = [], set()
    for r in sm["runs"]:
        if r["act"] not in seen:
            seen.add(r["act"])
            first.append(r)
    expl = {}
    for r in ov["runs"]:
        expl.setdefault(r["act"], r)
    # (activation, latent) -> the matcher's grade, so bucket and verdict appear
    # side by side instead of in two files joined by hand
    verdict = {(g["act"], g["feature"]): g for g in (gr or [])}

    L = ["# What each latent is about — shared vs lost vs made", "",
         "Every validated latent label, grouped by what the round trip did with "
         "it. **Nothing here is inferred by a model** — the labels are what each "
         "detector responds to, listed under the bucket set arithmetic put them "
         "in.", "",
         f"Unlabelled latents are counted everywhere but cannot be shown: only "
         f"{len(val):,} of {len(lab):,} earned a validated label.", ""]
    for r in sorted(first, key=lambda x: x["act"]):
        i = r["act"]
        e = expl.get(i, {})
        L += ["---", "", f"## Activation {i}", ""]
        if e.get("prompt"):
            L += ["**The prompt Gemma was given:**", "",
                  "> " + " ".join(e["prompt"].split()), ""]
        if e.get("response"):
            L += ["<details><summary><b>Gemma's full response</b> "
                  f"(the activation is at token {e.get('activation_token_index','?')})"
                  "</summary>", "",
                  "> " + " ".join(e["response"].split()).replace("\n", " "), "",
                  "</details>", ""]
        if e.get("source_text"):
            L += [f"**Context the activation encodes (its last 600 chars):** "
                  f"…{' '.join(e['source_text'].split())[-600:]}", ""]
        if e.get("explanation"):
            L += [f"**What the AV said about it:** "
                  f"{' '.join(e['explanation'].split())}", ""]
        for name, key, gloss in (("SHARED", "shared_features", "survived"),
                                 ("LOST", "lost_features", "destroyed"),
                                 ("MADE", "invented_features", "invented")):
            fs = r[key]
            named = [f for f in fs if f in val]
            L.append(f"### {name} — {gloss}  · {len(named)} labelled, "
                     f"{len(fs) - len(named)} unlabelled")
            L.append("")
            # THREE verdicts, not two. `unknown` means one of the two controls
            # fired -- the same latent also matched unrelated explanations, or
            # this explanation also matched latents that never fired -- so the
            # measurement refused itself. Rendering that as "not stated" would
            # turn a failed measurement into evidence about the AV.
            tally = {"present": 0, "not_present": 0, "unknown": 0}
            for f in named:
                v = verdict.get((i, f))
                vd = v.get("verdict") if v else None
                if vd in tally:
                    tally[vd] += 1
                tag = {"present": f"  **[stated — {v['grade'] if v else ''}]**",
                       "not_present": "  *[not stated]*",
                       "unknown": "  *[controls fired — cannot tell]*"}.get(vd, "")
                L.append(f"- `f{f}` {val[f]['label']}{tag}")
            if named and verdict:
                bits = [f"{tally['present']} stated",
                        f"{tally['not_present']} not stated"]
                if tally["unknown"]:
                    bits.append(f"{tally['unknown']} undecidable")
                L.append("")
                L.append(f"*Of {len(named)} named {name.lower()} latents: "
                         + ", ".join(bits) + ".*")
            L.append("")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- entry point

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default="results", help="directory of artefacts")
    ap.add_argument("--out", default=None, help="defaults to <dir>/summary.json")
    a = ap.parse_args()
    d = Path(a.dir)

    ov = json.loads((d / "feature_overlap.json").read_text())
    sm = json.loads((d / "feature_overlap_l0_small.json").read_text())
    bg = json.loads((d / "feature_overlap_l0_big.json").read_text())
    lab = json.loads((d / "feature_labels.json").read_text())
    gr = json.loads((d / "grounding.json").read_text())

    fpr = float((gr.get("validation") or {}).get("false_positive_rate", 0.057))

    n_acts = len({r["act"] for r in ov["runs"]})
    # HOW MANY INDEPENDENT SAMPLES IS THIS REALLY? Two activations from the same
    # Gemma conversation share nearly all their context, so they are one cluster,
    # not two observations. An earlier run had 50 activations from 30
    # conversations and nothing in any artefact said so, while every confidence
    # interval below was computed as if all 50 were independent.
    docs = {r.get("doc_id") for r in ov["runs"] if r.get("doc_id")}
    n_docs = len(docs) or None
    summary = {
        "meta": {
            "n_activations": n_acts,
            "n_documents": n_docs,
            "independent": (n_docs == n_acts) if n_docs else None,
            "n_pairs": len(ov["runs"]),
            "runs_per_activation": len(ov["runs"]) // max(n_acts, 1),
            "source": str(d.resolve()),
        },
        "reconstruction": reconstruction(ov),
        "overlap": overlap(sm, bg),
        "labels": labels(lab),
        "conveyance": conveyance(gr["rows"], fpr),
        "judge": judge_validation(gr),
    }

    out = Path(a.out) if a.out else d / "summary.json"
    out.write_text(json.dumps(summary, indent=2))
    (d / "SUMMARY.md").write_text(render_md(summary))

    # Per-example table. Everything the round trip recorded for each (activation,
    # explanation) pair, one row each, so a reader can check any single case
    # without parsing JSON -- and so a claim about "the outliers" can be checked.
    cols = ["act", "run", "row", "fve_A", "fve_B", "fve_C", "fve_D",
            "cos_A_sae_orig_vs_orig", "cos_B_ar_vs_orig",
            "cos_C_sae_ar_vs_ar", "cos_D_sae_ar_vs_orig",
            "n_orig", "n_ar", "n_shared", "n_lost", "n_invented",
            "jaccard", "control_jaccard", "weighted_kept", "cjk", "untagged"]
    lines = [",".join(cols)]
    for r in ov["runs"]:
        lines.append(",".join(
            "" if r.get(c) is None else
            (f"{r[c]:.6f}" if isinstance(r.get(c), float) else str(r.get(c)))
            for c in cols))
    (d / "per_example.csv").write_text("\n".join(lines) + "\n")

    (d / "LATENTS_BY_BUCKET.md").write_text(
        render_by_bucket(ov, sm, lab, gr.get("rows")))

    print(f"wrote {out}")
    print(f"wrote {d / 'SUMMARY.md'}")
    print(f"wrote {d / 'per_example.csv'}  ({len(ov['runs'])} rows)")
    print(f"wrote {d / 'LATENTS_BY_BUCKET.md'}")
    print()
    print(render_md(summary))


if __name__ == "__main__":
    main()
