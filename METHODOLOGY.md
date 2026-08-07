# Methodology

Three times in this project a measurement produced confident, plausible, **wrong**
numbers, and each was caught only by re-running the identical procedure on
deliberately mismatched data. §3 and §4 are those cases.

---

## 1. Why the paper's own metric cannot answer this

The NLA paper measures **FVE** — how close the AR's rebuild is to the original.
A high FVE means the AR rebuilt it well from the AV's text. It does **not** mean
the AV said anything true: during RL both models train on the same rollouts
(`docs/design.md:97` upstream), so the AR is fitted to the AV's output rather than
judging it. The fixed point is any mutually consistent code. Hence a third reader
with no stake in the pair — an SAE, which reads the activation directly and never
saw the NLA.

**Gemma metric trap.** Gemma's activations sit at mean pairwise cosine **0.967**
(Qwen: 0.30) because dimension 2339 carries ~70,783 of the mean. So `rawvar` is
tiny — **0.0279** — and it is FVE's denominator:

```
FVE = 1 − 2(1−cos)/rawvar   →   1 − 71.7×(1−cos)
```

0.001 of cosine moves FVE by 0.072. The multiplier depends on which activations
were sampled (the n=10 run: 65.0×), so it is not a constant of the model. Every
FVE here is reported with its cosine.

> **"Latent", not "feature."** A latent is a dimension of the SAE; a feature is
> what it might mean, which is a claim. The code and JSON keys still say
> `feature` — renaming would invalidate every shipped artefact.

---

## 2. Corpus and SAE choice

**The corpus is Gemma's own writing**, matching how Gemma Scope 2's SAEs were
fine-tuned. Not cosmetic: an earlier pass on FineWeb, out-of-distribution for the
SAE, measured a **7-point** effect where Gemma rollouts gave **25**.

**Two SAEs, each the conservative choice for its job:**

| | `l0_big` (~120 latents) | `l0_small` (~21) |
|---|---|---|
| correct label vs wrong label | **+0.008 AUC** — indistinguishable | **+0.092 AUC** |
| used for | reconstruction fidelity | anything about *meaning* |

`l0_big` is the **stronger** SAE, so "the NLA beats the SAE" is harder to claim
against it. `l0_small` is required wherever a latent must be named, since at ~120
active latents a correct label scores the same as a wrong one. Both are re-encoded
from the **same saved vectors**, so neither was picked for giving a nicer number.

---

## 3. Labelling latents

Each generated label is scored on data the generator never saw.

**The first version measured nothing and reported 33% reliable.** The control —
score each label against a *different* latent's data, where the answer is always
"no":

```
matched   (own label)        0.604
shuffled  (a WRONG label)    0.557    <- should be ~0.50
```

A deliberately wrong label scored almost as well as the right one. Causes: the
negatives were drawn from other latents' *top* exemplars while positives came from
weak ranks, so negatives looked more latent-like; argmax Yes/No threw away the
signal; and the SAE was too dense.

**Now:** generate 3 candidates, pick the best on ranks 40–120, score it on ranks
120–300 — *disjoint*, so the reported number never sees the data that chose the
label. Every latent is also scored with a **wrong** label; the threshold is the
95th percentile of that null, i.e. a measured 5% false-positive rate.

```
attempted     1,624      mean AUC 0.742   <- includes the half that get rejected
                         wrong-label null 0.499
                         threshold        0.756
validated       816 (50%)  mean AUC 0.873
```

**0.742 is not the quality of the labels in use.** Kept labels average 0.873.
They sit there rather than 0.95+ because the test band is harder than what the
generator saw, the scorer is Gemma-3-12B not a frontier model, and some latents
are genuinely polysemantic.

**"Validated" means "beats a wrong label at a 5% false-positive rate", not
"correct"** — ~40% of kept labels are predictive but vague about *what* they
detect. Prompt engineering alone never fixed any of this (0.596 → 0.609).

---

## 4. Judging whether an explanation covers a latent

**The first prompt said yes to almost everything** — asked whether the explanation
"plausibly" contained the latent, and answered YES to 411 of 476 pairs, including
**78% of latents that provably did not fire**.

Three variants on identical pairs:

| variant | false-positive rate | AUC |
|---|---:|---:|
| A — plain Yes/No | **0.783** | 0.744 |
| **B — graded, strict** (in use) | **0.075** | 0.767 |
| C — ranking (diagnostic only) | — | 0.707 |

**AUC barely moved while FPR moved tenfold** — the model could always rank real
above fake, it just would not say no. **Calibration, not capability**, which is
why rewording fixed it and a bigger model would not have. The fixes: drop
"plausibly", state the base rate (one or two sentences against ~20 latents, so
most are genuinely not covered), give uncertainty its own answer, and name the
observed failure modes so they can be banned. The prompt never states that the
latent was active — that is false for the controls and would bias exactly the
pairs measuring the false-positive rate.

**Two controls, because there are two ways to fail:**

```
null_expl   this latent       vs unrelated explanations   -> catches a generic latent
null_feat   this explanation  vs latents that never fired -> catches a broad explanation
```

One control cannot tell those apart. `null_feat` also gives clean ground truth:
those latents provably did not fire, so every "covered" is an error — that *is*
the false-positive rate. Verdicts are three-way; if either null is high the answer
is `UNKNOWN`, not "absent".

```
false-positive rate   5.7%    (the prompt it replaced: 78.3%)
matcher AUC           0.807   vs unrelated explanations
                      0.836   vs latents that never fired
self-consistency     89.2%    across 5 explanations of one activation
```

---

## 5. Statistics

- **Every rate has its own null**, from re-running the procedure on mismatched data.
- **Only gaps are quoted where the level is not interpretable** — a permissive
  judge inflates both arms; the difference survives, the level does not.
- **The unit is the activation, not the pair.** 3,032 pairs come from **50
  activations**, so pooling inflates confidence ~2.5×: shared vs lost is `z = 6.4`
  pooled but **`t = 2.56`** per activation, which is what is reported. For the same
  reason no test is quoted on §2's two SAE rows — same pairs, two dictionaries.
- **Selection on the outcome metric is logged.** The FVE gate chose activations
  scoring 0.73–0.77, easier than average by construction. Every seed is recorded,
  and the gate has since been removed.

---

## 6. Tried and did not work

- **Matching short claims to latents.** At 3-word fragments the matcher had only
  surface form: it matched *"Reflective, relatable tone"* to *"Adjectives
  modifying terms related to AI systems"* **in an unrelated activation**, because
  "relatable" is an adjective. Mismatched control **54%** — a coin flip.
- **Matching at category level.** `topic_domain` appears in 99% of activations,
  and the category-level control between different activations scores **0.591**
  against 0.013–0.029 at latent level. Categories are for reporting, not testing.
- **A per-label confidence score.** A monotonicity bug rated a latent at **AUC
  0.172 — below chance** — as 98% likely real. Deleted.
- **Regex heuristics over label text.** Used three times, wrong three times: one
  classifier called *"noun phrases denoting superhero characters"* grammatical
  because the label contains "noun".
- **Blind bucket descriptions** (`src/describe_buckets.py`). Works and is legible,
  but qualitative and read by eye, so **not reported in `RESULTS.md`**. With 2–3
  labelled latents it over-reaches ~10% of the time.
