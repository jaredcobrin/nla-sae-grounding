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

**All numbers below: 50 activations × 5 sampled explanations = 250 pairs**, on
Gemma-3-12B-IT layer 32, using text Gemma itself generated (the distribution the
SAE was fine-tuned on).

Method: **[METHODOLOGY.md](METHODOLOGY.md)** · Raw data: [`results/`](.) ·
Experiments that failed their own controls: **[INCONCLUSIVE.md](INCONCLUSIVE.md)**

> Two SAEs are used. A denser one (`l0_big`, ~120 active latents) for §1, where
> the question is how faithfully something can be rebuilt. A sparser one
> (`l0_small`, ~21) from §2 onward, wherever a latent has to be *named* — labels
> generated at `l0_big` fail validation. They are separately trained, so a result
> from one does not automatically hold for the other.

---

## 1. Two sentences of English preserve an activation better than the SAE does

**FVE** measures how close a rebuild is to the original — 1.0 is perfect.

| | what is doing the rebuilding | FVE |
|---|---|---|
| **A** | the SAE: break the activation into latents, reassemble | 0.587 |
| **B** | **the NLA: activation → two sentences → activation** | **0.739** |
| **C** | the SAE, but rebuilding the *AR's output* instead | 0.700 |
| **D** | both lossy steps chained together | 0.494 |

**B beats A by 0.152.** An activation survives being written into English and
rebuilt better than it survives a purpose-built 16,384-latent decomposition — and
this was measured on the SAE's home turf, with the *stronger* of the two SAEs. An
earlier smaller run found the same ordering on two other text corpora.

**C also beats A, by 0.113**, and this is a caveat rather than a result: the SAE
reads the AR's output *more accurately* than it reads a real activation, using
fewer latents to do it (101 vs 120). So when §2 compares "what's in the original"
against "what's in the rebuild", **the instrument is sharper on one side than the
other.**

> Gemma's activations are unusually similar to each other, which makes FVE
> exaggerate small differences: `FVE = 1 − 71.7×(1−cos)`, so the C > A gap is only
> 0.0016 in cosine terms. C > A was also only measured on the denser SAE.

---

## 2. Most latents survive the round trip — and that is not chance

The same 250 pairs, re-encoded under each SAE:

| | `l0_small` (~21/activation) | | `l0_big` (~120/activation) | |
|---|---:|---:|---:|---:|
| | **count** | **share** | **count** | **share** |
| **shared** | 3,529 | 56.5% | 17,125 | 44.9% |
| **lost** | 1,441 | 23.1% | 12,850 | 33.7% |
| **made** | 1,280 | 20.5% | 8,202 | 21.5% |

On its own, "56.5% shared" proves nothing — **some latents fire on almost any
text** (punctuation, common grammar), so any two activations overlap a bit for
free. The test is to run the identical comparison against a **completely
unrelated** activation and see what that scores.

**Jaccard** = how much two sets share, divided by everything they cover between
them. 0 means nothing in common, 1 means identical.

| Jaccard | `l0_small` | `l0_big` |
|---|---:|---:|
| rebuild vs **its own** activation | **0.576** | **0.450** |
| rebuild vs an **unrelated** activation | 0.009 | 0.026 |
| ratio | **65×** | **17×** |

Unrelated activations share essentially nothing. **This is the most trustworthy
number in the project**: it is counting matching ID numbers, with no language
model anywhere in the measurement and nothing to calibrate.

---

## 3. The latents that survive are the ones the explanation talks about

For each latent, a judge is shown the AV's explanation and the latent's label and
asked whether the explanation covers it.

This only works for latents we can *describe*, so it runs on the 3,032
(latent, explanation) pairs where the label passed validation. **Half of all
labels fail that validation and are thrown away** — those latents are still
counted in every total, just never named.

| | latents | **mentioned in the explanation** |
|---|---:|---:|
| **shared** | 1,840 | **45.9%** |
| **made** | 562 | 35.1% |
| **lost** | 630 | 31.4% |

The judge itself makes mistakes 5.7% of the time (measured against latents that
provably were *not* in the activation). `shared` at 45.9% is **8.1× that error
floor**, so it is not the judge's noise. The prompt this judge replaced scored
78.3% — it said yes to almost anything.

**Is the gap between buckets real?** These 3,032 pairs come from only 50
activations, so treating them as 3,032 independent observations would overstate
confidence by about 2.5×. Computing the difference *within* each activation and
then comparing across the 50:

| | difference | 95% confidence interval | |
|---|---:|---|---|
| shared vs lost | +11.2 points | [+2.6, +19.7] | real |
| shared vs made | +12.6 points | [+2.4, +22.9] | real |
| made vs lost | +1.1 points | [−11.1, +13.3] | **too close to call** |

**This is the main result.** What the AV writes about genuinely tracks what the
SAE finds inside the activation — it is not free-associating. `made` and `lost`
cannot be separated from each other.

*(`shared` latents do have slightly better labels than `lost` ones — 0.872 vs
0.856 — but the gap survives inside every matched label-quality band, so label
quality is not what is producing it.)*

---

## 4. But being mentioned is not what makes a latent survive

Take every latent that was really in the activation, and sort it two ways at
once — was it mentioned, and did it survive?

| | `shared` | `lost` | **total** |
|---|---:|---:|---:|
| **mentioned** | 845 | 198 | **1,043** |
| **not mentioned** | 995 | 432 | **1,427** |
| **total** | **1,840** | **630** | 2,470 |

Read this table down a column and you get §3's number: of the latents that
survived, 46% were mentioned. Read it **across a row** and you get a different
question — of the latents that were *mentioned*, 81% survived, against 70% of
unmentioned ones. Only the row version says anything about whether mentioning
helps, and per activation that gap is **+7.5 points, 95% CI [+0.7, +14.2]** — the
weakest result in this file.

**The biggest cell in that table is "never mentioned, survived anyway": 995
latents, 54% of everything that survived.** The AR only ever sees the two
sentences, so it is producing those latents without the text visibly saying so.
198 latents went the other way — mentioned, and lost regardless.

**Why that happens is not established here.**

> **What this means for the tool.** `trust_report.py` marks a latent CONFIRMED
> when it is in the activation *and* in the AR's rebuild. For 54% of those, the
> explanation never visibly mentioned it. **CONFIRMED means the round trip
> preserved it — not that the explanation said it.**

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
- **Nothing here separates "the AR was told" from "the AR guessed well"** (§4).
  Doing so needs an AR trained independently of the AV, which the released
  checkpoints do not provide.
- **The SAE reads the rebuild more clearly than the original** (§1, C > A), so
  `made` counts are not a like-for-like comparison.
- **Nothing here checks whether a latent is *true* of the source text.** Both
  attempts failed their own controls — [INCONCLUSIVE.md](INCONCLUSIVE.md).
- **The confabulation finding is not new.** The NLA paper documents it. What is
  new here is checking it against SAE latents.
