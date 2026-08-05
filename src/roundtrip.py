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

from nla_av import ThinkingAV                                    # noqa: E402
from sampling import FAILED_EXTRACTION_MSE, load_vectors          # noqa: E402
from nla.schema import load_predict_mean_baselines                    # noqa: E402
from nla_inference import NLACritic                                   # noqa: E402

from hf_paths import sae_variant_dir, L0_SMALL, L0_BIG  # noqa: E402

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
    ap.add_argument("--seed", type=int, default=0, help="starting seed for the gate")
    ap.add_argument("--max-seed-tries", type=int, default=25)
    ap.add_argument("--gate-lo", type=float, default=0.73)
    ap.add_argument("--gate-hi", type=float, default=0.77)
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
    av = ThinkingAV(args.av, device=args.device, prompt_style="metacognitive")
    critic = NLACritic(args.ar, device=args.device)
    _, rawvar = load_predict_mean_baselines(args.parquet, critic.mse_scale)
    print(f"[cfg] rawvar={rawvar:.4f}  mse_scale={critic.mse_scale:.4f} "
          f"injection_scale={av.cfg.injection_scale}  embed_scale={av.embed_scale:.4f}")

    def gen(v, seed):
        torch.manual_seed(seed)
        _r, _t, e, _c = av.generate(v, use_thinking=False, temperature=args.temperature,
                                    thinking_max_tokens=64,
                                    explanation_max_tokens=args.explanation_max_tokens,
                                    do_sample=True)
        return e

    # ---------------- Stage 0: sample + FVE gate ----------------
    # The gate SELECTS ACTIVATIONS ON THE OUTCOME METRIC, so the chosen 10 are
    # easier than average by construction. Every seed tried is logged so the
    # selection is visible rather than hidden.
    print("\n--- Stage 0: FVE gate (target "
          f"[{args.gate_lo}, {args.gate_hi}]) ---")
    gate_log, chosen = [], None
    for t in range(args.max_seed_tries):
        seed = args.seed + t
        V, row_idx, _ = load_vectors(args.parquet, args.n, seed)
        mses = []
        for i, v in enumerate(V):
            e = gen(v, seed * 1000 + i)
            mses.append(FAILED_EXTRACTION_MSE if e is None else critic.score(e, v)[0])
        f = fve_of(mses, rawvar)
        gate_log.append({"seed": seed, "fve": f})
        ok = args.gate_lo <= f <= args.gate_hi
        print(f"  seed {seed:>3}: FVE={f:.4f}  {'PASS' if ok else 'reject'}")
        if ok:
            chosen = (seed, V, row_idx); break
    if chosen is None:
        print(f"\nNo seed in {args.max_seed_tries} tries hit the gate. "
              f"Best: {max(g['fve'] for g in gate_log):.4f}. Stopping.")
        (out_dir / "feature_overlap_gate_failed.json").write_text(
            json.dumps({"gate_log": gate_log}, indent=2))
        return
    seed, V, row_idx = chosen
    print(f"  -> using seed {seed}, rows {list(map(int, row_idx))}")

    # SOURCE TEXT, carried through to the results. An earlier run stored only the
    # parquet row index; the parquet then died with its pod and the rollout
    # responses were generated unseeded, so the text behind those results is gone
    # for good and no by-eye check against it is possible. Never again.
    import pyarrow.parquet as _pq
    _txt = _pq.ParquetFile(args.parquet).read(
        columns=["detokenized_text_truncated"]).column(0).to_pylist()
    src_text = [_txt[int(r)][-1200:] for r in row_idx]
    print(f"  -> carried {len(src_text)} source texts into the results")

    # ---------------- Stage 1: original -> SAE ----------------
    print("\n--- Stage 1: original activations through the SAE ---")
    A_orig = sae_encode(V, P)
    V_sae = sae_decode(A_orig, P)
    F_orig = [set((A_orig[i] > 0).nonzero().flatten().tolist()) for i in range(len(V))]
    sae_cos = [cos_of(V_sae[i], V[i]) for i in range(len(V))]
    sae_mse = [norm_mse(V_sae[i], V[i], critic.mse_scale) for i in range(len(V))]
    print(f"  L0 mean {np.mean([len(f) for f in F_orig]):.1f}   "
          f"recon cos {np.mean(sae_cos):.4f}   FVE {fve_of(sae_mse, rawvar):.4f}")

    # ---------------- Stage 2: original -> AV -> AR ----------------
    print(f"\n--- Stage 2: AV->AR, {args.runs} runs per activation ---")
    runs, v_ar_list = [], []
    for i in range(len(V)):
        for r in range(args.runs):
            e = gen(V[i], seed * 1000 + i * 100 + r)
            if e is None:
                mse, cos, v_ar = FAILED_EXTRACTION_MSE, 0.0, torch.zeros(V.shape[1])
            else:
                mse, cos = critic.score(e, V[i])
                v_ar = critic.reconstruct(e)          # AR's predicted activation
            v_ar_list.append(v_ar.float())
            runs.append({"act": i, "run": r, "row": int(row_idx[i]),
                         "explanation": e, "mse": mse, "cos": cos,
                         "cjk": bool(e and _CJK.search(e)), "untagged": e is None})
        print(f"  act {i}: cos " +
              " ".join(f"{x['cos']:.3f}" for x in runs[-args.runs:]))
    V_ar = torch.stack(v_ar_list)
    n_untagged = sum(r["untagged"] for r in runs)
    n_cjk = sum(r["cjk"] for r in runs)
    print(f"  FVE over all {len(runs)} runs: {fve_of([r['mse'] for r in runs], rawvar):.4f}"
          f"   untagged {n_untagged}/{len(runs)}   CJK {n_cjk}/{len(runs)}")

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
    mse_C = [norm_mse(V_ar_sae[k], V_ar[k], critic.mse_scale) for k in range(len(V_ar))]
    mse_D = [norm_mse(V_ar_sae[k], V[runs[k]["act"]], critic.mse_scale)
             for k in range(len(V_ar))]
    print(f"  L0 mean {np.mean([len(f) for f in F_ar]):.1f}   "
          f"recon cos {np.mean(ar_sae_cos):.4f}")
    print(f"  FVE  A SAE(orig)vs orig {fve_of(sae_mse, rawvar):>7.4f}"
          f"   B AR vs orig {fve_of([r['mse'] for r in runs], rawvar):>7.4f}")
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
            "source_text": src_text[i],
        })

    def m(key): return float(np.mean([r[key] for r in runs]))
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
    )
    (out_dir / "feature_overlap.json").write_text(json.dumps({
        "config": vars(args), "seed_used": seed, "rawvar": rawvar,
        "gate_log": gate_log,
        "source_text": src_text,
        "stage1": {"F_orig": [sorted(f) for f in F_orig],
                    "strengths": [{int(j): float(A_orig[i][j]) for j in sorted(F_orig[i])}
                                   for i in range(len(V))],
                    "sae_cos": sae_cos, "sae_fve": fve_of(sae_mse, rawvar)},
        "runs": runs,
        "totals": {k: m(k) for k in ("n_orig", "n_ar", "n_shared", "n_lost",
                                      "n_invented", "jaccard", "control_jaccard",
                                      "weighted_kept")},
        "fve": {"A_sae_orig_vs_orig": fve_of(sae_mse, rawvar),
                 "B_ar_vs_orig": fve_of([r["mse"] for r in runs], rawvar),
                 "C_sae_ar_vs_ar": fve_of(mse_C, rawvar),
                 "D_sae_ar_vs_orig": fve_of(mse_D, rawvar)},
        "sanity": {"untagged": n_untagged, "cjk": n_cjk,
                    "fve_all_runs": fve_of([r["mse"] for r in runs], rawvar)},
    }, indent=2))
    print(f"\nwrote {out_dir/'feature_overlap.json'}")
    print(f"wrote {out_dir/'feature_overlap_vectors.npz'}")


if __name__ == "__main__":
    main()
