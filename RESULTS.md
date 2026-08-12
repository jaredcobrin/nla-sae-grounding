# Results

## The setup, in one paragraph

An **activation** is a language model's internal state at one word — 3,840
numbers, unreadable directly. The NLA is two models: the **AV** looks at an
activation and writes two sentences describing it; the **AR** reads only those
two sentences and tries to rebuild the original activation. The worry — which the
NLA paper raises itself — is that the AV, being a full language model, might
invent plausible-sounding detail. You cannot catch that by checking AV against
AR, because they were trained together and can agree on a fiction. So this uses a
**sparse autoencoder (SAE)** as an independent witness: it breaks any activation
into a list of active **latents**, and it never saw the NLA.

Three groups of latents matter throughout:

| | |
|---|---|
| **shared** | in the original activation **and** in the AR's rebuild — survived the round trip |
| **lost** | in the original, gone from the rebuild |
| **made** | in the rebuild only — the AR produced it from nowhere visible |

**All numbers below: 50 activations x 5 sampled explanations = 250 pairs**, on
Gemma-3-12B-IT layer 32, on Gemma's own chat writing (the distribution the SAE
was fine-tuned on).

> **These are superseded numbers.** They come from a 50-activation run, which
> the power calculation says is roughly half the sample needed to settle §3b.
> A 200-conversation run regenerates every figure here from
> [`results/SUMMARY.md`](results/SUMMARY.md); that file, never this one, is
> where numbers should be quoted from.

Method: **[METHODOLOGY.md](METHODOLOGY.md)** · Raw data: [`results/`](.) ·
Experiments that failed their own controls: **[INCONCLUSIVE.md](INCONCLUSIVE.md)**

> Two SAEs are used. A denser one (`l0_big`, ~120 active latents) for §1, where
> the question is how faithfully something can be rebuilt. A sparser one
> (`l0_small`, ~21) from §2 onward, wherever a latent has to be *named* — labels
> generated at `l0_big` fail validation. They are separately trained, so a result
> from one does not automatically hold for the other.

---

## 1. What the AR produces is not shaped like a real activation

**FVE** measures how close a rebuild is to the original — 1.0 is perfect.

| | what is being rebuilt, by what | FVE |
|---|---|---|
| **A** | a **real activation**, by the SAE | 0.582 |
| **C** | the **AR's output**, by the same SAE | **0.711** |
| **B** | a real activation, by the NLA round trip | 0.687 |
| **D** | both lossy steps chained together | 0.455 |

**C beats A by +0.129, and that is the finding here.** Hand the SAE something the
AR produced and it decomposes it *better* than it decomposes a genuine
activation — using **fewer latents** to do it, 98.9 against 119.7. The AR does not
emit a typical point in activation space. It emits something cleaner, sitting
more squarely inside the SAE's dictionary than the real thing does.

That is a claim about **what the AR emits**, which is why it is the more
interesting of the two comparisons: it characterises the object rather than
ranking two rebuilders. It also has a direct consequence for §2 — when we compare
"what is in the original" against "what is in the rebuild", **the instrument is
sharper on one side than the other**, and the asymmetry favours finding latents
in the rebuild.

**B beats A by +0.106** — an activation survives being written into English and
read back better than it survives a purpose-built 16,384-latent decomposition,
measured on the SAE's home turf with the *stronger* of the two SAEs. Treat this
as the weaker of the two claims: it ranks two systems rather than characterising
either, and per [METHODOLOGY §2](METHODOLOGY.md) the corpus may be in-sample for
the SAE, which flatters row A and makes the comparison conservative rather than
generous.

> **Both gaps are small in cosine terms, and the mean is not the typical case.**
> Gemma's activations are so alike that `rawvar` ≈ 0.028, making
> `FVE = 1 − 71×(1−cos)`; the C − A gap is about 0.0018 of cosine. In the other
> direction the same multiplier means a handful of bad reconstructions dominate
> the mean: row B's **median is +0.774** against a mean of +0.687, with the
> published Gemma figure at 0.768. The typical activation reconstructs at the
> published level and 13 of 250 pairs drag the average down. `SUMMARY.md` prints
> the full distribution. C > A was measured only on the denser SAE.

---

## 2. Most latents survive the round trip — and that is not chance

The same 250 pairs, re-encoded under each SAE:

| | `l0_small` (~21/activation) | | `l0_big` (~120/activation) | |
|---|---:|---:|---:|---:|
| | **count** | **share** | **count** | **share** |
| **shared** | 3,480 | 53.8% | 17,042 | 45.3% |
| **lost** | 1,675 | 25.9% | 12,888 | 34.3% |
| **made** | 1,310 | 20.3% | 7,678 | 20.4% |

On its own, "53.8% shared" proves nothing — **some latents fire on almost any
text** (punctuation, common grammar), so any two activations overlap a bit for
free. The test is to run the identical comparison against a **completely
unrelated** activation and see what that scores.

**Jaccard** = how much two sets share, divided by everything they cover between
them. 0 means nothing in common, 1 means identical.

| Jaccard | `l0_small` | `l0_big` |
|---|---:|---:|
| rebuild vs **its own** activation | **0.540** | **0.451** |
| rebuild vs an **unrelated** activation | 0.013 | 0.030 |
| ratio | **43×** | **15×** |

Unrelated activations share essentially nothing. **This is the most trustworthy
number in the project**: it is counting matching ID numbers, with no language
model anywhere in the measurement and nothing to calibrate.

---

## 3. Does the explanation talk about the latents that survive?

**This section is two separate measurements, with two separate nulls.** Keeping
them apart matters, because they can fail independently.

### 3a. Bucketing — which latents survived

Pure set arithmetic on latent IDs, exactly as in §2. No text is read, no judge is
involved, nothing can be miscalibrated.

| bucket | latents | |
|---|---:|---|
| **shared** | 1,682 | fires in the original **and** the rebuild |
| **lost** | 663 | fires in the original only |
| **made** | 530 | fires in the rebuild only |

**Its null is §2's mismatched-activation control** — compare one activation's
latents against a *different* activation's rebuild. Without it the overlap could
be pure base rate, since common latents fire on almost everything.

### 3b. Matching — did the explanation mention it

Now a judge reads the AV's explanation and the latent's label and asks whether
the explanation covers it. This needs a latent we can *describe*, so it runs on
the 2,875 (latent, explanation) pairs whose label passed validation. **Half of
all labels fail validation and are discarded** — those latents still count in
every total above, they just cannot be named.

| bucket | mentioned in the explanation | chance (`null_expl`) |
|---|---:|---:|
| **shared** | **41.9%** | 8.4% |
| **made** | 34.5% | 7.2% |
| **lost** | 31.4% | 8.5% |

**Its nulls are two, because a judge can fail in two directions.** `null_feat` —
judge the real explanation against a latent that never fired — measures whether
it says yes to anything: **6.7%**, so `shared` is 6.3× that floor. The prompt
this judge replaced scored **78.3%** on the same test. `null_expl` — judge a real
latent against an *unrelated* activation's explanation — measures whether the
latent is so generic any text matches it. Both are broken out per bucket above,
and they come back **flat** (8.4 / 8.5 / 7.2%), so the differences between
buckets are not chance rates in disguise.

### Is the difference between buckets real?

The 2,875 pairs come from only **50 activations**, so treating them as 2,875
independent observations would overstate confidence roughly 2.5×. Computing each
difference *within* an activation and then comparing across activations:

| | difference | 95% confidence interval | |
|---|---:|---|---|
| shared vs made | +10.1 points | [+1.2, +19.0] | holds |
| shared vs lost | +8.5 points | [−0.6, +17.6] | **inconclusive** |
| made vs lost | +0.1 points | [−10.6, +10.8] | **too close to call** |

**At n = 50 the headline comparison does not reach significance.** `shared` beats
`made`, but the shared-vs-lost interval crosses zero. This is a power problem,
not a null result: the power calculation puts the minimum at ~112 independent
activations, and this run has 50. A 200-conversation run is what decides it, and
until then this section states a direction, not a finding.

*(One confound was checked and does not explain the ordering: `shared` latents do
have sharper labels than `lost` ones, 0.871 vs 0.860, and conveyance genuinely
rises with label quality — +15.7 points from the weakest validated labels to the
strongest. But holding label quality fixed, the gap moves only **1.6 points**
across every threshold, so labelling is not what produces it. `SUMMARY.md` §4
prints this every run.)*

> **What this means for the tool.** The tool marks a latent `SHARED` when it is in
> the activation *and* in the AR's rebuild. But **58% of `shared` latents were
> never visibly mentioned in the explanation** — the AR produced them from
> context. `SHARED` means the round trip preserved it, not that the explanation
> said it.

---

## Limitations

- **50 activations, one model, one layer, one corpus.** The 250 pairs are 50 × 5
  sampled explanations, so the real sample size is 50.
- **These activations were picked using the metric being reported.** A gate
  selected ones scoring FVE 0.73–0.77, making them easier than average by
  construction. Every seed tried is logged, and the gate has since been removed
  from the code.
- **Only half the latents can be named**, and the unnamed half may behave
  differently.
- **An SAE does not have a latent for everything.** A claim can be true with no
  latent to match it, so a missing latent is weak evidence of absence — a limit
  the NLA paper notes about its own method.
- **Nothing here separates "the AR was told" from "the AR guessed well".**
  Doing so needs an AR trained independently of the AV, which the released
  checkpoints do not provide.
- **The SAE reads the rebuild more clearly than the original** (§1, C > A), so
  `made` counts are not a like-for-like comparison.
- **Nothing here checks whether a latent is *true* of the source text.** Both
  attempts failed their own controls — [INCONCLUSIVE.md](INCONCLUSIVE.md).
- **The confabulation finding is not new.** The NLA paper documents it. What is
  new here is checking it against SAE latents.
