"""Baseline round-trip FVE for a released NLA pair — the number to beat.

Measures the published metric end-to-end:

    gold activation h  →  AV verbalizes  →  explanation z  →  AR reconstructs  →  ĥ
    per-sample MSE = ((normalize(ĥ) − normalize(h))**2).mean()      [ = 2(1 − cos) ]
    FVE            = 1 − mean(MSE) / rawvar_baseline

Target for `kitft/nla-qwen2.5-7b-L20-{av,ar}`: **fve_nrm ≈ 0.752**.

Fidelity notes — every choice here mirrors the training-time path so the number
is comparable to the published one:

  * MSE math is identical to `nla/reward.py::_mse_to_reward` — both pred and gold
    are L2-normalized to `mse_scale` (√d_model), then `.mean()`. That is exactly
    what `NLACritic.score()` does.
  * FVE formula is `nla/loss.py:110`: `1 − mean_loss / nla_baseline_rawvar`.
  * The rawvar denominator comes from `schema.load_predict_mean_baselines`, which
    uses the **un-normalized** mean μ (the classical FVE definition, ≈0.72 for
    Qwen L20). Normalizing μ inflates the denominator to ≈0.94 and therefore
    inflates FVE — that's the documented footgun.
  * Explanation extraction uses `schema.extract_explanation` (the same function
    training uses). On a tag miss, training assigns the orthogonal-equivalent
    penalty rather than dropping the sample — see `reward.py:38`. We do the same,
    because silently excluding failures would inflate FVE.
  * Sampling temperature defaults to 1.0 — the paper samples the AV at T=1.
    (Note `nla_inference.py`'s CLI defaults to 0.7; don't use that for a headline
    number.)

ALL scale parameters (`injection_scale`, `mse_scale`, `d_model`, prompt
templates, token IDs) are loaded from each checkpoint's `nla_meta.yaml` sidecar
and asserted against the live tokenizer — never hardcoded. See CLAUDE.md,
"Sidecar is the contract."

─────────────────────────────────────────────────────────────────────────────
Prerequisites

1. SGLang serving the AV checkpoint (--disable-radix-cache is MANDATORY;
   input_embeds requests carry no token IDs, so cache entries alias):

     python -m sglang.launch_server --model-path ./av --port 30000 \
         --disable-radix-cache --mem-fraction-static 0.85 --trust-remote-code

2. A parquet with an `activation_vector` column. Produce it with stage0 so the
   extraction matches the training data (in particular _MIN_POSITION = 50):

     python -m nla.datagen.stage0_extract \
         --base-model Qwen/Qwen2.5-7B-Instruct \
         --corpus HuggingFaceFW/fineweb --corpus-config sample-10BT \
         --corpus-length 50 --layer-index 20 --positions-per-doc 10 \
         --output acts_test.parquet

   Use DISJOINT `--corpus-start` ranges for test / val / train. stage0 samples 10
   positions per document, so a row-level split would leak near-duplicates of the
   same document into both sides. See CLAUDE.md, "Stage-1 split is DOCUMENT-level".

   NOTE the layer convention: `--layer-index 20` is the output of decoder block
   20, which equals HF's `hidden_states[21]` (index 0 is the embedding output).
   See `extractors.HFExtractor` docstring. The README's quick snippet uses
   `hidden_states[20]` — fine for a smoke test, WRONG by one layer for a
   baseline measurement.

Usage

    python experiments/baseline_fve.py \
        --av ./av --ar ./ar --parquet acts_test.parquet --n 500 \
        --sglang-url http://localhost:30000 --out runs/baseline_seed0.json

Run it 3× with different --seed to establish the noise floor (the AV samples
stochastically, so FVE varies run to run). Any future improvement must exceed
that spread to mean anything.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import torch

# Line-buffer stdout even when redirected to a file (nohup, tee, etc.). Default
# Python buffering is block-buffered for non-tty destinations, so progress
# prints can sit invisible in an internal buffer for many minutes on a slow
# run — indistinguishable from a hang when tailing the log live. Cost real
# confusion once; not leaving it for anyone running this unattended.
sys.stdout.reconfigure(line_buffering=True)

# Repo root on path: `nla_inference` is a root-level standalone module and `nla`
# is the package beside it. Keeps this experiment script out of the upstream
# package tree while still importing both.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nla.schema import (  # noqa: E402
    ACTIVATION_COLUMN,
    compute_predict_mean_baselines,
    extract_explanation,
    load_predict_mean_baselines,
)
from nla_inference import NLAClient, NLACritic  # noqa: E402

# Training's penalty for an unparseable rollout (reward.py:38 uses -2.0 as the
# reward, i.e. MSE = 2.0 — the orthogonal-equivalent). Reusing the same value
# keeps a tag-miss from being scored more favourably here than in training.
FAILED_EXTRACTION_MSE = 2.0


def load_vectors(
    parquet_path: str, n: int, seed: int, pool_cap: int = 50_000
) -> tuple[torch.Tensor, list[int], list[int | None]]:
    """Read up to `pool_cap` rows, then random-sample `n` of them.

    Random-sampling rather than head-slicing matters: stage0 writes rows grouped
    by document, so the first N rows come from only a handful of docs and are
    not representative. Seeded so the same --seed selects the same rows.

    Returns (vectors [N, d] float32, chosen row indices, n_raw_tokens or Nones).
    """
    pf = pq.ParquetFile(parquet_path)
    cols = set(pf.schema_arrow.names)
    want = [ACTIVATION_COLUMN] + (["n_raw_tokens"] if "n_raw_tokens" in cols else [])

    chunks: list[np.ndarray] = []
    positions: list[int | None] = []
    total = 0
    for batch in pf.iter_batches(batch_size=8192, columns=want):
        col = batch.column(ACTIVATION_COLUMN)
        # .flatten() → values buffer, works for both FixedSizeList (stage0's
        # schema) and variable-length ListArray (the README's quick snippet).
        flat = col.flatten().to_numpy(zero_copy_only=False).astype(np.float32)
        chunks.append(flat.reshape(len(col), -1))
        if "n_raw_tokens" in want:
            positions.extend(batch.column("n_raw_tokens").to_pylist())
        else:
            positions.extend([None] * len(col))
        total += len(col)
        if total >= pool_cap:
            break

    pool = np.concatenate(chunks, axis=0)
    assert len(pool) > 0, f"no rows in {parquet_path!r}"
    if n > len(pool):
        print(f"[warn] requested n={n} but parquet has {len(pool)} rows — using all")
        n = len(pool)

    idx = np.random.default_rng(seed).choice(len(pool), size=n, replace=False)
    idx.sort()  # keep parquet order for readable logs
    return (
        torch.from_numpy(pool[idx]),
        idx.tolist(),
        [positions[i] for i in idx],
    )


def summarize(values: list[float]) -> dict[str, float]:
    a = np.asarray(values, dtype=np.float64)
    return {
        "mean": float(a.mean()),
        "std": float(a.std(ddof=1)) if len(a) > 1 else 0.0,
        "p10": float(np.percentile(a, 10)),
        "median": float(np.median(a)),
        "p90": float(np.percentile(a, 90)),
        "min": float(a.min()),
        "max": float(a.max()),
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--av", required=True, help="AV (actor) checkpoint dir, with nla_meta.yaml")
    ap.add_argument("--ar", required=True, help="AR (critic) checkpoint dir, with nla_meta.yaml + value_head.safetensors")
    ap.add_argument("--parquet", required=True, help="parquet with an activation_vector column")
    ap.add_argument("--sglang-url", default="http://localhost:30000")
    ap.add_argument("--n", type=int, default=500, help="activations to score")
    ap.add_argument("--seed", type=int, default=0, help="selects rows AND labels the run")
    ap.add_argument("--temperature", type=float, default=1.0,
                    help="AV sampling temperature. 1.0 matches training — do not "
                         "use nla_inference.py's 0.7 CLI default for headline numbers.")
    ap.add_argument("--max-new-tokens", type=int, default=200,
                    help="RL capped rollouts at 150; 200 gives headroom so "
                         "explanations aren't truncated before </explanation>.")
    ap.add_argument("--device", default="cuda", help="device for the AR forward pass")
    ap.add_argument("--out", default=None, help="write per-sample results + summary JSON here")
    ap.add_argument("--print-every", type=int, default=25)
    args = ap.parse_args()

    print("=" * 72)
    print("NLA baseline round-trip FVE")
    print("=" * 72)

    gold, row_idx, positions = load_vectors(args.parquet, args.n, args.seed)
    print(f"[data] {len(gold)} vectors from {args.parquet} (seed={args.seed})")

    client = NLAClient(args.av, sglang_url=args.sglang_url)
    critic = NLACritic(args.ar, device=args.device)

    # Sidecar cross-checks. d_model must agree across parquet / AV / AR, else
    # you're scoring one model's vectors with another's checkpoint.
    assert gold.shape[1] == client.cfg.d_model, (
        f"parquet d={gold.shape[1]} != AV sidecar d_model={client.cfg.d_model}. "
        f"Wrong parquet for this checkpoint."
    )
    print(f"[cfg] injection_scale={client.cfg.injection_scale}  "
          f"mse_scale={critic.mse_scale:.4f}  d_model={client.cfg.d_model}")
    print(f"[cfg] temperature={args.temperature}  max_new_tokens={args.max_new_tokens}")

    # Computed once, up front — neither depends on loop progress (gold is
    # fully selected before the loop starts, rawvar_full is a full-parquet
    # stat), so they're available for a partial write at any point, not just
    # after the loop completes.
    _, rawvar_full = load_predict_mean_baselines(args.parquet, critic.mse_scale)
    _, rawvar_subset = compute_predict_mean_baselines(gold, critic.mse_scale)

    def write_results(records: list[dict], mses: list[float], coses: list[float],
                       n_untagged: int, elapsed_sec: float, *, is_partial: bool) -> None:
        # Same shape written mid-run (partial) and at the end (complete) —
        # an interrupted run leaves the last partial write sitting at --out,
        # not nothing. A prior version of this script only wrote once, at
        # the very end; a run interrupted at n=490/500 left zero recoverable
        # per-sample data despite having scored 490 real activations.
        if not args.out or not records:
            return
        mean_mse = float(np.mean(mses))
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "config": {
                "av": args.av, "ar": args.ar, "parquet": args.parquet,
                "n": len(gold), "n_scored_so_far": len(records), "seed": args.seed,
                "temperature": args.temperature, "max_new_tokens": args.max_new_tokens,
                "injection_scale": client.cfg.injection_scale, "mse_scale": critic.mse_scale,
                "d_model": client.cfg.d_model,
            },
            "results": {
                "is_partial": is_partial,
                "fve_nrm": 1.0 - mean_mse / rawvar_full,
                "fve_nrm_subset_baseline": 1.0 - mean_mse / rawvar_subset,
                "mean_mse": mean_mse,
                "rawvar_full": rawvar_full,
                "rawvar_subset": rawvar_subset,
                "cos": summarize(coses),
                "mse": summarize(mses),
                "n_untagged": n_untagged,
                "elapsed_sec": elapsed_sec,
            },
            "samples": records,
        }, indent=2))

    mses: list[float] = []
    coses: list[float] = []
    records: list[dict] = []
    n_untagged = 0
    t0 = time.time()

    for i, v in enumerate(gold):
        raw = client.generate(
            v.numpy(),
            temperature=args.temperature,
            max_new_tokens=args.max_new_tokens,
            extract_explanation=False,   # we parse with schema.extract_explanation
        )
        expl = extract_explanation(raw)

        if expl is None:
            # Match training: penalise, don't drop. Dropping would inflate FVE
            # by scoring only the samples the AV happened to format correctly.
            n_untagged += 1
            mse, cos = FAILED_EXTRACTION_MSE, 0.0
        else:
            mse, cos = critic.score(expl, v)

        mses.append(mse)
        coses.append(cos)
        records.append({
            "row": row_idx[i],
            "n_raw_tokens": positions[i],
            "gold_norm": float(v.norm()),
            "explanation": expl,
            "raw_len_chars": len(raw),
            "mse": mse,
            "cos": cos,
        })

        # Print the first two decodes IN FULL. This is the single best
        # correctness check in the whole pipeline: readable English means
        # injection worked; all-CJK (or English describing a CJK character)
        # means injection failed and every number below is meaningless.
        if i < 2:
            print(f"\n─── decode [{i}]  ‖v‖={v.norm():.1f}  cos={cos:.3f} ───")
            print((expl or raw)[:600])
            print()

        if (i + 1) % args.print_every == 0 or i + 1 == len(gold):
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            eta = (len(gold) - i - 1) / rate if rate > 0 else 0
            print(f"[{i+1:>5}/{len(gold)}] running cos={np.mean(coses):.4f}  "
                  f"mse={np.mean(mses):.4f}  {rate:.2f} it/s  eta={eta/60:.1f}m")
            write_results(records, mses, coses, n_untagged, elapsed, is_partial=(i + 1 < len(gold)))

    # ── FVE ────────────────────────────────────────────────────────────────
    # Headline denominator over the FULL parquet (up to schema's 50k cap), which
    # is what training does when it sets nla_baseline_rawvar — a large-sample
    # variance estimate is stabler than one over a few hundred scored rows.
    # We also report the subset denominator; a large gap means n is too small
    # for the scored sample to represent the distribution.
    mean_mse = float(np.mean(mses))
    fve = 1.0 - mean_mse / rawvar_full
    fve_subset = 1.0 - mean_mse / rawvar_subset

    print("\n" + "=" * 72)
    print(f"FVE (fve_nrm)          : {fve:.4f}      ← headline; target ≈ 0.752")
    print(f"  mean MSE             : {mean_mse:.4f}")
    print(f"  rawvar baseline      : {rawvar_full:.4f}  (full parquet)")
    print(f"  FVE w/ subset rawvar : {fve_subset:.4f}  ({rawvar_subset:.4f}) — sanity only")
    print("-" * 72)
    cs = summarize(coses)
    print(f"cos  mean={cs['mean']:.4f}  median={cs['median']:.4f}  "
          f"p10={cs['p10']:.4f}  p90={cs['p90']:.4f}  min={cs['min']:.4f}")
    print(f"untagged (no <explanation>): {n_untagged}/{len(gold)} "
          f"({100*n_untagged/len(gold):.1f}%) — scored as MSE={FAILED_EXTRACTION_MSE}")
    print("=" * 72)

    if fve < 0.6:
        print(
            "\n[!] Well below the published 0.752. Check, in order:\n"
            "    1. LAYER OFF-BY-ONE — stage0 --layer-index 20 == HF hidden_states[21].\n"
            "       If you hand-rolled extraction with hidden_states[20], that's layer 19.\n"
            "    2. Decodes above: CJK soup ⇒ injection failed (wrong injection_scale,\n"
            "       double-BOS, or missing --disable-radix-cache).\n"
            "    3. AR BOS invariant — reconstruct() must tokenize with\n"
            "       add_special_tokens=True (Gemma fve 0.77 → 0.31 without it).\n"
            "    4. Early positions — stage0's _MIN_POSITION=50 filter should\n"
            "       already handle this; a hand-rolled parquet may not.\n"
        )

    if args.out:
        write_results(records, mses, coses, n_untagged, time.time() - t0, is_partial=False)
        print(f"\nwrote {args.out}  ({len(records)} per-sample records)")
        print("Per-sample records are keyed by parquet `row` — keep them; the "
              "affine-map comparison later is PAIRED on the same rows.")


if __name__ == "__main__":
    main()
