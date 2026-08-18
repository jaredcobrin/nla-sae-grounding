# Methodology

Steps only, in service of one question: **does the AV's final paragraph, which
carries more FVE, also carry more of what is genuinely in the activation?**
Design-decision history and dead ends are not here — see the side-material
archive if that is what you're looking for.

---

## 1. Why an SAE, not FVE alone

FVE measures whether the AR can rebuild the activation from the AV's text. It
does not measure whether the text is true, because the AR and AV are trained
together on the same rollouts and can settle on any code both sides agree on. An
**SAE** — trained on Gemma independently of the NLA, never on this pipeline's
output — reads the activation directly and gives a second, independent readout:
a set of active **latents**, plus a validated label for what each one detects.

## 2. Setup

- Model: **Gemma-3-12B-IT, layer 32**. AV and AR are the released NLA checkpoints
  for this layer, frozen.
- Corpus: **200 activations, one per conversation**, sampled from Gemma Scope's
  own shipped corpus (`examples.safetensors`) — the same corpus the SAE's feature
  exemplars index into, so a latent's label and its firing behaviour here draw
  from the same distribution.
- SAE: **Gemma Scope 2**, two widths from the same saved vectors — `l0_big`
  (~120 active latents, used for reconstruction fidelity) and `l0_small` (~21,
  used wherever a latent must be named or matched to text).

**Corpus caveat.** Google does not document whether this corpus was also used to
train the SAE. If it was, the SAE's own reconstruction (§ Results, row 1's
implicit ceiling) is flattering to the SAE, which makes the round trip's showing
against it *harder* to win, not easier.

## 3. The paragraph split

The AV writes to a stable three-part shape: what kind of document this is, what
it is about, and what the final token is doing. One explanation is generated per
activation, then cut **once** into three variants — the comparison is paired, so
none of the difference between them can come from resampling the AV:

| variant | contents |
|---|---|
| `full` | the explanation as written |
| `no_final` | parts 1–2 |
| `final_only` | part 3 — what the final token is doing |

The cut is anchored on the phrase "final token," not on paragraph count: on this
run it succeeded **200/200** — the phrase appears exactly once per explanation,
never in the first paragraph.

## 4. What each activation contributes: shared / lost / made

Per activation, the SAE encodes both the **original** activation and the **AR's
rebuilt** activation, giving two latent sets:

- **F_orig** — latents active in the original (= `shared` + `lost`)
- **shared** — in F_orig, and still active after the round trip
- **lost** — in F_orig, gone after the round trip
- **made** — active after the round trip, not in F_orig

F_orig depends only on the original activation, so it is identical across all
three paragraph variants for a given activation; shared/lost/made are recomputed
per variant, since the round trip changes with the text.

## 5. Labelling latents

Every latent that fires is auto-labelled: three candidate labels are generated,
the best is picked on a held-out band of exemplars, and the winner is graded on a
**32-item quiz** (16 positions where it fires, 16 where it almost certainly does
not) as an AUC. A label passes only if it beats the 95th percentile of a
**wrong-label null** — the same quiz, scored against a label that is definitely
wrong. 3,329 labels attempted, **1,771 (53%) validated**, mean AUC 0.880 among
those kept.

## 6. Judging whether the text conveys a latent

One latent, one segment of text, one question to an LLM judge: does this text
convey what the latent detects? Graded `CLEARLY`/`PROBABLY`/`UNCLEAR`/`NO`, never
told whether the latent actually fired. The judge sees `no_final` and
`final_only` separately; `full`'s coverage is the union of the two, which makes
it monotonic by construction (a whole cannot cover less than one of its parts).

## 7. Nulls and controls

| control | what it catches |
|---|---|
| **wrong-label null** (§5) | a label that scores well by being generic, not accurate |
| **null_feat** — this explanation vs. 3 latents that never fired | a judge too willing to say "covered" |
| **null_expl** — this latent vs. 3 unrelated explanations | a latent generic enough to match anything |
| **mismatched activation control** (§ reconstruction) | the AR's rebuild scored against the wrong original |
| **mismatched conversation control** (near-miss sweep) | a latent match that is generic to the topic, not the token |

Null partners are always drawn from the **same paragraph variant** as the
matched pair, since variants differ in length and length alone shifts a judge's
yes-rate.

## 8. One activation per conversation

Two activations from the same Gemma response share nearly all their context and
are one cluster, not two independent samples. Sampling takes at most one
position per conversation; `SUMMARY.md` prints the conversation count against
the activation count so a clustered sample cannot pass silently.
