# Results

Does the AV's final paragraph — shown by loops (LessWrong, 15 May 2026) to
carry most of the round trip's FVE — also carry more of what is genuinely in
the activation? Tested using an SAE as a witness independent of the AV and AR.

All numbers regenerate from `results/SUMMARY.md` (`src/summarize_results.py`).
200 activations, one explanation each, 200 distinct conversations. Methodology:
[METHODOLOGY.md](METHODOLOGY.md).

---

## The central table

| | full explanation | first two paragraphs | final paragraph |
|---|---:|---:|---:|
| **1. FVE** | +0.691 | +0.268 (39% of full) | +0.582 (84% of full) |
| **2. latents recovered** — SAE vs SAE, no text | 70.2% | 30.1% (43% of full) | 58.9% (84% of full) |
| **3. grounded, of labeled** F_orig latents | 43.0% | 19.6% (46% of full) | 41.6% (97% of full) |
| **4. grounded, of ALL** F_orig latents | 19.5% | 8.9% (46% of full) | 18.9% (97% of full) |

Row 3 denominator: 1,834 labelled F_orig latents. Row 4 denominator: 4,036, all
F_orig latents whether labelled or not.

## Reconstruction (SAE: `l0_big`)

| | FVE | implied cosine |
|---|---:|---:|
| A — SAE vs original | 0.561 | 0.99357 |
| B — NLA round trip vs original | 0.691 | 0.99547 |
| C — SAE vs AR output | 0.696 | 0.99555 |
| D — SAE(AR) vs original | 0.444 | 0.99184 |
| B, control — AR vs a **different** activation | −0.772 | — |

L0: original 119.2, AR output 97.0. `rawvar` 0.0293.

## Latent overlap and its control (SAE: `l0_small`)

| | shared | lost | made | total |
|---|---:|---:|---:|---:|
| count | 2,834 | 1,202 | 959 | 4,995 |
| share | 56.7% | 24.1% | 19.2% | 100% |

| Jaccard | value |
|---|---:|
| matched — rebuild vs its own activation | 0.572 |
| control — rebuild vs an **unrelated** activation | 0.006 |
| ratio | 99.9× |

## Labels and their null

| | n | mean AUC |
|---|---:|---:|
| attempted | 3,329 | 0.751 |
| validated (beat the wrong-label null) | 1,771 (53%) | 0.880 |
| wrong-label null | — | 0.485 |

## Judge and its two nulls

| | value |
|---|---:|
| false-positive rate | 4.6% |
| AUC vs `null_expl` (unrelated explanations) | 0.783 |
| AUC vs `null_feat` (latents that never fired) | 0.808 |
| monotonicity violations, 2,414 latents judged under both a segment and `full` | 0 |
| false-positive rate spread across variants | 0.037 |

## Near-miss sweep (SAE: `l0_big`)

Rebuild of position *p* vs the real activation at *p + d*, same conversation.

| offset | Jaccard | n |
|---|---:|---:|
| self (*d* = 0) | 0.441 | — |
| *d* = −50 | 0.054 | 159 |
| *d* = −20 | 0.062 | 187 |
| *d* = −5 | 0.083 | 196 |
| *d* = +5 | 0.078 | 197 |
| *d* = +20 | 0.061 | 182 |
| *d* = +50 | 0.053 | 164 |
| unrelated conversation | 0.025 | — |

Nearest offset retains 19% of the self-match; furthest retains 12%.

## FVE vs. grounding, per activation

Pearson r, within one variant, between an activation's FVE and its own share of
grounded latents.

| variant | n | r | 95% CI |
|---|---:|---:|---|
| `full` | 188 | −0.014 | −0.157 to +0.129 |
| `no_final` | 191 | −0.082 | −0.221 to +0.061 |
| `final_only` | 189 | +0.068 | −0.075 to +0.209 |

---

## Limitations

- 200 activations, one model, one layer, one corpus.
- Corpus may be in-sample for the SAE — [METHODOLOGY.md](METHODOLOGY.md) §2.
- Judge false-negative rate not measured at scale. A 40-pair hand audit of an
  earlier judge version: missed 8, over-called 0.
- 45% of F_orig latents are labelled; row 4 treats the rest as unconveyed.
