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
tiny — **0.0282** — and it is FVE's denominator:

```
FVE = 1 − 2(1−cos)/rawvar   →   1 − 70.9×(1−cos)
```

0.001 of cosine moves FVE by 0.071. The multiplier depends on which activations
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

Activations are sampled from **Gemma Scope's own corpus** — the `tokens` array
inside `examples.safetensors`, 236,783 finished Gemma chat conversations shipped
with the SAE. It is the same corpus the SAE's published feature exemplars index
into: `seq_ids` and `positions` address rows of this exact array, which is how
each latent gets its label in §3.

Earlier runs reproduced Gemma Scope's recipe instead, sampling oasst1 + LMSYS
prompts and generating responses with Gemma. That path still exists
(`--arm rollout`), but it costs ~400 decode steps per conversation — hours per
run — and is not bit-reproducible, since the responses depend on sampling
temperature and model version. Using the shipped corpus makes stage 1 one
forward pass per conversation, and makes the text identical for anyone
re-running.

> **Stated limitation: this corpus may be in-sample for the SAE.** Google
> documents neither where the text came from nor whether the SAE was trained on
> it. If it was, the SAE's own reconstruction score in §1 is flattering to the
> SAE — which makes §1's claim (the NLA round trip beats the SAE) *harder* to
> win, not easier: the SAE is scored on home ground while the NLA is scored away,
> since the AV and AR were trained on WildChat + Ultra-FineWeb. For §2 and §3 it
> is neutral, because those compare buckets and matched-vs-null *within* one
> corpus, so a corpus-level effect moves the measurement and its null together.
> What it cannot support is any claim about how Gemma Scope SAEs reconstruct
> activations **in general**. No such claim is made here.
>
> The related worry — that a label derived from Gemma Scope's corpus might not
> describe how a latent behaves in ours — was checked back when the two corpora
> were different, and came back negative. Of the 1,142 latents that fired across
> an earlier run's activations, **none** was absent from Gemma Scope's corpus and
> **none** fell in its rarest 10%; the median sat at the **91st percentile** of
> all 16,384 latents by firing frequency. The latents this experiment touches are
> the well-characterised ones. Drawing both sides from one corpus removes the
> question rather than answering it.

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

### How a label is scored

A label is a hypothesis, so it is tested like one — **as a 32-question quiz**:

- **16 positives** — text snippets at positions where the latent *does* fire,
  drawn from ranks 120–300 of its activation strengths
- **16 negatives** — snippets from uniformly random positions, where it almost
  certainly does not (at ~21 active latents out of 16,384, a random position has
  a ~0.13% chance of firing this one)
- shuffled together; for each, the scorer sees **only the label and the snippet**
  and answers whether that snippet is one the latent fires on

The score is `logP(Yes) − logP(No)`, and the label's grade is the **AUC** over the
32 items: can it separate firing positions from non-firing ones? 0.5 is blind, 1.0
is perfect.

*Why 32 and not 8: an 8-item quiz quantises AUC into 9 possible values. At n=24
the measured signal swung from +0.122 to +0.008 between two samples of latents —
noise big enough to have produced either "this works" or "this is broken".*

Three candidate labels are generated per latent, the best is picked on a
**separate** band (ranks 40–120, 6+6 items), and only then is the winner scored on
120–300. The bands are disjoint, so the reported number never sees the data that
chose the label.

### The first version measured nothing and reported 33% reliable

The control: score each label against a **different latent's** quiz, where the
right answer is always "no".

```
matched   (own label)        0.604
shuffled  (a WRONG label)    0.557    <- should be ~0.50
```

A deliberately wrong label scored almost as well as the right one. Causes: the
negatives were drawn from other latents' *top* exemplars while positives came
from weak ranks, so negatives often looked **more** latent-like than positives
(switching to random negatives alone moved the gap +0.047 → +0.078); argmax
Yes/No threw away the signal; and the SAE was too dense.

Every latent is now also scored with **2 wrong labels**, and the pass threshold is
the 95th percentile of that pooled null — a measured 5% false-positive rate rather
than a number chosen by feel.

```
attempted     2,242      mean AUC 0.743   <- includes the half that get rejected
                         wrong-label null 0.498
                         threshold        0.756
validated     1,115 (50%)   mean AUC 0.876
```

**0.743 is not the quality of the labels in use.** Kept labels average 0.876.
They sit there rather than 0.95+ because the test band is harder than what the
generator saw, the scorer is Gemma-3-12B not a frontier model, and some latents
are genuinely polysemantic.

**"Validated" means "beats a wrong label at a 5% false-positive rate", not
"correct"** — ~40% of kept labels are predictive but vague about *what* they
detect. Prompt engineering alone never fixed any of this (0.596 → 0.609).

---

## 4. Judging whether an explanation covers a latent

### What the matcher is shown

One latent, one explanation, one question. The prompt gives the model the AV's
explanation (as "the DESCRIBER's summary") and the latent's validated label (as
"what the DETECTOR responds to"), and asks whether the summary covers that thing.
It answers with one word: `CLEARLY` / `PROBABLY` / `UNCLEAR` / `NO`.

It is **never told whether the latent was actually active** — that would be true
for real pairs and false for the controls, and would bias exactly the pairs that
measure the error rate. Both conditions are worded identically.

Each pair is judged **7 times**: once matched, plus **3 unrelated explanations**
and **3 latents that never fired**.

```
matched     this latent       vs its OWN explanation
null_expl   this latent       vs 3 unrelated explanations   -> catches a generic latent
null_feat   this explanation  vs 3 latents that never fired -> catches a broad explanation
```

**Two controls, because there are two ways to fail**, and one control cannot tell
them apart. `null_feat` also supplies clean ground truth: those latents provably
did not fire, so every "covered" there is an error — that *is* the false-positive
rate. Verdicts are three-way: if either null rate exceeds 0.5 the answer is
`UNKNOWN`, not "absent".

### The first prompt said yes to almost everything

It asked whether the explanation "plausibly" contained the latent, as a binary
Yes/No — and answered YES to **411 of 476 pairs**, including **78% of latents that
provably did not fire**.

Three variants, run on identical pairs:

| variant | false-positive rate | AUC |
|---|---:|---:|
| A — plain Yes/No | **0.783** | 0.744 |
| **B — graded, strict** (in use) | **0.075** | 0.767 |
| C — ranking (diagnostic only) | — | 0.707 |

**AUC barely moved while the false-positive rate moved tenfold.** The model could
always rank real above fake — it just would not say no. **Calibration, not
capability**, which is why rewording fixed it and a bigger model would not have.
Four changes did it: drop "plausibly"; state the base rate in the prompt (one or
two sentences against ~20 latents, so `NO` is the ordinary answer); give
uncertainty its own option; and name the observed failure modes so they can be
banned — same broad topic, could plausibly contain it, grammatical patterns found
in all writing.

```
false-positive rate   6.7%    (the prompt it replaced: 78.3%)
matcher AUC           0.807   vs unrelated explanations
                      0.836   vs latents that never fired
self-consistency     89.2%    across 5 explanations of one activation
```

---

## 5. Statistics

- **Every rate has its own null**, from re-running the procedure on mismatched data.
- **Only gaps are quoted where the level is not interpretable** — a permissive
  judge inflates both arms; the difference survives, the level does not.
- **One activation per conversation.** Two activations sampled from the same
  Gemma response share nearly all their context; a run that took 10 apiece
  produced pairs one token apart. Sampling 50 rows from such a corpus gave 50
  activations spread over 30 conversations, and every interval was computed as
  if all 50 were independent. `load_vectors` now takes at most one row per
  `doc_id`, and `SUMMARY.md` prints the conversation count so this cannot hide.
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
