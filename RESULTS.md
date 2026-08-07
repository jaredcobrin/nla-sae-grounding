# Results

**50 Gemma-3-12B-IT layer-32 activations × 5 sampled explanations = 250 pairs**,
on Gemma-generated rollouts (oasst1 + LMSYS prompts, responses from Gemma itself
— the distribution Gemma Scope 2's SAEs were fine-tuned on).

Method: **[METHODOLOGY.md](METHODOLOGY.md)** · Raw artefacts: [`results/`](.) ·
Experiments that failed their own controls: **[INCONCLUSIVE.md](INCONCLUSIVE.md)**

Two SAEs are used. `l0_big` (~120 active latents) for the reconstruction scores
in §1; `l0_small` (~21) everywhere a latent has to be *named*, because labels
generated at `l0_big` do not pass validation. They are separately trained
dictionaries, so results do not automatically transfer between them.

---

## 1. The NLA round trip reconstructs an activation better than the SAE does

| | reconstructed from | SAE | FVE |
|---|---|---|---|
| **A** | the SAE's latents | `l0_big` | 0.587 |
| **B** | **two sentences of English** (the NLA round trip) | none | **0.739** |
| **C** | the SAE's latents, applied to the AR's output | `l0_big` | 0.700 |
| **D** | the SAE's reading of the AR's output | `l0_big` | 0.494 |

**B > A by 0.152**, measured on the corpus the SAE was fine-tuned on. B involves
no SAE, so it is unchanged by that choice; `l0_big` is the stronger variant, so
this is the conservative form of the comparison. An earlier n=10 pass held the
same ordering on FineWeb and WildChat as well.

**C > A by 0.113** — the SAE reconstructs the AR's *output* better than a real
activation, and needs fewer latents to do it (101.3 vs 119.9). **The two sides of
every overlap count below are therefore not read with equal fidelity.**

> Gemma's `rawvar` is 0.0279, so `FVE = 1 − 71.7×(1−cos)` and FVE exaggerates
> small differences: the C > A gap is 0.0016 in cosine. C > A is also measured at
> `l0_big` only, not at the `l0_small` used from §3 onward.

---

## 2. Latent overlap survives the round trip, far above its control

The 250 pairs re-encoded under each SAE — identical vectors, only the dictionary
changes.

| | `l0_small` (~21/activation) | | `l0_big` (~120/activation) | |
|---|---:|---:|---:|---:|
| | **total** | **share** | **total** | **share** |
| **shared** — in the activation *and* the reconstruction | 3,529 | 56.5% | 17,125 | 44.9% |
| **lost** — in the activation, not the reconstruction | 1,441 | 23.1% | 12,850 | 33.7% |
| **made** — in the reconstruction only | 1,280 | 20.5% | 8,202 | 21.5% |

Many latents fire on almost any text, so those counts mean nothing until you know
what two *unrelated* vectors share. Scoring each reconstruction against a
**different** activation:

| Jaccard | `l0_small` | `l0_big` |
|---|---:|---:|
| matched — against its own activation | **0.576** | **0.450** |
| **mismatched control** | 0.009 | 0.026 |
| ratio | **65×** | **17×** |

**This is the most robust number here** — integer set arithmetic on latent IDs,
with no language model anywhere in the measurement.

---

## 3. Latents the round trip keeps are the ones the explanation talks about

3,032 (latent, explanation) pairs — the 250 pairs restricted to latents with a
validated label, since a text cannot be checked against a latent nobody can
describe. Half of all labels fail validation and are discarded; the unnamed half
is **counted in every total but never named**.

| bucket | n | **conveyed by the explanation** |
|---|---:|---:|
| **shared** | 1,840 | **45.9%** |
| **made** | 562 | 35.1% |
| **lost** | 630 | 31.4% |

`shared` at 45.9% is **8.1×** the judge's measured 5.7% false-positive rate. That
judge was selected by a bake-off; the prompt it replaced scored 78.3%.

Compared **per activation and then across the 50 activations** — pooling the
3,032 pairs would count one activation's latents as dozens of independent
observations and overstate confidence by ~2.5× —

| | difference | 95% CI | |
|---|---:|---|---|
| shared vs lost | +11.2 pts | [+2.6, +19.7] | t = 2.56 |
| shared vs made | +12.6 pts | [+2.4, +22.9] | t = 2.42 |
| made vs lost | +1.1 pts | [−11.1, +13.3] | not distinguishable |

`shared` beats both other buckets. `made` and `lost` cannot be told apart.

**This is the main result**, and it is a correlation between an SAE's reading of
an activation and text an independent model wrote about it. It is not explained
here.

*(`shared` labels do score slightly higher than `lost` labels — 0.872 vs 0.856 —
but the gap holds inside every matched label-quality band, +14.0 points weighted,
so label quality is not what produces it.)*

---

## 4. But being mentioned is not what makes a latent survive

The same latents, split both ways:

| | `shared` | `lost` | **total** |
|---|---:|---:|---:|
| **mentioned** | 845 | 198 | **1,043** |
| **not mentioned** | 995 | 432 | **1,427** |
| **total** | **1,840** | **630** | 2,470 |

Down a column, 46% of `shared` latents were mentioned — the figure above. Across a
row, **81%** of mentioned latents are `shared`, against **70%** of unmentioned
ones. Both are correct; only the row reading bears on whether mentioning helps.
Per activation that gap is **+7.5 points, 95% CI [+0.7, +14.2]** — the weakest
result in this file.

**The largest cell is "not mentioned, yet `shared`": 995 latents — 54% of all
`shared` latents.** The AR reconstructed them without the explanation visibly
saying so. In the opposite corner, 198 were mentioned and lost anyway. **No
mechanism for either is established here.**

> **What this means for the tool.** `trust_report.py` marks a latent CONFIRMED
> when it is in the activation *and* in the AR's reconstruction. For 54% of those,
> the explanation did not visibly convey it. **CONFIRMED means the round trip
> preserved it, not that the explanation said it.**

---

## Limitations

- **n = 50 activations**, one model, one layer, one corpus. The 250 pairs are
  50 × 5 sampled explanations, so the effective n is 50.
- **These activations were selected on the outcome metric.** An FVE gate chose
  ones scoring 0.73–0.77, so they are easier than average by construction. Every
  seed tried is logged; the gate has since been removed from the code.
- **~50% label coverage.** The unnamed half may behave differently.
- **An SAE is incomplete.** A claim can be true with no corresponding latent, so
  absence of a latent is weak evidence — a limitation the NLA paper names of its
  own method.
- **Every "kept" and "confirmed" number measures the AR's prior plus the
  explanation, not the explanation alone** (§4). Separating them needs an AR
  trained independently of the AV, which the released checkpoints do not provide.
- **The two sides of the overlap counts are read with unequal fidelity** (§1,
  C > A), so `made` counts are not like-for-like.
- **Nothing here checks whether a latent is *true* of the source text.** Both
  attempts failed their controls — [INCONCLUSIVE.md](INCONCLUSIVE.md).
- **The confabulation phenomenon is not a new finding.** The NLA paper documents
  it. What is new here is checking it against SAE latents.
