# Results artefacts

Every number in [`../RESULTS.md`](../RESULTS.md) comes from these files. All are
from the same run: **50 Gemma-3-12B-IT layer-32 activations**, 5 sampled
explanations each, Gemma-generated rollouts.

| file | what is in it |
|---|---|
| `feature_overlap.json` | the round trip. 250 runs with the **AV's explanation**, the **source text**, per-example MSE **and** FVE for all four comparisons (A–D), feature sets, the FVE gate log |
| `feature_overlap_l0_small.json` | feature sets re-encoded at L0≈21 — used for anything about feature *meaning* |
| `feature_overlap_l0_big.json` | feature sets re-encoded at L0≈120 — used for the reconstruction claim |
| `feature_labels.json` | 1,624 labels, each with its **AUC** and the **wrong-label null scores** it was validated against. `reliable: true` means it beat the 95th percentile of that null |
| `grounding.json` | per (feature, explanation): the grade (`CLEARLY`/`PROBABLY`/`UNCLEAR`/`NO`), the verdict, **both null rates**, and the label's AUC |
| `feature_classification.json` | per feature: grammar-vs-content, generic-vs-specific, and whether it is actually present in the source text, **with a control on a different document** |
| `bucket_descriptions.json` | blind English summaries of shared/lost/made, plus a control summary from a different activation |
| `FEATURES_BY_BUCKET.md` | readable: every validated label grouped by bucket, per activation, with the AV explanation and source text. No model inference anywhere |
| `example_reports/` | six worked trust reports from `src/trust_report.py` |

## Not included

`feature_overlap_vectors.npz` (6.5 MB) holds all four vector families —
`v_orig`, `v_orig_sae`, `v_ar`, `v_ar_sae` — and the corpus parquet (3 MB) holds
the activations and source text. Both are excluded by `.gitignore` as binary
artefacts; regenerate with `scripts/run_pipeline.sh`, or ask for them directly.

The `.npz` is what a later probe would need: fit a direction separating
AR-reconstructed activations from real ones, with `v_orig_sae` available so the
SAE's own reconstruction error can be subtracted out rather than confounded with
the AR effect.

## Reading the JSON

```python
import json
g = json.load(open("grounding.json"))
g["validation"]          # FPR, matcher AUC, self-consistency, grade counts
g["rows"][0]             # one (feature, explanation) judgement

o = json.load(open("feature_overlap.json"))
o["fve"]                 # the four pooled FVEs
o["runs"][0]["fve_B"]    # per-example FVE, AR vs original
o["source_text"][0]      # the document behind activation 0
o["gate_log"]            # every seed the FVE gate tried
```

**Check `gate_log` before quoting anything.** The gate selects activations
scoring 0.73–0.77 FVE, so they are easier than average by construction. It is
logged rather than hidden.
