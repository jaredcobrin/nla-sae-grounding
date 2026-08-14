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
attempted     3,329      mean AUC 0.751   <- includes the half that get rejected
                         wrong-label null 0.485
                         threshold        0.756
validated     1,771  (53%)  mean AUC 0.880
```

**0.751 is not the quality of the labels in use.** Kept labels average 0.880.
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
| plain Yes/No | **0.783** | 0.744 |
| graded, strict | **0.075** | 0.767 |
| ranking (diagnostic only) | — | 0.707 |

**AUC barely moved while the false-positive rate moved tenfold.** The model could
always rank real above fake — it just would not say no. **Calibration, not
capability**, which is why rewording fixed it and a bigger model would not have.

### The graded prompt was not monotonic in the explanation

`full` is exactly `no_final` + `final_only` — the paragraph split is a cut, not a
rewrite — so anything a part covers, the whole must cover. Judged directly, it
did not:

```
latents judged under both full and final_only     2,047
covered under final_only, NOT under full            435   (21.3%)
covered under full, NOT under final_only            128
```

Two in five of `final_only`'s hits were contradicted by a text containing it
verbatim. Holding the latent, its label, its bucket and its activation fixed and
changing only which text the judge read moved the answer by **+15 points**, in
every bucket alike (shared +15.3, made +16.4, lost +15.8), so it is a property of
the text length rather than of the latents.

The cause is the base-rate instruction the fix above installed. It told the judge
the summary is "one or two sentences" — **true of 3% of real explanations**, which
run to a median of three sentences over three paragraphs — and that most latents
are therefore not covered. That makes the judgement relative to how much text is
on screen: more text, each latent is a smaller share of it, same latent flips to
absent.

### What replaced it

Three prompts were measured on identical pairs, with the null pool stratified
(below). Removing the false length claim and nothing else was best on every axis
except monotonicity; deleting the base rate entirely made the judge answer
"covered" for ~82% of everything, so its own nulls fired and the gate discarded
46–71 points of it. **The base rate is load-bearing; the length claim was the
defect.**

Monotonicity is not fixable by wording — all three prompts spanned a wide range
of strictness and none came near zero. It is fixed structurally instead:

**The judge never sees a whole explanation.** It judges the two segments —
`no_final` and `final_only` — and `full` is reconstructed as their union. A union
cannot be smaller than a part, so coverage is monotonic by construction:
**0 violations in 2,414 latents judged under both.**

Costs, both reported rather than hidden:

- **The union compounds false positives.** `full` inherits both segments' errors,
  so its FPR is higher than either alone (7.0% against 1.6% and 5.4%). Corrected
  against its own floor, `full` still gains: 43.0% raw, 40.3% corrected.
- **The post-gate verdict is not quite monotonic.** `full`'s null rates are the
  union of its segments', so the two-null gate fires on it more often — 33 of
  2,414 latents (1.4%) are `present` for a segment but `unknown` for `full`.
  Coverage is exact; the verdict after gating inherits the compounded null.
- A latent conveyed only by the **combination** of two segments is missed. The
  union is a lower bound on containment.

### Nulls are drawn from the same segment

A null must differ from the matched arm in exactly one respect — that the latent
does not belong to it. Drawing `null_expl` partners from a pool containing all
variants broke that, because the variants differ in length and the judge's
yes-rate depends on length. Measured under the old design, `null_feat` was 5.0%
for `no_final`, 5.4% for `full` and 11.5% for `final_only`: a mixed pool inflates
the stingy variants' floor with text from the generous one and deflates the
generous one's. Partners now come from the same variant.

```
false-positive rate         4.6%     (the prompt it replaced: 78.3%)
matcher AUC                 0.783    vs unrelated explanations
                            0.808    vs latents that never fired
monotonicity violations     0.0%     coverage; 1.4% after the gate
FPR spread across variants  0.037    (was 0.089)
```

**Not measurable at scale: the false-negative rate.** The SAE gives free ground
truth for false positives — a latent either fired or it did not — but nothing
says an explanation *did* mean to mention something. A 40-pair hand audit of an
earlier version found the judge missed 8 and over-called 0.

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

---

## 7. Two harder controls

Both reuse the pipeline exactly as it already stands. Neither introduces a new
metric: every existing number — FVE mean and median, the A/B/C/D comparisons,
Jaccard on both SAEs with its mismatched null, the shared/lost/made buckets, the
judge's conveyance with `null_feat`/`null_expl`/per-bucket chance/label-quality
stratification, and the same per-activation aggregation — is simply computed more
than once and reported side by side.

### 7a. Paragraph ablation — which part of the explanation carries it

The AV writes to a stable three-part shape:

1. what kind of document this is
2. what it is about
3. **what the final token is doing**

Part 3 is a different kind of claim from parts 1–2: it describes the single token
the activation sits on, not the passage around it. If it carries most of the
reconstruction on its own, the NLA is doing next-token description rather than
context summarisation, and every other section has to be read in that light.

The explanation is generated **once** per activation and then split, so the
comparison is paired — none of the difference between variants can come from
resampling the AV.

| variant | what it is |
|---|---|
| `full` | the explanation as written |
| `no_final` | parts 1–2 |
| `final_only` | part 3 |

**The split is anchored on the phrase, not on paragraph count.** Measured over 250
real explanations:

```
exactly 3 paragraphs                                  245/250   98%
"final token" appears at least once                   250/250  100%
...appears more than once (would be ambiguous)          0/250
exactly one paragraph contains it, and not the first  250/250  100%
```

The five that are not three paragraphs are the case that makes the anchor
necessary: the final token is *itself* a newline, so the AV writes `Final token "`
/ blank line / `" ends a transitional header…` and the paragraph splits itself.
Anchoring on the phrase rejoins those; counting paragraphs would have put half of
part 3 into `no_final` and corrupted both variants without any error.

`explanation_splits.json` dumps 20 splits to eyeball and records the method used
per sample. **Watch the anchor rate in `SUMMARY.md` §6** — if it falls, the AV's
output format has moved and the variants are no longer what they claim.

**Length is reported, not adjusted away.** The variants differ in length, so a
variant could score higher simply by having more text. `SUMMARY.md` prints token
counts and FVE per 100 tokens beside the raw figure. On this AV the two ablations
are close in length anyway (~318 vs ~337 characters), but that is a property of
this checkpoint, not a guarantee.

### 7b. Near-miss sweep — is the match specific to this token?

The standing Jaccard null compares the rebuild against an activation from an
**unrelated conversation**, which shares almost nothing (0.013 against a matched
0.540). Clearing that bar shows the rebuild is not generic. It does **not** show
the rebuild is specific to *this token*.

The harder version: compare the rebuild of position *p* against the **real
activation at p+d in the same conversation**, for d ∈ {−50, −20, −5, +5, +20,
+50}. Same topic, same document, same speaker, a few tokens away.

- **flat across d** → the explanation describes the passage; the exact position is
  doing no work
- **falls with |d|** → the round trip is genuinely position-specific

No extra AV or AR work: the round trip still happens only at *p*. The neighbour
activations come from the forward pass that already runs during extraction, which
is also why they are saved there — doing it later would need Gemma resident
alongside the AV and AR, which does not fit.

**Directions are never averaged.** Text before *p* is context the activation
encodes; text after is context it cannot. −20 and +20 are different measurements
and pooling them would hide any asymmetry.

**Attrition is reported, not clamped.** An offset that falls outside the valid
region is dropped, never moved to the nearest legal position — clamping would turn
a +50 into a +30 and make the x-axis a lie. Since short responses lose the far
offsets first, and short responses are not a random subsample, `SUMMARY.md` §7
also prints a **restricted** curve over only the activations long enough to supply
every offset, so the points are comparable to each other.
