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


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx, my = st.mean(xs), st.mean(ys)
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    den = math.sqrt(sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys))
    return num / den if den else None


def _ranks(v: list[float]) -> list[float]:
    """Average ranks, so ties do not distort Spearman."""
    order = sorted(range(len(v)), key=lambda i: v[i])
    out = [0.0] * len(v)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        avg = (i + j) / 2
        for k in range(i, j + 1):
            out[order[k]] = avg
        i = j + 1
    return out


def corr(xs: list[float], ys: list[float]) -> dict:
    """Pearson + Spearman with a Fisher-z 95% CI on r.

    The CI is the point of this: with n around 200, |r| below about 0.14 cannot
    be told from zero, so a near-zero r must be reported as "no correlation
    DETECTABLE at this n", never as "no correlation".
    """
    n = len(xs)
    r = _pearson(xs, ys)
    out = {"n": n, "pearson": r, "spearman": _pearson(_ranks(xs), _ranks(ys))}
    if r is not None and n > 3 and abs(r) < 1:
        z = 0.5 * math.log((1 + r) / (1 - r))
        se = 1 / math.sqrt(n - 3)
        lo, hi = z - 1.96 * se, z + 1.96 * se
        out["ci_low"] = math.tanh(lo)
        out["ci_high"] = math.tanh(hi)
        out["detectable_floor"] = math.tanh(1.96 * se)
        out["significant"] = bool(out["ci_low"] > 0 or out["ci_high"] < 0)
    return out


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
    fve, rawvar = dict(ov["fve"]), ov["rawvar"]
    runs = ov.get("runs") or []

    # RECOMPUTE B/C/D FROM THE RUNS HANDED IN, rather than trusting the
    # top-level `fve` block. That block is fixed at variant="full", so the
    # paragraph ablation would otherwise report the same FVE for all three
    # variants -- which is exactly what it did before this, and it looked
    # perfectly plausible in the table. A is per-ACTIVATION, not per-run, so it
    # is left alone; the same activations underlie every variant.
    #
    # FVE is 1 - mean(mse)/rawvar, so it must be rebuilt from the mse values.
    # Averaging per-example FVEs would give a different number.
    _mse = lambda key: [r[key] for r in runs if r.get(key) is not None]
    for out_key, mse_key in (("B_ar_vs_orig", "mse_B_ar_vs_orig"),
                              ("C_sae_ar_vs_ar", "mse_C_sae_ar_vs_ar"),
                              ("D_sae_ar_vs_orig", "mse_D_sae_ar_vs_orig")):
        vals = _mse(mse_key) or (_mse("mse") if out_key == "B_ar_vs_orig" else [])
        if vals:
            fve[out_key] = 1.0 - st.mean(vals) / rawvar

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


def monotonicity(rows: list[dict]) -> dict | None:
    """Is the judge CONSISTENT about containment? Measured, not assumed.

    `full` is literally `no_final` + `final_only` -- the paragraph split is a cut,
    not a rewrite. So anything `final_only` covers, `full` must also cover: adding
    text cannot remove coverage. Any (activation, latent) judged covered under
    the SUBSET and not covered under the SUPERSET is a logical violation.

    Measured on the 200-conversation run: 435 violations against 128 in the legal
    direction, a 3.4:1 ratio, on 2,047 latents judged under both. So the judge is
    NOT monotonic, and the cause is almost certainly its own prompt, which tells
    it to "be strict" because "most detectors are NOT covered". That makes the
    judgement RELATIVE to the whole explanation -- is this one of the main things
    here? -- rather than absolute containment. Feed it more text and each latent
    is a smaller share of it, so the same latent flips to "not covered".

    CONSEQUENCE, and it is a real limit on what this project can claim:
    conveyance rates are NOT comparable ACROSS variants of different lengths. A
    shorter explanation scores higher for reasons of salience, not content.
    WITHIN one variant the artefact applies to every bucket equally and cancels,
    so shared-vs-lost inside a single variant is unaffected.

    This is why `conveyance` reports `rate_union` alongside the direct rate --
    see that function.
    """
    seen: dict[tuple, dict] = {}
    for r in rows:
        seen.setdefault((r["act"], r["feature"]), {})[r.get("variant", "full")] = r
    both = [d for d in seen.values() if "full" in d and "final_only" in d]
    if len(both) < 50:
        return None
    P = lambda r: r["verdict"] == "present"
    viol = sum(1 for d in both if not P(d["full"]) and P(d["final_only"]))
    legal = sum(1 for d in both if P(d["full"]) and not P(d["final_only"]))
    return {
        "n_judged_under_both": len(both),
        "violations_full_no_subset_yes": viol,
        "legal_full_yes_subset_no": legal,
        "violation_rate": viol / len(both),
        "ratio_violation_to_legal": (viol / legal) if legal else None,
        # A monotonic judge would put this near zero. Anything above ~5% means
        # cross-variant conveyance comparisons are measuring length, not content.
        "cross_variant_comparable": viol / len(both) < 0.05,
    }


def conveyance(rows: list[dict], fpr: float,
               union_rows: list[dict] | None = None) -> dict:
    """Section 3: does the explanation cover each latent?

    Bucket comparisons are computed PER ACTIVATION and compared across them.
    The pooled z is also reported, solely to document how much pooling inflates.

    `union_rows`, when given, supplies the SEGMENT judgements this explanation is
    made of, and every bucket also gets a `rate_union`: a latent counts as
    covered if ANY segment covers it. That figure is monotonic by construction --
    a union cannot be smaller than one of its parts -- which the directly-judged
    rate is not (see `monotonicity`). Both are reported: the direct rate is what
    the judge actually said, the union is the coherent one.

    The union is a LOWER bound on true containment. A latent covered only by the
    COMBINATION of two segments -- paragraph 1 establishes "code tutorial",
    paragraph 3 says "variable declaration", and the latent is "variable
    declaration in code tutorials" -- is missed, because each segment is judged
    alone. That is the price of monotonicity, and it is the safe direction.
    """
    by_bucket, per_act = {}, defaultdict(list)
    for r in rows:
        per_act[r["act"]].append(r)

    # (activation, latent) -> covered by at least one segment.
    #
    # A latent appears here only if it was actually JUDGED under some segment.
    # That distinction is load-bearing: the `made` bucket is per-variant, so a
    # latent the AR invents from the full explanation may never appear in a
    # segment's buckets and so was never judged there. Counting those as "not
    # covered" made the union rate for `made` come out BELOW the direct rate
    # (33.1% vs 37.0%) -- impossible for a union, and purely an artefact of
    # scoring unmeasured latents as negatives. Rows with no segment judgement are
    # EXCLUDED from the union rate, and the coverage is reported alongside so a
    # thin denominator cannot pass unnoticed.
    uni: dict[tuple, bool] = {}
    for r in (union_rows or []):
        k = (r["act"], r["feature"])
        uni[k] = uni.get(k, False) or (r["verdict"] == "present")

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
        s_uni = [r for r in s if (r["act"], r["feature"]) in uni] if uni else []
        ku = sum(1 for r in s_uni if uni[(r["act"], r["feature"])]) if s_uni else None
        by_bucket[b] = {
            "n": len(s),
            "conveyed": k,
            "rate": k / len(s) if s else None,
            # Monotonic by construction; see the docstring. None when the run has
            # no segment judgements to union (single-variant runs).
            "rate_union": (ku / len(s_uni)) if s_uni else None,
            # How many of this bucket's latents the union could actually be
            # computed on. A low number means the union rate is not comparable
            # to the direct rate beside it.
            "n_union": len(s_uni) or None,
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

    # REAL = shared + lost = the latents genuinely in the original activation.
    # `made` is excluded because those are not in the original at all.
    #
    # THIS IS THE DENOMINATOR TO COMPARE VARIANTS ON, and the reason is
    # structural: shared = F_orig n F_ar and lost = F_orig - F_ar, so their union
    # is F_orig whatever F_ar does. Verified on the 200-conversation run --
    # all three variants give an identical real set in 200/200 activations,
    # a mean of 20.2 latents each.
    #
    # So the three variants are three descriptions of the SAME activation being
    # asked about the SAME latents. Rates over `shared` alone are not comparable
    # across variants, because `shared` is itself an outcome: full has 14.2 of
    # the 20.2, final_only 11.9, no_final 6.1. Dividing by a number that moves
    # with the thing being measured mixes "did the explanation say it" with "did
    # the AR recover it".
    #
    # `made` is a different question -- what the AR invents that was never there
    # -- and is reported separately rather than folded into a coverage rate.
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

    made_rows = [r for r in rows if r["bucket"] == "made"]
    return {
        "n_pairs": len(rows),
        "n_activations": len(per_act),
        "by_bucket": by_bucket,
        # The comparable quantity: coverage over F_orig, whose size does not
        # depend on the variant. `recovered_frac` is the AR's job (how much of
        # F_orig survived), `rate` is the explanation's job (how much of F_orig
        # the text conveys) -- two different things over one fixed denominator.
        "over_f_orig": {
            "n": len(real),
            "rate": p_real,
            "rate_corrected_for_fpr": corrected,
            "recovered_frac": (by_bucket["shared"]["n"] / len(real)) if real else None,
            "conveyed_of_recovered": by_bucket["shared"]["rate"],
            "conveyed_of_destroyed": by_bucket["lost"]["rate"],
        },
        # Not part of faithfulness to the original -- these were never in it.
        "made_separately": {
            "n": len(made_rows),
            "rate": (sum(1 for r in made_rows if r["verdict"] == "present")
                     / len(made_rows)) if made_rows else None,
            "null_expl_rate": by_bucket["made"]["null_expl_rate"],
            "note": "latents the AR invented; reported apart from the F_orig "
                    "coverage rate because they are a different question",
        },
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


def by_label_quality(rows: list[dict], n_bands: int = 5) -> dict | None:
    """Does the conveyance rate just track how good the LABEL is?

    When a latent comes back "not present" there are two readings: the AV never
    mentioned it, or its label is too vague for the judge to match. This
    separates them without any extra judging, by splitting the same rows on the
    label's own AUC.

    It replaced a proposed fourth judge arm that would have scored each latent
    against the SOURCE TEXT as a "perfect explanation" ceiling. That arm was
    dropped: the source text is the document the activation came from, and a
    latent's label is derived from text that makes it fire, so asking whether
    the source matches the label mostly re-asks whether the label is right --
    which the AUC gate in label_features.py already tests, with a wrong-label
    null and disjoint select/report bands. It would have doubled the judge stage
    to weakly duplicate an existing control.

    Two things to read here:
      * conveyance RISING with label AUC means label quality limits the headline
        rate, so the headline understates what happens for well-identified
        latents. Expect null_expl to fall at the same time -- a vague label
        matches unrelated explanations more often too.
      * the shared-vs-lost gap holding as the threshold tightens is the finding
        surviving its most obvious confound. If the gap only exists among weak
        labels, it is an artefact of labelling, not a result about the AV.
    """
    rows = [r for r in rows if r.get("label_auc") is not None]
    if len(rows) < n_bands * 20:
        return None
    rows.sort(key=lambda r: r["label_auc"])
    # Same convention as conveyance(): unknowns stay in the denominator, so
    # these rates are directly comparable to the bucket table above.
    rate = lambda s: (sum(1 for r in s if r["verdict"] == "present") / len(s)
                      if s else None)

    bands, per = [], len(rows) // n_bands
    for i in range(n_bands):
        b = rows[i * per:] if i == n_bands - 1 else rows[i * per:(i + 1) * per]
        ne = [r["null_expl_rate"] for r in b if r.get("null_expl_rate") is not None]
        bands.append({
            "auc_low": b[0]["label_auc"], "auc_high": b[-1]["label_auc"],
            "n": len(b), "rate": rate(b),
            "null_expl_rate": st.mean(ne) if ne else None,
        })

    thresholds = []
    for thr in (0.0, 0.85, 0.90, 0.94):
        s = [r for r in rows if r["label_auc"] >= thr]
        sh = [r for r in s if r["bucket"] == "shared"]
        ls = [r for r in s if r["bucket"] == "lost"]
        if not sh or not ls:
            continue
        thresholds.append({"threshold": thr, "n_shared": len(sh), "n_lost": len(ls),
                           "shared": rate(sh), "lost": rate(ls),
                           "gap": rate(sh) - rate(ls)})
    gaps = [t["gap"] for t in thresholds]
    return {
        "bands": bands,
        "rate_lift_weakest_to_strongest": bands[-1]["rate"] - bands[0]["rate"],
        "by_threshold": thresholds,
        # If this is small the finding does not depend on label quality.
        "gap_spread_across_thresholds": (max(gaps) - min(gaps)) if gaps else None,
    }


def ablation(ov: dict, sm: dict, bg: dict, gr: dict, fpr: float,
             variants: list[str]) -> dict | None:
    """Section 6: what each part of the explanation contributes.

    The AV writes to a three-part shape -- what kind of document this is, what it
    is about, and what the FINAL TOKEN is doing. The third part is a different
    kind of claim from the first two: it is about the single token the activation
    sits on, not the surrounding passage. If it carries most of the signal alone,
    the NLA is doing next-token description rather than context summarisation,
    and every other section has to be read in that light.

    No new metric is introduced. Each variant goes through the identical pipeline
    -- same AR, same SAE, same buckets, same judge, same nulls -- and this reports
    the existing numbers three times, side by side.

    TWO THINGS TO CHECK BEFORE READING THE RESULT:

    * the split's anchor rate, in `split`. The cut is made at the paragraph that
      talks about the final token; if the AV's output format drifts, that rate
      falls and the variants stop being what they claim to be.
    * `tokens_mean` and `fve_B_per_100_tokens`. The variants are not the same
      length, so a variant scoring higher could simply be the one with more text.
      Reporting per token does not remove that confound -- it exposes it.
    """
    if len(variants) < 2:
        return None
    bv = ov.get("by_variant") or {}
    out = {"variants": variants, "split": ov.get("split_report"), "by_variant": {}}
    for v in variants:
        runs = [r for r in ov["runs"] if r.get("variant", "full") == v]
        rows = [r for r in gr["rows"] if r.get("variant", "full") == v]
        sm_v = {**sm, "runs": [r for r in sm["runs"] if r.get("variant", "full") == v],
                "totals": (sm.get("by_variant", {}).get(v) or sm["totals"])}
        bg_v = {**bg, "runs": [r for r in bg["runs"] if r.get("variant", "full") == v],
                "totals": (bg.get("by_variant", {}).get(v) or bg["totals"])}
        entry = {
            "reconstruction": reconstruction({**ov, "runs": runs}) if runs else None,
            "overlap": overlap(sm_v, bg_v) if sm_v["runs"] and bg_v["runs"] else None,
            "conveyance": conveyance(rows, fpr) if rows else None,
            "label_quality": by_label_quality(rows) if rows else None,
        }
        for k in ("tokens_mean", "tokens_median", "chars_mean",
                  "fve_B_per_100_tokens", "n_split_failed", "n_untagged", "n_cjk"):
            if k in bv.get(v, {}):
                entry[k] = bv[v][k]
        out["by_variant"][v] = entry
    return out


def fve_vs_grounding(ov: dict, gr: dict, variants: list[str],
                     min_latents: int = 3) -> dict | None:
    """Does a better reconstruction mean a better-GROUNDED explanation?

    loops (LessWrong, 15 May 2026, "Some observations about NLA explanations")
    showed on this same checkpoint that cutting the final paragraph costs far
    more reconstruction error than cutting the first two. That is a statement
    about FVE. It leaves open whether FVE tracks what the explanation actually
    says about the activation, which is what this measures.

    Two levels, and they can disagree:

      * BETWEEN variants -- does the part of the text with more FVE also carry
        more grounded content? (reported by ablation(), above)
      * BETWEEN activations -- within one variant, is an activation the AR
        rebuilds well also one whose latents the explanation names?

    The second is the sharper test and the one FVE would need to pass to be
    usable as a proxy for grounding. Activations with fewer than `min_latents`
    judged latents are dropped: a rate over one or two latents is mostly noise.
    """
    fve = {(r["act"], r.get("variant", "full")): r["fve_B"] for r in ov["runs"]}
    num: dict = {}
    den: dict = {}
    for r in gr["rows"]:
        # F_orig only -- shared + lost is what was genuinely in the activation.
        # `made` was not, so it cannot speak to grounding.
        if r["bucket"] not in ("shared", "lost"):
            continue
        if r["verdict"] not in ("present", "not_present"):
            continue          # `unknown` = the measurement refused itself
        k = (r["act"], r.get("variant", "full"))
        den[k] = den.get(k, 0) + 1
        num[k] = num.get(k, 0) + (r["verdict"] == "present")

    out: dict = {"min_latents": min_latents, "by_variant": {}}
    for v in variants:
        ks = [k for k in den if k[1] == v and den[k] >= min_latents and k in fve]
        if len(ks) < 3:
            continue
        c = corr([fve[k] for k in ks], [num[k] / den[k] for k in ks])
        c["n_activations_dropped"] = sum(
            1 for k in den if k[1] == v and den[k] < min_latents)
        out["by_variant"][v] = c
    return out or None


def distance_sweep(ov: dict, sm: dict, bg: dict) -> dict | None:
    """Section 7: is the latent match specific to THIS token?

    The standing Jaccard null compares the rebuild against an activation from an
    unrelated conversation, which shares almost nothing -- an easy bar to clear.
    This is the hard version: compare the rebuild of position p against the REAL
    activation at p+d in the SAME conversation. Same topic, same document, same
    speaker, a few tokens away.

      flat across d   -> the explanation describes the passage, and the exact
                         position is doing no work
      falls with |d|  -> the round trip is genuinely position-specific

    Directions are never averaged: text before p is context the activation
    encodes, text after is context it cannot, so -20 and +20 are different
    measurements and pooling them would hide any asymmetry.

    `restricted` repeats the curve over only the activations long enough to
    supply every offset. Without it each point comes from a different subset of
    conversations -- short responses lose the far offsets first, and short
    responses are not a random subsample -- so a falling curve could be attrition
    rather than distance.
    """
    sw = ov.get("distance_sweep")
    if not sw:
        return None
    out = {
        "offsets": sw["offsets"],
        "self_match_delta0": sw["self_match_delta0"],
        "unrelated_conversation_null": sw["unrelated_conversation_null"],
        "n_activations": sw.get("n_activations"),
        "n_activations_all_offsets": sw.get("n_activations_all_offsets"),
        "l0_big": (sw.get("by_variant") or {}).get("full"),
        "l0_big_restricted": (sw.get("by_variant_restricted") or {}).get("full"),
        "by_variant": sw.get("by_variant"),
        "l0_small": sm.get("distance_sweep"),
    }
    curve, self0 = out["l0_big"] or {}, out["self_match_delta0"]
    if curve and self0:
        # How much of the self-match survives one step away, and at the far end.
        # Near 1.0 at d=+-5 means the match is about the passage, not the token.
        near = [curve[k]["jaccard"] for k in ("5", "-5")
                if curve.get(k, {}).get("jaccard") is not None]
        far = [curve[k]["jaccard"] for k in ("50", "-50")
               if curve.get(k, {}).get("jaccard") is not None]
        out["nearest_over_self"] = (max(near) / self0) if near else None
        out["furthest_over_self"] = (max(far) / self0) if far else None
    return out


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
          "| bucket | n | conveyed | conveyed (union) | null_feat | null_expl | vs null_expl | mean label AUC |",
          "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for b in ("shared", "made", "lost"):
        d = c["by_bucket"][b]
        u = _fmt(d.get("rate_union"), "{:.1%}")
        if d.get("n_union"):
            u += f" (n={d['n_union']:,})"
        L.append(f"| {b} | {d['n']:,} | {d['rate']:.1%} | {u} | "
                 f"{d['null_feat_rate']:.1%} | "
                 f"{d['null_expl_rate']:.1%} | {d['over_null_expl']:.1f}x | "
                 f"{d['mean_label_auc']:.3f} |")
    L += [f"| **REAL** (shared+lost = F_orig) | {c['real']['n']:,} | "
          f"{c['real']['rate']:.1%} | | | | | |",
          ""]
    fo = c.get("over_f_orig")
    if fo:
        L += ["**Compare variants on this row, not on `shared`.** `shared` and "
              "`lost` partition F_orig, the latents genuinely in the activation, "
              "so their union is the same set for every variant — three "
              "descriptions of one activation, asked about the same latents. "
              "`shared` on its own is an *outcome* (how much the AR recovered), "
              "so a rate over it divides by a number that moves with what is "
              "being measured.", "",
              f"- of F_orig, the AR recovered **{fo['recovered_frac']:.1%}** "
              f"(`shared`); the rest was destroyed by the round trip (`lost`)",
              f"- of F_orig, the explanation conveys **{fo['rate']:.1%}** raw, "
              f"**{fo['rate_corrected_for_fpr']:.1%}** corrected for the judge's "
              f"false-positive rate",
              f"- split: **{fo['conveyed_of_recovered']:.1%}** of recovered "
              f"latents are conveyed vs **{fo['conveyed_of_destroyed']:.1%}** of "
              f"destroyed ones", ""]
    md = c.get("made_separately")
    if md and md.get("rate") is not None:
        L += ["### `made` — reported separately", "",
              "These latents were **never in the original activation**; the AR "
              "produced them from the text. They are not part of faithfulness to "
              "the activation, so they are kept out of the coverage rate above "
              "rather than averaged into it.", "",
              f"- **{md['n']:,}** invented latents, **{md['rate']:.1%}** of them "
              f"traceable to something the explanation says "
              f"(chance {md['null_expl_rate']:.1%})", ""]
    L += [
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
          f"never mentioned** in the explanation"]

    q = s.get("label_quality")
    if q:
        L += ["", "### Is this just label quality?", "",
              "A latent scored 'not present' has two readings: the AV never "
              "mentioned it, or its label is too vague for the judge to match. "
              "Splitting the same rows on each label's own AUC separates them, "
              "with no extra judging.", "",
              "| label AUC band | n | conveyed | null_expl | vs null |",
              "|---|---:|---:|---:|---:|"]
        for b in q["bands"]:
            ratio = (b["rate"] / b["null_expl_rate"]) if b["null_expl_rate"] else None
            L.append(f"| {b['auc_low']:.3f}-{b['auc_high']:.3f} | {b['n']:,} | "
                     f"{b['rate']:.1%} | {b['null_expl_rate']:.1%} | "
                     + (f"{ratio:.1f}x |" if ratio else "- |"))
        L += ["",
              f"- conveyance moves **{100*q['rate_lift_weakest_to_strongest']:+.1f} "
              f"points** from the weakest validated labels to the strongest. A "
              f"large lift means the headline rate understates what happens for "
              f"well-identified latents, and that chance is lower there too -- a "
              f"vague label matches unrelated explanations more often as well.",
              "",
              "**The check that matters: does the shared-vs-lost gap survive as "
              "the label threshold tightens?** If it only exists among weak "
              "labels it is an artefact of labelling, not a result about the AV.",
              "",
              "| labels kept | shared | lost | gap |", "|---|---:|---:|---:|"]
        for t in q["by_threshold"]:
            nm = "all validated" if t["threshold"] == 0.0 else f"AUC >= {t['threshold']:.2f}"
            L.append(f"| {nm} (n={t['n_shared']:,}/{t['n_lost']:,}) | {t['shared']:.1%} | "
                     f"{t['lost']:.1%} | **{100*t['gap']:+.1f} pts** |")
        if q["gap_spread_across_thresholds"] is not None:
            spread = 100 * q["gap_spread_across_thresholds"]
            L += ["", f"- the gap varies by **{spread:.1f} points** across those "
                      f"thresholds "
                      f"({'stable -- the finding does not depend on label quality' if spread < 5 else 'UNSTABLE -- the finding tracks label quality and must not be quoted as a result about the AV'})."]

    L += ["", "## 5. Judge validation", ""]
    for k, v in s["judge"].items():
        if isinstance(v, (int, float)):
            L.append(f"- {k}: **{v:.3f}**")

    mo = s.get("judge_monotonicity")
    if mo:
        L += ["", "### Is the judge consistent about containment?", "",
              "`full` is exactly `no_final` + `final_only` -- the split is a cut, "
              "not a rewrite -- so anything a part covers, the whole must cover. "
              "Any latent judged covered under the SUBSET and not under the "
              "SUPERSET is a logical violation.", "",
              f"- judged under both: **{mo['n_judged_under_both']:,}**",
              f"- **violations** (full NO, subset YES): "
              f"**{mo['violations_full_no_subset_yes']:,}** "
              f"({mo['violation_rate']:.1%})",
              f"- legal direction (full YES, subset NO): "
              f"{mo['legal_full_yes_subset_no']:,}",
              ""]
        if not mo["cross_variant_comparable"]:
            L += ["> **Conveyance rates are NOT comparable across variants.** The "
                  "judge's prompt tells it to be strict because most latents are "
                  "not covered, which makes the judgement RELATIVE to the whole "
                  "explanation rather than absolute containment. A shorter "
                  "explanation therefore scores higher for reasons of salience, "
                  "not content. Within a single variant the artefact applies to "
                  "every bucket equally and cancels, so shared-vs-lost inside one "
                  "variant is unaffected. Use `rate_union` for anything "
                  "cross-variant.", ""]

    fg = s.get("fve_vs_grounding")
    if fg and fg.get("by_variant"):
        L += ["", "## 6b. Does FVE predict grounding?", "",
              "loops (LessWrong, 15 May 2026) showed on this checkpoint that "
              "cutting the final paragraph costs far more reconstruction error "
              "than cutting the first two. That is about FVE. This asks whether "
              "FVE tracks what the explanation actually says about the "
              "activation.", "",
              "Per activation, within one variant: does a higher FVE go with a "
              "higher share of that activation's own latents being named?", "",
              "| variant | n | Pearson r | 95% CI | Spearman | detectable? |",
              "|---|---:|---:|---|---:|---|"]
        for v, c in fg["by_variant"].items():
            ci = (f"{_fmt(c.get('ci_low'), '{:+.3f}')} to "
                  f"{_fmt(c.get('ci_high'), '{:+.3f}')}")
            L.append(f"| `{v}` | {c['n']} | {_fmt(c.get('pearson'), '{:+.3f}')} | "
                     f"{ci} | {_fmt(c.get('spearman'), '{:+.3f}')} | "
                     f"{'**yes**' if c.get('significant') else 'no'} |")
        floors = [c.get("detectable_floor") for c in fg["by_variant"].values()
                  if c.get("detectable_floor")]
        L += ["",
              f"- activations with fewer than {fg['min_latents']} judged latents "
              "are dropped -- a rate over one or two latents is mostly noise",
              (f"- at this n, |r| below about {max(floors):.2f} cannot be "
               "distinguished from zero. A near-zero row means **no correlation "
               "detectable at this n**, not that none exists."
               if floors else ""),
              "- this is the between-ACTIVATION question. The between-VARIANT "
              "one -- does the part of the text with more FVE carry more "
              "grounded content -- is section 6 above."]

    ab = s.get("ablation")
    if ab:
        L += ["", "## 6. Paragraph ablation — which part of the explanation carries it", "",
              "The AV writes to a three-part shape: what kind of document this is, "
              "what it is about, and what the **final token** is doing. The third "
              "part is a different kind of claim -- about the one token the "
              "activation sits on, not the passage around it. Each variant runs "
              "through the identical pipeline; no new metric is introduced.", "",
              "| | `full` | `no_final` (parts 1-2) | `final_only` (part 3) |",
              "|---|---:|---:|---:|"]
        vs = ab["variants"]
        cell = lambda f: " | ".join(f(ab["by_variant"][v]) for v in vs)
        def _g(d, *path, default=None):
            for k in path:
                if not isinstance(d, dict) or k not in d or d[k] is None:
                    return default
                d = d[k]
            return d
        rows_spec = [
            ("**FVE B** (mean)", lambda e: _fmt(_g(e, "reconstruction", "fve", "B_ar_vs_orig"), "{:+.4f}")),
            ("FVE B (median)", lambda e: _fmt(_g(e, "reconstruction", "fve_B_distribution", "median"), "{:+.4f}")),
            ("cosine B", lambda e: _fmt(_g(e, "reconstruction", "cos_implied", "B_ar_vs_orig"), "{:.5f}")),
            ("FVE B control (wrong activation)", lambda e: _fmt(_g(e, "reconstruction", "mismatched_control", "fve_B_control"), "{:+.4f}")),
            ("Jaccard `l0_small`", lambda e: _fmt(_g(e, "overlap", "l0_small", "jaccard_matched"), "{:.4f}")),
            ("Jaccard control `l0_small`", lambda e: _fmt(_g(e, "overlap", "l0_small", "jaccard_control"), "{:.4f}")),
            ("shared latents", lambda e: _fmt(_g(e, "overlap", "l0_small", "totals", "shared"), "{:,}")),
            ("lost latents", lambda e: _fmt(_g(e, "overlap", "l0_small", "totals", "lost"), "{:,}")),
            ("made latents", lambda e: _fmt(_g(e, "overlap", "l0_small", "totals", "made"), "{:,}")),
            ("conveyance `shared`", lambda e: _fmt(_g(e, "conveyance", "by_bucket", "shared", "rate"), "{:.1%}")),
            ("conveyance `lost`", lambda e: _fmt(_g(e, "conveyance", "by_bucket", "lost", "rate"), "{:.1%}")),
            ("chance (`null_expl`, shared)", lambda e: _fmt(_g(e, "conveyance", "by_bucket", "shared", "null_expl_rate"), "{:.1%}")),
            ("shared - lost gap", lambda e: _fmt(_g(e, "conveyance", "comparisons", "shared_vs_lost", "clustered", "mean"), "{:+.1%}")),
            ("**tokens** (mean)", lambda e: _fmt(e.get("tokens_mean"), "{:.0f}")),
            ("**FVE B per 100 tokens**", lambda e: _fmt(e.get("fve_B_per_100_tokens"), "{:+.4f}")),
        ]
        for label, f in rows_spec:
            L.append(f"| {label} | " + cell(f) + " |")
        sp = ab.get("split") or {}
        L += ["",
              f"- split: **{sp.get('usable', 0):,}/{sp.get('n', 0):,}** usable, "
              f"anchor rate **{_fmt(sp.get('anchor_rate'), '{:.0%}')}**, "
              f"methods `{sp.get('by_method')}`",
              "- the cut is made at the paragraph naming the final token. A falling "
              "anchor rate means the AV's output format moved and these variants "
              "are no longer what they claim -- check `explanation_splits.json`.",
              "- **the variants differ in length**, so read FVE per 100 tokens "
              "beside the raw figure. Per-token does not remove the confound, it "
              "makes it visible."]

    sw = s.get("distance_sweep")
    if sw:
        L += ["", "## 7. Near-miss sweep — is the match specific to this token?", "",
              "The standing Jaccard null uses an **unrelated conversation**, which "
              "shares almost nothing. This is the harder null: the rebuild of "
              "position *p* against the **real activation at p+d in the same "
              "conversation** -- same topic, same document, a few tokens away. "
              "Flat across *d* would mean the explanation describes the passage "
              "and the exact position does no work.", "",
              "| offset | Jaccard (`l0_big`) | n | restricted | n |",
              "|---|---:|---:|---:|---:|"]
        big = sw.get("l0_big") or {}
        res = sw.get("l0_big_restricted") or {}
        L.append(f"| **d = 0** (its own activation) | **{sw['self_match_delta0']:.4f}** | | | |")
        for d in sw["offsets"]:
            e, r = big.get(str(d), {}), res.get(str(d), {})
            L.append(f"| d = {d:+d} | {_fmt(e.get('jaccard'), '{:.4f}')} | {e.get('n', 0)} "
                     f"| {_fmt(r.get('jaccard'), '{:.4f}')} | {r.get('n', 0)} |")
        L.append(f"| *unrelated conversation* | *{sw['unrelated_conversation_null']:.4f}* | | | |")
        L += ["",
              f"- **{sw.get('n_activations_all_offsets')}/{sw.get('n_activations')}** "
              f"activations are long enough to supply every offset. The "
              f"`restricted` columns use only those, so the points are comparable "
              f"to each other; in the unrestricted columns a falling curve could "
              f"be attrition, since short responses lose the far offsets first.",
              "- directions are **not** averaged: text before *p* is context the "
              "activation encodes, text after is context it cannot."]
        if sw.get("nearest_over_self") is not None:
            L.append(f"- at the nearest offset the match retains "
                     f"**{sw['nearest_over_self']:.0%}** of the self-match; at the "
                     f"furthest, **{_fmt(sw.get('furthest_over_self'), '{:.0%}')}**.")
    return "\n".join(L) + "\n"


def _fmt(v, spec="{:.3f}"):
    """Format a number that may legitimately be absent."""
    if v is None:
        return "-"
    try:
        return spec.format(v)
    except (TypeError, ValueError):
        return str(v)


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
                # `full` is a UNION of its segments, so it has a coverage bit
                # and no grade. Printing the grade unconditionally rendered
                # "[stated - None]" for every full row.
                _g = (v or {}).get("grade")
                tag = {"present": ("  **[stated — %s]**" % _g) if _g else "  **[stated]**",
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

    # EVERY PRIMARY SECTION IS variant="full" ONLY.
    # The paragraph ablation makes three records per activation -- the whole
    # explanation and two cut-down versions of it. Pooling them would report the
    # average of an explanation and two ablations of itself, which is not a
    # quantity anything is true of. So the sections below are filtered to the
    # unmodified explanation, and the ablation gets its own section where the
    # three are shown side by side.
    # `.get("variant", "full")` throughout: artefacts written before the ablation
    # existed have no variant field and are all "full" by definition.
    _V = lambda rs, v="full": [r for r in rs if r.get("variant", "full") == v]
    variants = [v for v in ("full", "no_final", "final_only")
                if any(r.get("variant", "full") == v for r in ov["runs"])]
    has_ablation = len(variants) > 1

    ov_full = {**ov, "runs": _V(ov["runs"])}
    sm_full = {**sm, "runs": _V(sm["runs"]),
                "totals": (sm.get("by_variant", {}).get("full") or sm["totals"])}
    bg_full = {**bg, "runs": _V(bg["runs"]),
                "totals": (bg.get("by_variant", {}).get("full") or bg["totals"])}
    rows_full = _V(gr["rows"])

    n_acts = len({r["act"] for r in ov_full["runs"]})
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
            "n_pairs": len(ov_full["runs"]),
            "runs_per_activation": len(ov_full["runs"]) // max(n_acts, 1),
            "variants": variants,
            "source": str(d.resolve()),
        },
        "reconstruction": reconstruction(ov_full),
        "overlap": overlap(sm_full, bg_full),
        "labels": labels(lab),
        # The segments `full` is made of. Passed so conveyance can report a
        # union rate that is monotonic by construction, which the directly
        # judged rate is not -- see monotonicity().
        "conveyance": conveyance(
            rows_full, fpr,
            union_rows=[r for r in gr["rows"]
                        if r.get("variant", "full") in ("no_final", "final_only")]
            if has_ablation else None),
        "judge_monotonicity": monotonicity(gr["rows"]),
        "label_quality": by_label_quality(rows_full),
        "judge": judge_validation(gr),
        # The paragraph ablation: every section above, recomputed per variant.
        "ablation": (ablation(ov, sm, bg, gr, fpr, variants)
                     if has_ablation else None),
        # Does FVE predict grounding? Between variants AND between activations.
        "fve_vs_grounding": fve_vs_grounding(ov, gr, variants),
        "distance_sweep": distance_sweep(ov, sm, bg),
    }

    out = Path(a.out) if a.out else d / "summary.json"
    out.write_text(json.dumps(summary, indent=2))
    (d / "SUMMARY.md").write_text(render_md(summary))

    # Per-example table. Everything the round trip recorded for each (activation,
    # explanation) pair, one row each, so a reader can check any single case
    # without parsing JSON -- and so a claim about "the outliers" can be checked.
    cols = ["act", "run", "variant", "row", "fve_A", "fve_B", "fve_C", "fve_D",
            "cos_A_sae_orig_vs_orig", "cos_B_ar_vs_orig",
            "cos_C_sae_ar_vs_ar", "cos_D_sae_ar_vs_orig",
            "n_orig", "n_ar", "n_shared", "n_lost", "n_invented",
            "jaccard", "control_jaccard", "weighted_kept",
            "n_tokens", "n_chars", "split_method",
            "activation_token_index", "offset_into_response", "cjk", "untagged"]
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
