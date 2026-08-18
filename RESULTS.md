# Results

loops (LessWrong, 15 May 2026) found that on this same checkpoint, cutting the
AV's final paragraph costs far more reconstruction error (FVE) than cutting the
first two — the final paragraph carries most of the round trip. That is a claim
about FVE. It leaves open whether the final paragraph also carries more of what
is genuinely *in* the activation, or only more of what the AR happens to be able
to rebuild. This tests that, using an SAE as a witness independent of both the
AV and AR.

All numbers below regenerate from `results/SUMMARY.md` — quote from there, not
from here. 200 activations, one explanation each, from 200 distinct
conversations. Methodology: [METHODOLOGY.md](METHODOLOGY.md).

---

## The central result

| | full explanation | first two paragraphs | final paragraph |
|---|---:|---:|---:|
| **1. FVE** | +0.691 | +0.268 (39% of full) | +0.582 (**84%** of full) |
| **2. latents recovered** — SAE vs SAE, no text involved | 70.2% | 30.1% (43% of full) | 58.9% (**84%** of full) |
| **3. grounded, of labeled** F_orig latents — judge reads the text | 43.0% | 19.6% (46% of full) | 41.6% (**97%** of full) |
| **4. grounded, of ALL** F_orig latents (conservative) | 19.5% | 8.9% (46% of full) | 18.9% (**97%** of full) |

Rows 1–2 need no judge or labels — the SAE checking its own vectors. Rows 3–4
need both. All four agree: the final paragraph keeps ~84% of the round trip's
raw signal and ~97% of what a reader can actually confirm the explanation
states. **Two independent measurements — raw latent overlap, and an LLM judge
reading text against labelled latents — agree on where the content is.**

Row 4's denominator is every latent genuinely in the activation, whether or not
it could be labelled (4,036 total; 1,834 labelled). Row 4 is lower than row 3 by
construction, not by a separate finding.

## Does FVE predict grounding, activation by activation?

The table above answers this **between paragraph variants**. Within one variant,
**between activations**, it does not: an activation the AR reconstructs well is
no more likely to be one whose latents the explanation actually names.

| variant | n | Pearson r | 95% CI |
|---|---:|---:|---|
| `full` | 188 | −0.014 | −0.157 to +0.129 |
| `no_final` | 191 | −0.082 | −0.221 to +0.061 |
| `final_only` | 189 | +0.068 | −0.075 to +0.209 |

No correlation detectable in any variant — at this n, \|r\| under ~0.14 cannot be
told from zero. FVE tracks grounding at the level of *which part of the text*,
not at the level of *which activation*.

## Supporting measurements

- **The round trip beats the SAE reconstructing itself.** AR-vs-original FVE
  0.691 against the SAE's own A-vs-original 0.561 (gap +0.129) — the text
  bottleneck is not simply worse than the SAE's own lossy encoding.
- **Both against their own controls.** AR-vs-original scored against a
  *mismatched* activation: +1.463 gap. Latent-set Jaccard, matched vs.
  mismatched: 0.572 vs 0.006 (99.9× separation). Neither result is close to its
  null.
- **Labels**: 3,329 attempted, **1,771 (53%) validated** against a wrong-label
  null, mean AUC 0.880 among those kept.
- **Judge**: false-positive rate **4.6%**, AUC 0.78–0.81 against its two nulls,
  **0 monotonicity violations** across 2,414 latents judged under both a segment
  and the reconstructed whole.

---

## Limitations

- **200 activations, one model, one layer, one corpus.** One activation per
  conversation and one explanation per activation, so 200 is the number of
  independent samples.
- **The corpus may be in-sample for the SAE.** If so, the SAE's own
  reconstruction (row 1's implicit ceiling) is flattering to the SAE, which
  makes the round trip's showing *harder* to win, not easier. See
  [METHODOLOGY.md](METHODOLOGY.md) §2.
- **Row 3's false-negative rate is not measurable at scale.** The SAE gives free
  ground truth for false positives; nothing gives ground truth for "the
  explanation meant to say this and the judge missed it." A 40-pair hand audit
  of an earlier judge version found it missed 8, over-called 0.
- **Only 45% of F_orig latents can be labelled**, so row 4 treats every
  unlabelled latent as unconveyed. It is a lower bound, not a separate finding
  from row 3.
- **An SAE does not have a latent for everything.** A claim can be true with no
  latent to match it — a limit the NLA paper notes about its own method.
- **Correlation, not causation, and only at n≈190.** The zero in "does FVE
  predict grounding between activations" is "not detectable at this n," not
  proven zero.
