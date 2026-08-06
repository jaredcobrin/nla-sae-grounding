# Results

All numbers from **50 Gemma-3-12B-IT layer-32 activations**, 5 sampled
explanations each, on Gemma-generated rollouts (oasst1 + LMSYS prompts, responses
from Gemma itself — the corpus Gemma Scope 2's IT SAEs were fine-tuned on).

Raw artefacts for every table are in [`results/`](.).

---

## 1. Reconstruction: the text bottleneck beats the SAE

Four comparisons, all in FVE, all on the same 50 activations:

| | what it measures | FVE |
|---|---|---|
| **A** SAE(orig) vs orig | how well the SAE represents the activation | 0.587 |
| **B** AR(AV(orig)) vs orig | how well **two sentences of English** represent it | **0.739** |
| **C** SAE(AR) vs AR | how well the SAE represents the AR's output | 0.700 |
| **D** SAE(AR) vs orig | both lossy paths composed | 0.494 |

**B > A by 0.152.** An activation survives being verbalised and reconstructed
better than it survives a purpose-built 16,384-feature sparse autoencoder — on
the corpus the SAE was fine-tuned on.

An earlier n=10 pass reproduced this on three corpora:

| | FineWeb | Rollouts | WildChat |
|---|---|---|---|
| A · SAE vs orig | 0.4575 | 0.5652 | 0.4702 |
| B · AR vs orig | **0.7355** | **0.7493** | **0.7251** |
| gap B−A | +0.278 | +0.184 | +0.255 |

The SAE gains +0.108 on its home distribution — closing about a third of the gap
— but the ordering never flips.

**C > A on all three corpora** (+0.157/+0.105/+0.172). The AR does not emit an
arbitrary vector; it emits one sitting *closer to the SAE's dictionary* than a
real activation does. That is what a model trained to predict activations from
text would do, and it is a caveat on every "invented feature" count below: they
are measured on a vector that is already more SAE-friendly than the original.

**Read cosine, not FVE, for small differences.** Gemma's `rawvar` is 0.0279, so
`FVE ≈ 1 − 65×(1−cos)` and 0.001 of cosine moves FVE by 0.065.

---

## 2. Coarse features survive; fine-grained ones do not

Same vectors, re-encoded under both sparsities:

| SAE | features/activation | shared | lost | made | **kept** | Jaccard | control |
|---|---|---|---|---|---|---|---|
| `l0_small` | ~21 | 14.1 | 5.8 | 5.1 | **71%** | 0.576 | 0.016 |
| `l0_big` | ~120 | 68.5 | 51.4 | 32.8 | **57%** | 0.450 | 0.026 |

The control is the same reconstruction's features scored against a **different**
activation — 0.016–0.026 against 0.45–0.58 matched, a 20–35× separation. Without
it the raw overlap would be uninterpretable, since many features fire on almost
any text.

**The round trip keeps the gist and drops the detail.** That is what you would
expect from squeezing an activation through two sentences of English.

---

## 3. Labelling, and how much of it to trust

```
labels attempted         1,624
  mean AUC over ALL      0.742        <- includes the half that get rejected
  wrong-label null       0.499        <- chance
  gap                    +0.243
  threshold (95th pct)   0.756

validated (kept)         816 / 1,623  (50%)
  mean AUC               0.873
  median                 0.875
```

**0.742 is not the quality of the labels this repo uses.** It averages over every
label the generator attempted, half of which fail validation and are thrown away.
The ones actually used average **0.873**, and 19 features score a perfect 1.0.

**"Validated" means "beats a wrong label at a measured 5% false-positive rate",
not "correct".** Roughly 40% of kept labels sit just above threshold, where a
label is predictive but vague about *what* the feature detects.

The other 50% are **counted in every total but never named**. A report resting on
4 of 15 features says so.

---

## 4. How much of the activation does the explanation convey?

Per feature, does the AV's explanation cover it?

```
bucket        n     present   not present   unknown
shared     1840       46%         50%          4%
lost        630       31%         66%          3%
made        562       35%         60%          5%
ALL-real   2470       42%         54%          4%
```

Corrected for the 5.7% false-positive floor: **~43% of what is in the activation
is conveyed.**

**Mentioned features survive; unmentioned ones do not — 46% vs 31%.** The
explanation is the only channel between AV and AR, so a feature the text never
carries has nothing to be rebuilt from.

### By category

| category | n | clearly conveyed |
|---|---|---|
| code_technical | 360 | **66%** |
| other | 40 | 52% |
| named_entity | 520 | 50% |
| topic_domain | 1475 | 43% |
| numeric | 120 | 42% |
| language | 90 | 37% |
| formatting | 95 | 37% |
| syntax | 1110 | 36% |
| sentiment_tone | 440 | 36% |
| genre_register | 320 | 34% |

`code_technical` stands out. `syntax` is uniformly low, which is the expected
null — a two-sentence summary describes what text is *about*, not its grammar.

### The judge's own validation

```
false-positive rate    5.7%      (the earlier prompt scored 78.3% here)
matcher AUC            0.807     vs unrelated explanations
                       0.836     vs non-firing features
self-consistency       89.2%     across 5 explanations of the same activation
```

Grade reliability, against a 25% base rate:

| grade | on real | on non-firing | % real |
|---|---:|---:|---:|
| CLEARLY | 1043 | 376 | **74%** |
| PROBABLY | 324 | 147 | 69% |
| UNCLEAR | 36 | 34 | 51% |
| NO | 1629 | 8539 | **16%** |

`NO` sitting *below* base rate means a "no" is real evidence of absence.

---

## 5. "Invented" features are mostly not invented

Every feature classified on three axes against **the source document**, which
this run finally saves:

```
judged present in its OWN text        77.8%
judged present in a DIFFERENT text    47.8%    <- control
gap                                   +30.0
```

| bucket | own | control | gap |
|---|---:|---:|---:|
| shared | 80% | 46% | +34 |
| lost | 73% | 46% | +27 |
| made | 78% | 56% | +22 |

Broken out, for features that are **content-bearing**:

| | present | control |
|---|---:|---:|
| made · content · specific | 65% | 30% |
| made · content · generic | 68% | 25% |

**Two-thirds of "invented" content features are genuinely in the source
document** — just not at the sampled token position. The AR reconstructs
**document-level context**, not **position-specific state**.

"Made up" is the wrong name for them. In the tool they are called **UNVERIFIED**.

---

## 6. A negative result: the round trip is indiscriminate by feature type

Composition of each bucket, grammar/content × generic/specific:

| bucket | n | content+specific | content+generic | grammar+specific | grammar+generic |
|---|---:|---:|---:|---:|---:|
| shared | 366 | 22% ±4 | 24% ±4 | 16% ±4 | 37% ±5 |
| lost | 128 | 23% ±7 | 26% ±8 | 20% ±7 | 31% ±8 |
| made | 113 | 18% ±7 | 25% ±8 | 17% ±7 | 41% ±9 |

Differences against `shared`, in sigma:

| cell | lost | made |
|---|---:|---:|
| content+specific | 0.2 | −1.1 |
| content+generic | 0.5 | 0.2 |
| grammar+specific | 0.8 | 0.1 |
| grammar+generic | −1.3 | 0.6 |

**Every difference is under 1.3σ.** The plausible story — "themes survive,
specifics are lost" — is not there. Hand-picked examples supporting it are easy to
find (`Nginx`, `"tomato"`, temperature values all appear in `lost`), and that is
exactly why the aggregate matters.

### What *does* differ

Lost **content+specific** features are less accurate about the text than shared
ones: **57% vs 80%**, a 24-point gap at **2.4σ**.

So some of what we call "destroyed by the round trip" is the **SAE having fired
spuriously in the first place** — the feature was never really about the
document, and the AR simply did not reproduce the error. That is a materially
different explanation for "loss", and it partly undercuts the headline.

### Label quality is not the confound

Mean label AUC by cell runs 0.82–0.89 — every cell well above the 0.756
threshold, and the shared/lost/made spread inside any row is within error bars.
Two real effects:

- **content** labels beat **grammar** labels: 0.877 vs 0.854 (**4.1σ**)
- **specific** beats **generic**: 0.876 vs 0.858 (**3.0σ**)

Both make sense — "mentions of CPU components" gives a scorer something
checkable; "a noun following a preposition" does not.

---

## 7. Qualitative: blind descriptions

A model given **only the feature labels**, never the explanation:

**Activation 0** — AV said *"PC build review… Intel Core i7-14700"*

| | |
|---|---|
| shared, blind | "computer hardware, specifically models and specifications… CPU/GPU components" |
| **control** | "technical document describing inventions or patents… manufacturing and lighting" |

**Activation 1** — AV said *"PC hardware checklist… AMD Ryzen 5 7600"*

| | |
|---|---|
| shared, blind | "computer hardware and technical specifications… model names, version numbers, motherboards" |
| **control** | "programming, specifically Python… errors and debugging" |

The blind summaries recover the AV's subject; the controls land elsewhere
entirely.

**Do not over-read the thin buckets.** `shared` averages 7.3 labelled features,
`lost` 2.6 and `made` 2.3. On 2–3 labels the describer over-reaches about 10% of
the time — one produced *"a legal document or agreement"* from a single feature
about legal notices.

---

## Limitations

- **n = 50 activations**, one model, one layer, one corpus. Runs are not
  independent: 50 × 5 sampled explanations, so effective n is nearer 50 than 250.
- **The FVE gate selects on the outcome metric** — activations are chosen to
  score 0.73–0.77, so they are easier than average by construction. Every seed
  tried is logged.
- **~50% label coverage.** The unnamed half may behave differently; nothing here
  would show it.
- **SAE incompleteness.** A claim can be true and have no corresponding feature.
  Absence of a feature is weak evidence — a limitation the NLA paper itself names.
- **Some "lost" features were spurious** (§6), so the loss rate overstates what
  the bottleneck destroys.
- **"Invented" features are measured on a vector already closer to the SAE's
  dictionary than a real activation** (§1, C > A), so the two sides are not quite
  like-for-like.
- **The confabulation phenomenon is not a new finding.** The NLA paper documents
  it. What is new here is checking it against SAE features.
- **The prior-art check was not exhaustive.**
