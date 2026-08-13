"""Which SAE features survive the AV->AR round trip, and which are invented?

Tests the NLA paper's own stated open limitation:

> "Excessive expressivity: Because the AV is a full language model, it has the
> capacity to make additional inferences beyond what is stored in an activation."

FVE cannot answer it — during RL the AR trains on the AV's own rollouts
(docs/design.md:97), so it is fitted to the AV's output distribution rather than
being an independent judge. An SAE reads the activation directly.

WHY THIS VERSION HAS NO LLM ANYWHERE IN THE MEASUREMENT
Earlier passes matched explanation TEXT against feature MEANINGS, which required
auto-interp and a judge. Both proved unreliable: across 40 hand-audited pairs the
judge missed 8 and over-called 0, and two earlier judges failed audit by ignoring
explicit instructions. This version treats a fired feature simply as "a feature
of this activation", identified by integer index. What each feature MEANS is a
separate question, answerable later for whichever features turn out to matter.
The comparison reduces to set overlap over integers — exact and reproducible.

THE PIPELINE
  v            the sampled activation
  v_sae        SAE(v)                 — what the SAE can represent of it
  v_ar         AR(AV(v))              — what survives the natural-language round trip
  v_ar_sae     SAE(AR(AV(v)))         — SAE view of that

  F_orig = features(v)     F_ar = features(v_ar)
  lost     = F_orig \\ F_ar     invented = F_ar \\ F_orig

CONTROL IS NOT OPTIONAL. Common syntactic features fire on everything, so raw
overlap is uninterpretable; F_orig(i) vs F_ar(j!=i) gives the base rate.

ALL FOUR VECTOR FAMILIES ARE SAVED to .npz. They are the input to later probe
work (fit a direction separating AR-reconstructed from real activations), and
regenerating them costs a full run. Keeping v_orig_sae too means the SAE's own
reconstruction error can be subtracted out, so a probe isolates the AR effect
instead of confounding it with SAE lossiness.

Usage:
    python src/roundtrip.py \
        --av <av_dir> --ar <ar_dir> --n 10 --runs 5 \
        --out-dir results
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import re
import sys
from pathlib import Path

import numpy as np
import torch
from safetensors.torch import load_file

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
# nla_inference.py and the nla/ package come from the upstream NLA repo
# (kitft/natural_language_autoencoders). Point NLA_REPO at a clone of it, or
# place this repo inside one. nla_av.py and sampling.py are vendored here
# because this fork modified them -- nla_av.py in particular carries the Gemma
# embed-scale fix (see its docstring).
_UP = os.environ.get("NLA_REPO") or str(_HERE.parent.parent)
sys.path.insert(0, _UP)

from nla_av import AVRunner                                    # noqa: E402
from sampling import FAILED_EXTRACTION_MSE, load_vectors          # noqa: E402
from nla.schema import load_predict_mean_baselines                    # noqa: E402
from nla_inference import NLACritic                                   # noqa: E402

from hf_paths import sae_variant_dir, L0_BIG  # noqa: E402
from explanation_parts import VARIANTS, split_explanation, split_report  # noqa: E402

# If injection silently fails the AV describes the literal marker char and
# free-associates in CJK. CLAUDE.md calls this the loudest smoke test for the
# whole injection path.
_CJK = re.compile(r"[　-鿿豈-﫿＀-￯]")


def load_sae():
    d = sae_variant_dir(L0_BIG)
    return load_file(str(d / "params.safetensors"))


def sae_encode(V: torch.Tensor, P: dict) -> torch.Tensor:
    """Gemma Scope JumpReLU. b_dec is added on DECODE only — subtracting it from
    the input destroys the signal (measured cos 0.31 vs 0.99), because
    ||b_dec||=73948 is comparable to ||v|| itself."""
    pre = V @ P["w_enc"] + P["b_enc"]
    return torch.where(pre > P["threshold"], pre, torch.zeros_like(pre))


def sae_decode(acts: torch.Tensor, P: dict) -> torch.Tensor:
    return acts @ P["w_dec"] + P["b_dec"]


def fve_of(mses, rawvar):
    return 1.0 - float(np.mean(mses)) / rawvar


def cos_of(a: torch.Tensor, b: torch.Tensor) -> float:
    return float(torch.nn.functional.cosine_similarity(
        a.flatten().float(), b.flatten().float(), dim=0))


def norm_mse(pred: torch.Tensor, gold: torch.Tensor, mse_scale: float) -> float:
    """Same normalization the critic uses: both L2-normalized to mse_scale, so
    MSE == 2(1-cos). Lets SAE reconstructions be scored on the same axis as AR
    reconstructions."""
    p = pred.float() / pred.float().norm().clamp_min(1e-12) * mse_scale
    g = gold.float() / gold.float().norm().clamp_min(1e-12) * mse_scale
    return float(((p - g) ** 2).mean())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--av", required=True)
    ap.add_argument("--ar", required=True)
    ap.add_argument("--parquet", default="acts_gemma_L32_test.parquet")
    ap.add_argument("--n", type=int, default=10, help="activations")
    ap.add_argument("--runs", type=int, default=5, help="AV samples per activation")
    ap.add_argument("--seed", type=int, default=0,
                    help="row-sampling seed. Used once -- there is no retry loop, "
                         "because retrying until FVE looks good would select "
                         "activations on the outcome metric")
    ap.add_argument("--health-lo", type=float, default=0.65,
                    help="warn below this FVE. NOT a filter -- nothing is "
                         "rejected or resampled. The paper reports ~0.752.")
    ap.add_argument("--health-hi", type=float, default=0.85)
    ap.add_argument("--temperature", type=float, default=1.0)
    ap.add_argument("--explanation-max-tokens", type=int, default=200)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--out-dir", default=str(_HERE))
    args = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)
    out_dir = Path(args.out_dir); out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 76)
    print("FEATURE OVERLAP — which SAE features survive the AV->AR round trip?")
    print("=" * 76)

    P = load_sae()
    # THE AV AND AR ARE NEVER RESIDENT TOGETHER. The AV is loaded here, used for
    # every explanation in stage 2a, then released before the AR is loaded in
    # 2b. Peak is one 12B model, so this fits a 24GB card. rawvar needs the AR's
    # mse_scale, which is read from its config without loading weights.
    av = AVRunner(args.av, device=args.device)
    critic = None
    # mse_scale is sqrt(d_model) by definition (3840 -> 61.9677; Qwen's 3584 ->
    # 59.87). Computing it here rather than reading it off the AR lets the AR
    # stay unloaded until stage 2b, which is what keeps the two 12B models from
    # ever being resident together. It is ASSERTED against the real value once
    # the AR loads, so the assumption cannot drift silently.
    import pyarrow.parquet as _pq
    _d = len(_pq.ParquetFile(args.parquet).read(
        columns=["activation_vector"]).column(0)[0])
    mse_scale = float(np.sqrt(_d))
    _, rawvar = load_predict_mean_baselines(args.parquet, mse_scale)
    print(f"[cfg] d_model={_d}  rawvar={rawvar:.4f}  mse_scale={mse_scale:.4f} "
          f"injection_scale={av.cfg.injection_scale}  embed_scale={av.embed_scale:.4f}")

    def gen(v, seed):
        torch.manual_seed(seed)
        e = av.generate(v, temperature=args.temperature,
                                    explanation_max_tokens=args.explanation_max_tokens,
                                    do_sample=True)
        return e

    # Length of a variant in tokens, not characters -- the AR reads tokens, so
    # that is the unit FVE-per-token has to be in. Uses the AV's own tokenizer,
    # which is the same one the AR uses. Must be called before the AV is released.
    def _ntok(text: str | None) -> int:
        if not text:
            return 0
        return len(av.tokenizer.encode(text, add_special_tokens=False))

    # ---------------- Stage 0: sample + FVE health check ----------------
    # THIS IS A DIAGNOSTIC, NOT A FILTER.
    #
    # The NLA paper reports FVE ~0.752 for these checkpoints. If this run
    # produces 0.45, something is broken -- wrong layer, failed injection,
    # mis-loaded weights -- and every downstream number would inherit it. So the
    # FVE is computed once, up front, and reported.
    #
    # An earlier version RESAMPLED until the FVE landed in [0.73, 0.77]. That
    # turned a health check into selection on the outcome metric: activations
    # were being chosen partly because they scored well on the thing being
    # measured. It never actually rejected a sample in practice (the n=50 run
    # accepted seed 0 at FVE 0.7394 on the first try), but the code could, and a
    # tool nobody should have to caveat is better than a caveat.
    #
    # Removing the search also removes the only place the AV and AR had to be
    # resident at the same time, which is what forced a 48GB card.
    print("\n--- Stage 0: sample ---")
    seed = args.seed
    V, row_idx, _ = load_vectors(args.parquet, args.n, seed)
    print(f"  seed {seed}, rows {list(map(int, row_idx))}")

    # SOURCE TEXT, carried through to the results. An earlier run stored only the
    # parquet row index; the parquet then died with its pod and the rollout
    # responses were generated unseeded, so the text behind those results is gone
    # for good and no by-eye check against it is possible. Never again.
    import pyarrow.parquet as _pq
    _cols = set(_pq.ParquetFile(args.parquet).schema_arrow.names)
    _want = ["detokenized_text_truncated", "doc_id"] + [
        c for c in ("prompt", "response", "activation_token_index")
        if c in _cols]
    _tbl = _pq.ParquetFile(args.parquet).read(columns=_want)
    _txt = _tbl.column("detokenized_text_truncated").to_pylist()
    _docs = _tbl.column("doc_id").to_pylist()
    src_text = [_txt[int(r)][-1200:] for r in row_idx]
    # The FULL prompt and response, uncut, carried into the results so a reader
    # can see the whole conversation an activation came from rather than the
    # 1200 characters before its token. Older corpora lack these columns.
    _get = lambda c: (_tbl.column(c).to_pylist() if c in _want else None)
    _p, _r, _pos = _get("prompt"), _get("response"), _get("activation_token_index")
    src_prompt = [_p[int(i)] for i in row_idx] if _p else None
    src_response = [_r[int(i)] for i in row_idx] if _r else None
    src_pos = [_pos[int(i)] for i in row_idx] if _pos else None
    # DOC ID PER ACTIVATION, carried through so the independence of the sample is
    # checkable from the results alone. An earlier run had 50 activations drawn
    # from only 30 conversations -- invisible in every artefact, and it narrowed
    # every confidence interval downstream.
    src_doc = [_docs[int(r)] for r in row_idx]
    n_docs = len(set(src_doc))
    # NEAR-MISS NEIGHBOURS for the distance sweep. Written by
    # extract_activations.py from the same forward pass that produced the
    # activation; absent from corpora built before that existed, in which case
    # the sweep is skipped rather than faked.
    nb_off_all, nb_vec_all = None, None
    if {"neighbor_offsets", "neighbor_vectors"} <= _cols:
        _nb = _pq.ParquetFile(args.parquet).read(
            columns=["neighbor_offsets", "neighbor_vectors"])
        _o = _nb.column("neighbor_offsets").to_pylist()
        _v = _nb.column("neighbor_vectors").to_pylist()
        nb_off_all = [[int(d) for d in _o[int(r)]] for r in row_idx]
        nb_vec_all = [_v[int(r)] for r in row_idx]
        print(f"  -> near-miss neighbours available for "
              f"{sum(1 for o in nb_off_all if o)}/{len(row_idx)} activations")
    else:
        print("  -> no neighbour columns in this parquet; distance sweep skipped")
    print(f"  -> carried {len(src_text)} source texts into the results")
    print(f"  -> {len(V)} activations from {n_docs} distinct conversations"
          + ("" if n_docs == len(V) else
             f"   !! NOT INDEPENDENT: {len(V) - n_docs} share a conversation"))

    # ---------------- Stage 1: original -> SAE ----------------
    print("\n--- Stage 1: original activations through the SAE ---")
    A_orig = sae_encode(V, P)
    V_sae = sae_decode(A_orig, P)
    F_orig = [set((A_orig[i] > 0).nonzero().flatten().tolist()) for i in range(len(V))]
    sae_cos = [cos_of(V_sae[i], V[i]) for i in range(len(V))]
    sae_mse = [norm_mse(V_sae[i], V[i], mse_scale) for i in range(len(V))]
    print(f"  L0 mean {np.mean([len(f) for f in F_orig]):.1f}   "
          f"recon cos {np.mean(sae_cos):.4f}   FVE {fve_of(sae_mse, rawvar):.4f}")

    # ---------------- Stage 2: original -> AV -> AR ----------------
    # PHASE 2a -- verbalize. AV only; the AR is released first.
    # Keeping both resident costs ~48GB and does not fit a 46GB card. The AV
    # never needs the AR's output, and explanations are just strings, so
    # splitting the loop in two costs nothing but a model reload.
    # PARAGRAPH ABLATION. The explanation is generated ONCE per (activation, run)
    # and then split into the variants below, so every variant describes the same
    # activation and the same sampled text -- the comparison is paired, and none
    # of the difference between variants can come from resampling the AV.
    #
    #   full        the explanation as written                (the existing path)
    #   no_final    parts 1-2: document type, what it is about
    #   final_only  part 3: what the FINAL TOKEN is doing
    #
    # Each variant is a separate record and goes through the identical downstream
    # pipeline -- same AR, same SAE, same buckets, same judge, same nulls. No new
    # metric is introduced; every existing number is simply computed three times.
    #
    # Token counts are recorded per variant because the variants are not the same
    # length, and FVE-per-token is reported alongside raw FVE so a length effect
    # is visible rather than being absorbed into the result. Measured on 250 real
    # explanations the two ablations are close in length anyway -- no_final ~318
    # chars, final_only ~337 -- but that is a property of this AV, not a promise.
    print(f"\n--- Stage 2a: AV -> explanations, {args.runs} runs per activation ---")
    print(f"    each split into {len(VARIANTS)} variants: {', '.join(VARIANTS)}")
    plan, splits = [], []
    for i in range(len(V)):
        for r in range(args.runs):
            e = gen(V[i], seed * 1000 + i * 100 + r)
            sp = split_explanation(e)
            splits.append(sp)
            for variant in VARIANTS:
                text = sp[variant]
                plan.append({
                    "act": i, "run": r, "variant": variant, "row": int(row_idx[i]),
                    "explanation": text,
                    # the unsplit text, on every record, so a reader of one row
                    # can see what it was cut out of
                    "explanation_full": sp["full"],
                    "split_method": sp["method"],
                    "n_chars": len(text) if text else 0,
                    "n_tokens": _ntok(text),
                    "cjk": bool(text and _CJK.search(text)),
                    # An ablation that produced no text is NOT the same failure as
                    # a broken injection, but both reach the AR as nothing. Flagged
                    # separately so they never get pooled.
                    "untagged": text is None,
                    "split_failed": sp[variant] is None and sp["full"] is not None,
                })
        done = sum(1 for x in plan
                   if x["act"] == i and x["variant"] == "full" and not x["untagged"])
        print(f"  act {i}: {done}/{args.runs} explanations")

    srep = split_report(splits)
    print(f"\n  split: {srep['usable']}/{srep['n']} usable "
          f"({srep['usable_rate']:.0%}), by method {srep['by_method']}")
    if srep["anchor_rate"] is not None and srep["anchor_rate"] < 0.9:
        print(f"  !! ANCHOR RATE {srep['anchor_rate']:.0%} -- the AV's output format has")
        print(f"     moved and the ablation may not be cutting where it claims.")
        print(f"     Inspect results/explanation_splits.json before using section 6.")
    # ~20 splits dumped for manual inspection, as the design requires: the split
    # point is the thing most likely to break silently.
    (out_dir / "explanation_splits.json").write_text(json.dumps({
        "report": srep,
        "sample": [{"method": s["method"], "n_paragraphs": s["n_paragraphs"],
                     "full": s["full"], "no_final": s["no_final"],
                     "final_only": s["final_only"]}
                    for s in splits[:20]],
    }, indent=2))
    print(f"  wrote {out_dir/'explanation_splits.json'} (20 splits to eyeball)")
    del av
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    print(f"  {sum(1 for x in plan if not x['untagged'])}/{len(plan)} extracted; AV released")

    # PHASE 2b -- reconstruct. AR only.
    print("\n--- Stage 2b: explanations -> AR reconstructions ---")
    critic = NLACritic(args.ar, device=args.device)
    assert abs(critic.mse_scale - mse_scale) < 1e-3, (
        f"mse_scale assumption wrong: computed sqrt(d_model)={mse_scale:.4f} but "
        f"the AR reports {critic.mse_scale:.4f}. Every FVE above stage 2b used "
        f"the computed value and is invalid.")
    runs, v_ar_list = [], []
    for rec in plan:
        e = rec["explanation"]
        if e is None:
            mse, cos, v_ar = FAILED_EXTRACTION_MSE, 0.0, torch.zeros(V.shape[1])
        else:
            mse, cos = critic.score(e, V[rec["act"]])
            v_ar = critic.reconstruct(e)
        v_ar_list.append(v_ar.float())
        runs.append({**rec, "mse": mse, "cos": cos})
    V_ar = torch.stack(v_ar_list)
    print(f"  {len(runs)} reconstructions")

    # ---- FVE health check. A DIAGNOSTIC, NOT A FILTER. ----
    # The paper reports ~0.752 for these checkpoints. A number far below that
    # means something is broken -- wrong layer, failed injection, mismatched
    # checkpoints -- and every downstream result would inherit it.
    #
    # An earlier version RESAMPLED until the FVE landed in [0.73, 0.77], which
    # turned a health check into selection on the outcome metric. It never
    # actually rejected a sample (the n=50 run took seed 0 at 0.7394 first try),
    # but the code could, and that is a caveat nobody should have to write.
    #
    # It is computed from the stage-2 work rather than a separate pass, which
    # also means the AV and AR never have to be resident together.
    # ON variant="full" ONLY. The ablations are EXPECTED to reconstruct worse --
    # that is the measurement -- so pooling them into the health check would drag
    # it below the band and raise a broken-pipeline warning on a healthy run.
    _full_mse = [r["mse"] for r in runs if r["variant"] == "full"]
    health_fve = fve_of(_full_mse, rawvar)
    gate_log = [{"seed": seed, "fve": health_fve, "variant": "full",
                  "note": "health check, not a filter"}]
    print(f"\n  FVE health check (variant=full): {health_fve:.4f}")
    if not (args.health_lo <= health_fve <= args.health_hi):
        print(f"  !! WARNING: outside the expected band "
              f"[{args.health_lo}, {args.health_hi}]. The paper reports ~0.752.")
        print(f"     Check: layer index (--layer-index L is hidden_states[L+1]);")
        print(f"     injection (grep the explanations for CJK); that the AV/AR")
        print(f"     checkpoints match the extraction model.")
        print(f"     Continuing -- this is a diagnostic, not a gate.")
    else:
        print(f"  within the expected band; AV/AR look healthy")
    n_untagged = sum(r["untagged"] for r in runs)
    n_cjk = sum(r["cjk"] for r in runs)
    print(f"  FVE over {len(_full_mse)} full explanations: {health_fve:.4f}"
          f"   untagged {n_untagged}/{len(runs)}   CJK {n_cjk}/{len(runs)}"
          f"   (counts span all {len(VARIANTS)} variants)")

    # ---------------- Stage 3: AR output -> SAE ----------------
    print("\n--- Stage 3: AR output activations through the SAE ---")
    A_ar = sae_encode(V_ar, P)
    V_ar_sae = sae_decode(A_ar, P)
    F_ar = [set((A_ar[k] > 0).nonzero().flatten().tolist()) for k in range(len(V_ar))]
    ar_sae_cos = [cos_of(V_ar_sae[k], V_ar[k]) for k in range(len(V_ar))]
    # PER-EXAMPLE mse for every comparison, so FVE can be recomputed for any
    # subset later without re-running. A previous version stored only the pooled
    # means and the per-run AR mse, which made "FVE for these 12 activations"
    # unanswerable without a full regeneration.
    #   A  SAE(orig) vs orig   per ACTIVATION  (sae_mse, computed in stage 1)
    #   B  AR       vs orig    per RUN         (rec["mse"], from the critic)
    #   C  SAE(AR)  vs AR      per RUN
    #   D  SAE(AR)  vs orig    per RUN
    mse_C = [norm_mse(V_ar_sae[k], V_ar[k], mse_scale) for k in range(len(V_ar))]
    mse_D = [norm_mse(V_ar_sae[k], V[runs[k]["act"]], mse_scale)
             for k in range(len(V_ar))]
    # Cosine for each comparison as well. It is recoverable from mse (they are
    # related by mse = 2(1-cos) after normalisation), but Gemma's tiny rawvar
    # means FVE magnifies cosine ~72x -- so cosine is the stable quantity to
    # eyeball, and having it stored means nobody has to re-derive it by hand.
    # THE MISSING NULL FOR B. Every other measurement in this project is
    # reported against a mismatched control; the FVE scores were not. That is a
    # real gap here, because Gemma activations sit at mean pairwise cosine 0.967
    # -- any plausible vector already scores well, so "B is high" could in
    # principle be about the distribution rather than about this activation.
    #
    # So: score each AR output against a DIFFERENT activation, paired halfway
    # across the set exactly as the latent-overlap control is. Measured at n=50,
    # a mismatched explanation gives FVE -0.66 against +0.69 matched -- WORSE
    # than predicting the mean activation, which is FVE 0 by definition. A wrong
    # explanation actively hurts, so B is about the activation it came from.
    _j = lambda k: (runs[k]["act"] + len(V) // 2) % len(V)
    mse_B_ctl = [norm_mse(V_ar[k], V[_j(k)], mse_scale) for k in range(len(V_ar))]
    cos_B_ctl = [cos_of(V_ar[k], V[_j(k)]) for k in range(len(V_ar))]
    cos_C = [cos_of(V_ar_sae[k], V_ar[k]) for k in range(len(V_ar))]
    cos_D = [cos_of(V_ar_sae[k], V[runs[k]["act"]]) for k in range(len(V_ar))]
    print(f"  L0 mean {np.mean([len(f) for f in F_ar]):.1f}   "
          f"recon cos {np.mean(ar_sae_cos):.4f}")
    print(f"  FVE  A SAE(orig)vs orig {fve_of(sae_mse, rawvar):>7.4f}"
          f"   B AR vs orig {fve_of([r['mse'] for r in runs], rawvar):>7.4f}")
    print(f"       B control: AR vs a DIFFERENT activation "
          f"{fve_of(mse_B_ctl, rawvar):>7.4f}   <- must be far below B")
    print(f"       C SAE(AR) vs AR    {fve_of(mse_C, rawvar):>7.4f}"
          f"   D SAE(AR) vs orig {fve_of(mse_D, rawvar):>7.4f}")

    # ---------------- Stage 4: set overlap ----------------
    print("\n--- Stage 4: feature-set overlap ---")
    for k, rec in enumerate(runs):
        i = rec["act"]
        fo, fa = F_orig[i], F_ar[k]
        inter = fo & fa
        # strength-weighted: losing a strong feature != losing a marginal one
        w_tot = float(A_orig[i].sum())
        w_kept = float(A_orig[i][list(inter)].sum()) if inter else 0.0
        # mismatched control: this AR feature set vs a DIFFERENT activation
        j = (i + len(V) // 2) % len(V)
        ctl = F_orig[j] & fa
        rec.update({
            "n_orig": len(fo), "n_ar": len(fa), "n_shared": len(inter),
            "n_lost": len(fo - fa), "n_invented": len(fa - fo),
            "jaccard": len(inter) / max(len(fo | fa), 1),
            "weighted_kept": w_kept / max(w_tot, 1e-9),
            "control_shared": len(ctl),
            "control_jaccard": len(ctl) / max(len(F_orig[j] | fa), 1),
            "shared_features": sorted(inter), "lost_features": sorted(fo - fa),
            "invented_features": sorted(fa - fo),
            "sae_recon_cos": ar_sae_cos[k],
            # per-example FVE, all four comparisons. mse is kept alongside so a
            # subset FVE is 1 - mean(subset mse)/rawvar rather than a mean of
            # per-example FVEs, which is not the same number.
            "mse_A_sae_orig_vs_orig": sae_mse[i], "fve_A": 1.0 - sae_mse[i] / rawvar,
            "mse_B_ar_vs_orig": rec["mse"], "fve_B": 1.0 - rec["mse"] / rawvar,
            "mse_C_sae_ar_vs_ar": mse_C[k], "fve_C": 1.0 - mse_C[k] / rawvar,
            "mse_D_sae_ar_vs_orig": mse_D[k], "fve_D": 1.0 - mse_D[k] / rawvar,
            "cos_A_sae_orig_vs_orig": sae_cos[i], "cos_B_ar_vs_orig": rec["cos"],
            "mse_B_control_wrong_expl": mse_B_ctl[k],
            "fve_B_control_wrong_expl": 1.0 - mse_B_ctl[k] / rawvar,
            "cos_B_control_wrong_expl": cos_B_ctl[k],
            "cos_C_sae_ar_vs_ar": cos_C[k], "cos_D_sae_ar_vs_orig": cos_D[k],
            "source_text": src_text[i],
            "doc_id": src_doc[i],
            **({"prompt": src_prompt[i]} if src_prompt else {}),
            **({"response": src_response[i]} if src_response else {}),
            **({"activation_token_index": src_pos[i]} if src_pos else {}),
        })

    # ---------------- Stage 5: near-miss distance sweep ----------------
    # THE EXISTING JACCARD NULL IS AN EASY ONE. It compares the rebuild against
    # an activation from an UNRELATED conversation, which shares almost nothing
    # -- 0.013 against a matched 0.540. Clearing that bar shows the rebuild is
    # not generic; it does not show the rebuild is specific to THIS TOKEN.
    #
    # The hard version: compare the rebuild of position p against the real
    # activation at p+d in the SAME conversation. Same topic, same document, same
    # speaker, a few tokens away. If Jaccard stays flat across d, the explanation
    # describes the passage and the exact position is doing no work. If it falls
    # off with |d|, the round trip is genuinely position-specific.
    #
    # No new AV or AR work -- the round trip still happens only at p. Directions
    # are kept separate throughout: text before p is context the activation
    # encodes, text after is context it cannot, so -20 and +20 are different
    # measurements and averaging them would hide any asymmetry.
    sweep = None
    _nb_flat, _nb_owner = [], []
    if nb_off_all is not None and any(nb_off_all):
        print("\n--- Stage 5: near-miss distance sweep ---")
        # Encode every neighbour once, in one batch, and index back by activation.
        for i, (offs, vecs) in enumerate(zip(nb_off_all, nb_vec_all)):
            for d, vec in zip(offs, vecs):
                _nb_flat.append(vec)
                _nb_owner.append((i, int(d)))
        flat, owner = _nb_flat, _nb_owner
        F_nb: dict[tuple[int, int], set] = {}
        if flat:
            A_nb = sae_encode(torch.tensor(flat, dtype=torch.float32), P)
            for n, (i, d) in enumerate(owner):
                F_nb[(i, d)] = set((A_nb[n] > 0).nonzero().flatten().tolist())

        offsets = sorted({d for _, d in owner})
        # A conversation supports the RESTRICTED curve only if it has every
        # offset. Without that, each point on the curve is drawn from a different
        # subset of conversations and the shape could be attrition rather than
        # distance -- short responses lose the far offsets first, and short
        # responses are not a random subsample.
        complete = {i for i in range(len(V))
                    if all((i, d) in F_nb for d in offsets)}
        print(f"  offsets {offsets}; {len(complete)}/{len(V)} activations have all of them")

        # enumerate, not runs.index(rec): index() is O(n) per call and matches by
        # VALUE, so two identical records would both resolve to the first one.
        for k, rec in enumerate(runs):
            rec["neighbor_jaccard"] = {
                str(d): (len(F_ar[k] & F_nb[(rec["act"], d)]) /
                          max(len(F_ar[k] | F_nb[(rec["act"], d)]), 1))
                for d in offsets if (rec["act"], d) in F_nb}

        def _curve(rs, restrict=None):
            out = {}
            for d in offsets:
                vals = [r["neighbor_jaccard"][str(d)] for r in rs
                        if str(d) in r["neighbor_jaccard"]
                        and (restrict is None or r["act"] in restrict)]
                out[str(d)] = {"jaccard": float(np.mean(vals)) if vals else None,
                                "n": len(vals)}
            return out

        _fr = [r for r in runs if r["variant"] == "full"]
        sweep = {
            "offsets": offsets,
            "self_match_delta0": float(np.mean([r["jaccard"] for r in _fr])),
            "unrelated_conversation_null": float(np.mean([r["control_jaccard"] for r in _fr])),
            "by_variant": {v: _curve([r for r in runs if r["variant"] == v])
                            for v in VARIANTS},
            # Same curve over only the activations long enough for every offset,
            # so the points are comparable to each other rather than each being a
            # different subsample.
            "by_variant_restricted": {
                v: _curve([r for r in runs if r["variant"] == v], restrict=complete)
                for v in VARIANTS},
            "n_activations_all_offsets": len(complete),
            "n_activations": len(V),
        }
        c = sweep["by_variant"]["full"]
        print("  variant=full:  d=0 (self) %.4f" % sweep["self_match_delta0"])
        for d in offsets:
            e = c[str(d)]
            print("                 d=%+4d      %s   n=%d"
                  % (d, ("%.4f" % e["jaccard"]) if e["jaccard"] is not None else "  -  ", e["n"]))
        print("                 unrelated  %.4f  <- the easy null" %
              sweep["unrelated_conversation_null"])

    # EVERY AGGREGATE IS PER VARIANT. Pooling the three would average an
    # explanation with two ablations of itself and mean nothing. The top-level
    # `fve`/`totals` keep reporting variant="full" so that downstream stages and
    # older artefacts keep the same contract, and `by_variant` carries all three.
    def _sub(v): return [r for r in runs if r["variant"] == v]

    def _agg(rs: list[dict]) -> dict:
        if not rs:
            return {}
        mm = lambda k: float(np.mean([r[k] for r in rs]))
        tok = [r["n_tokens"] for r in rs if r["n_tokens"] > 0]
        fve_b = fve_of([r["mse"] for r in rs], rawvar)
        return {
            "n_pairs": len(rs),
            "n_activations": len({r["act"] for r in rs}),
            "totals": {k: mm(k) for k in ("n_orig", "n_ar", "n_shared", "n_lost",
                                           "n_invented", "jaccard",
                                           "control_jaccard", "weighted_kept")},
            "fve": {"A_sae_orig_vs_orig": fve_of(sae_mse, rawvar),
                     "B_ar_vs_orig": fve_b,
                     "B_control_wrong_activation":
                         fve_of([r["mse_B_control_wrong_expl"] for r in rs], rawvar),
                     "C_sae_ar_vs_ar": fve_of([r["mse_C_sae_ar_vs_ar"] for r in rs], rawvar),
                     "D_sae_ar_vs_orig": fve_of([r["mse_D_sae_ar_vs_orig"] for r in rs], rawvar)},
            "fve_B_median": float(np.median([r["fve_B"] for r in rs])),
            "cos_B_mean": mm("cos"),
            # LENGTH, MADE VISIBLE. The variants differ in length, so a variant
            # scoring higher could simply be the one with more text. Reporting
            # FVE per token does not remove that confound -- it exposes it.
            "tokens_mean": float(np.mean(tok)) if tok else 0.0,
            "tokens_median": float(np.median(tok)) if tok else 0.0,
            "chars_mean": mm("n_chars"),
            "fve_B_per_100_tokens": (100.0 * fve_b / float(np.mean(tok))) if tok else None,
            "n_split_failed": sum(1 for r in rs if r.get("split_failed")),
            "n_untagged": sum(1 for r in rs if r["untagged"]),
            "n_cjk": sum(1 for r in rs if r["cjk"]),
        }

    by_variant = {v: _agg(_sub(v)) for v in VARIANTS}
    full_runs = _sub("full") or runs

    def m(key): return float(np.mean([r[key] for r in full_runs]))
    print("\n  --- per variant (paragraph ablation) ---")
    print("  %-11s %7s %7s %8s %8s %8s %7s" %
          ("variant", "FVE B", "median", "cos", "Jaccard", "shared", "tokens"))
    for v in VARIANTS:
        d = by_variant[v]
        if not d:
            continue
        print("  %-11s %+7.4f %+7.4f %8.5f %8.4f %8.1f %7.0f" %
              (v, d["fve"]["B_ar_vs_orig"], d["fve_B_median"], d["cos_B_mean"],
               d["totals"]["jaccard"], d["totals"]["n_shared"], d["tokens_mean"]))
    print()
    print(f"  |F_orig| {m('n_orig'):.1f}   |F_ar| {m('n_ar'):.1f}")
    print(f"  shared   {m('n_shared'):.1f}   lost {m('n_lost'):.1f}   "
          f"invented {m('n_invented'):.1f}")
    print(f"  Jaccard  matched {m('jaccard'):.4f}   control {m('control_jaccard'):.4f}"
          f"   gap {m('jaccard')-m('control_jaccard'):+.4f}")
    print(f"  strength-weighted fraction of the original kept: {m('weighted_kept'):.4f}")

    # ---------------- outputs ----------------
    np.savez_compressed(
        out_dir / "feature_overlap_vectors.npz",
        v_orig=V.numpy().astype(np.float32),
        v_orig_sae=V_sae.numpy().astype(np.float32),
        v_ar=V_ar.numpy().astype(np.float32),
        v_ar_sae=V_ar_sae.numpy().astype(np.float32),
        row_idx=np.array([int(r) for r in row_idx]),
        run_act=np.array([r["act"] for r in runs]),
        run_idx=np.array([r["run"] for r in runs]),
        # which ablation each v_ar row came from, so the saved vectors
        # can be split by variant without re-reading the JSON
        run_variant=np.array([r["variant"] for r in runs]),
        # Near-miss neighbours, flattened, with an (activation, offset) index so
        # refeature.py can redo the distance sweep under the other SAE without
        # re-reading the parquet or re-running Gemma. Empty arrays when the
        # corpus predates them.
        v_neighbor=(np.array(_nb_flat, dtype=np.float32) if _nb_flat
                     else np.zeros((0, V.shape[1]), dtype=np.float32)),
        neighbor_act=np.array([i for i, _ in _nb_owner], dtype=np.int64),
        neighbor_delta=np.array([d for _, d in _nb_owner], dtype=np.int64),
    )
    (out_dir / "feature_overlap.json").write_text(json.dumps({
        "config": vars(args), "seed_used": seed, "rawvar": rawvar,
        "gate_log": gate_log,
        "source_text": src_text,
        "doc_id": src_doc,
        "n_documents": n_docs,
        "stage1": {"F_orig": [sorted(f) for f in F_orig],
                    "strengths": [{int(j): float(A_orig[i][j]) for j in sorted(F_orig[i])}
                                   for i in range(len(V))],
                    "sae_cos": sae_cos, "sae_fve": fve_of(sae_mse, rawvar)},
        "runs": runs,
        # variant="full" -- the unmodified explanation. Downstream code that
        # predates the ablation reads these and keeps reporting the primary
        # result rather than an average over an explanation and two ablations.
        "totals": {k: m(k) for k in ("n_orig", "n_ar", "n_shared", "n_lost",
                                      "n_invented", "jaccard", "control_jaccard",
                                      "weighted_kept")},
        "fve": {"A_sae_orig_vs_orig": fve_of(sae_mse, rawvar),
                 "B_ar_vs_orig": fve_of([r["mse"] for r in full_runs], rawvar),
                 "C_sae_ar_vs_ar": fve_of([r["mse_C_sae_ar_vs_ar"] for r in full_runs], rawvar),
                 "D_sae_ar_vs_orig": fve_of([r["mse_D_sae_ar_vs_orig"] for r in full_runs], rawvar)},
        "variants": list(VARIANTS),
        "by_variant": by_variant,
        "split_report": srep,
        "distance_sweep": sweep,
        "sanity": {"untagged": n_untagged, "cjk": n_cjk,
                    "fve_all_runs": fve_of([r["mse"] for r in full_runs], rawvar)},
    }, indent=2))
    print(f"\nwrote {out_dir/'feature_overlap.json'}")
    print(f"wrote {out_dir/'feature_overlap_vectors.npz'}")


if __name__ == "__main__":
    main()
