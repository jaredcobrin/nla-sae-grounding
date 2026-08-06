# Results

All numbers from **50 Gemma-3-12B-IT layer-32 activations**, 5 sampled
explanations each, on Gemma-generated rollouts (oasst1 + LMSYS prompts, responses
from Gemma itself — the corpus Gemma Scope 2's IT SAEs were fine-tuned on).

Raw artefacts for every table are in [`results/`](.).

> ### Read this before the tables
>
> Three sections below report shared / lost / made counts, and **the numbers look
> like they disagree.** They do not — each counts a different population, for a
> stated reason.
>
> | § | one row = | which features | shared / lost / made |
> |---|---|---|---|
> | **2** | one of 250 (activation × explanation) pairs | **all** of them | means **14.1 / 5.8 / 5.1** |
> | **4** | the same 250 pairs | only those with a **validated label** | **1840 / 630 / 562** |
> | **6** | **one** explanation per activation — 50 pairs | validated label | **366 / 128 / 113** |
>
> - §4 drops unlabelled features because it asks *"does the explanation cover this
>   feature?"* — unanswerable if you cannot say what the feature detects. That
>   removes ~50%, exactly the label coverage in §3.
> - §6 uses one explanation per activation because a feature can be `shared` under
>   one sampled explanation and `lost` under another. Mixing them would put the
>   same feature in two buckets of one table
>   ([`classify_features.py:145`](../src/classify_features.py#L145)).
> - §2 reports **means**, §4 and §6 report **totals**. 14.1 × 250 = 3529, of which
>   1840 carry a label.
>
> **And the word "present" means two different things.** In §4 it is *"the
> explanation conveys this feature"*. In §5–6 it is *"this feature is really in the
> source document"* — a different judge answering a different question.

---

## 1. Reconstruction — the headline

Four FVE numbers, all on the same 50 activations. **B is the NLA's own round-trip
score**: activation → AV writes an explanation → AR rebuilds an activation from
that text. It is the number the NLA paper reports for its own system.

| | what is being reconstructed, from what | FVE |
|---|---|---|
| **A** | the activation, from **the SAE's features** | 0.587 |
| **B** | the activation, from **two sentences of English** — *this is the NLA* | **0.739** |
| **C** | the AR's output, from **the SAE's features** | 0.700 |
| **D** | the activation, from the SAE's reading of the AR's output | 0.494 |

### B > A: the text bottleneck beats the SAE, by 0.152

An activation survives being written into English and rebuilt **better than it
survives a purpose-built 16,384-feature sparse autoencoder** — measured on the
corpus that SAE was fine-tuned on.

### C > A: the SAE reads the AR's output better than a real activation, by 0.113

Same SAE, same dictionary, two different inputs. It reconstructs the AR's output
to 0.700 and a real activation to only 0.587.

A second, independent measurement points the same way — how many dictionary
features each vector needs:

| | features used (L0) | SAE reconstruction (cosine) |
|---|---|---|
| real activation | 119.9 | 0.99424 |
| AR output | **101.3** | **0.99581** |

**Fewer features, better fit.** Whatever the reason, the two sides of every
feature comparison below are not being read by the SAE with equal fidelity, and
§5 returns to what that costs.

*(In cosine the gap is 0.0016. FVE magnifies it because Gemma's `rawvar` is
0.0279 — see the note at the end of this section.)*

### Side note: it holds on three corpora, and the SAE does best on its home turf

An earlier n=10 pass, same pipeline:

| | FineWeb | **Rollouts** | WildChat |
|---|---|---|---|
| A · SAE | 0.4575 | **0.5652** | 0.4702 |
| B · NLA | 0.7355 | **0.7493** | 0.7251 |
| gap B−A | +0.278 | **+0.184** | +0.255 |
| gap C−A | +0.157 | **+0.105** | +0.172 |

Rollouts is the Gemma-generated corpus the SAE was fine-tuned on, and it is where
the SAE performs best — +0.108 over FineWeb, closing about a third of the gap to
the NLA. **The ordering never flips on any corpus**, and both gaps keep their sign
everywhere. This is why the main results use rollouts: it is the setting most
favourable to the SAE, so it is the conservative place to run the comparison.

> **Read cosine, not FVE, for small differences.** Gemma's `rawvar` is 0.0279, so
> `FVE ≈ 1 − 65×(1−cos)`: 0.001 of cosine moves FVE by 0.065. Large-looking FVE
> gaps here can be small cosine gaps.

---

## 2. Coarse features survive; fine-grained ones do not

Same vectors, re-encoded under both sparsities:

| SAE | features/activation | shared | lost | made | **kept** | Jaccard | control |
|---|---|---|---|---|---|---|---|
| `l0_small` | ~21 | 14.1 | 5.8 | 5.1 | **71%** | 0.576 | 0.009 |
| `l0_big` | ~120 | 68.5 | 51.4 | 32.8 | **57%** | 0.450 | 0.026 |

The control is the same reconstruction's features scored against a **different**
activation — 0.009–0.026 against 0.45–0.58 matched, a **17–65× separation**.
Without it the raw overlap would be uninterpretable, since many features fire on
almost any text.

> **The control was itself wrong once, and the fix is why these two rows now
> agree.** `refeature.py` paired each activation with its *neighbour*, but stage-0
> samples ~10 positions per document and writes them adjacently — so the
> "mismatched" pair was often another position of the **same document**. That is
> not a mismatch, and it inflated the `l0_big` control to 0.040 where
> `roundtrip.py`, which pairs halfway across the set, gave 0.026. Both scripts now
> use the half-offset and independently produce 0.0263. The error was
> conservative — it made the result look weaker — but the two files disagreeing
> was the signal that something was wrong.

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

# Part I — Does the *explanation* convey the activation?

Everything in this part is judged **against the explanation text**. One question,
asked once per (feature, explanation) pair: *does this explanation cover this
feature?*

**Population: 3,032 pairs** — the 250 activation × explanation pairs, restricted
to features carrying a validated label, because you cannot ask whether a text
covers a feature you cannot describe.

---

## 4. About 43% of what is in the activation reaches the text

```
bucket        n     conveyed   not conveyed   unknown
shared     1840       46%          50%          4%
lost        630       31%          66%          3%
made        562       35%          60%          5%
REAL       2470       42%          54%          4%
```

**`REAL` is `shared` + `lost` = 1840 + 630.** Those are the features genuinely
present in the original activation. `made` is excluded from it precisely because
those features are *not* in the original — they appear only in the AR's output.

Corrected for the judge's measured 5.7% false-positive floor:
**~43% of what is in the activation reaches the explanation.**

### The one comparison that matters here

**Features the explanation mentions survive the round trip; features it does not
mention do not — 46% vs 31%.**

The explanation is the *only* channel between AV and AR. A feature the text never
carries has nothing to be rebuilt from, and this is the direct evidence of that.

### By category

Same 3,032 pairs, cut by what kind of thing the feature detects:

| category | n | conveyed |
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

### Why the judge is trustworthy

The judge does not emit a bare yes/no — it grades `CLEARLY` / `PROBABLY` /
`UNCLEAR` / `NO`. The tables above collapse `CLEARLY` + `PROBABLY` to "conveyed".
Left uncollapsed, the grades separate:

| grade | on real features | on features that never fired | % real |
|---|---:|---:|---:|
| CLEARLY | 1043 | 376 | **74%** |
| PROBABLY | 324 | 147 | 69% |
| UNCLEAR | 36 | 34 | 51% |
| NO | 1629 | 8539 | **16%** |

Base rate is 25%. `CLEARLY` runs 3× above it, and **`NO` runs *below* it** — so a
"no" from this judge is real evidence of absence, not just a shrug.

```
false-positive rate    5.7%      the prompt this replaced scored 78.3%
matcher AUC            0.807     vs unrelated explanations
                       0.836     vs features that never fired
self-consistency       89.2%     across 5 explanations of one activation
```

The 78.3% is not a typo — the first prompt said "yes" to four out of five
features that provably were not in the activation. How this one was chosen
instead is in [METHODOLOGY.md](METHODOLOGY.md).

---

# Part II — Are the features really in the *source document*?

**Different question, different judge, and this is where the word "present"
changes meaning.** Part I asked whether the *explanation* covers a feature.
Part II asks whether the feature is genuinely in the **source text at all** —
comparing each feature's label against the document the activation came from.

**Population: 607 (feature, activation) pairs.** One explanation per activation
rather than five, because a feature can land in `shared` under one sampled
explanation and `lost` under another; mixing them would put one feature in two
rows of the same table.

**Every number in Part II is a gap against a control** — the same feature judged
against a *different* document. Feature labels are often generic enough to sound
plausible about any text, so the raw rate alone means nothing.

---

## 5. "Invented" features are mostly not invented

```
judged present in its OWN document        77.8%
judged present in a DIFFERENT document    47.8%   <- control
gap                                       +30.0
```

The control lands near 50%, which is the point: half the time a label sounds
right about a document it has nothing to do with. Only the gap carries signal.

| bucket | own | control | gap |
|---|---:|---:|---:|
| shared | 80% | 46% | **+34** |
| lost | 73% | 46% | **+27** |
| made | 78% | 56% | **+22** |

**`made` has a real gap too.** If those features were invented, they would sit at
the control. They do not.

Narrowing to **content-bearing** features, where the judgement is most meaningful:

| | own | control |
|---|---:|---:|
| made · content · specific | 65% | 30% |
| made · content · generic | 68% | 25% |

**Two-thirds of "invented" content features are genuinely in the source
document** — just not at the sampled token position. The AR is reconstructing
**document-level context**, not **position-specific state**.

"Made up" is therefore the wrong name. The tool calls them **UNVERIFIED**, which
means *not checked* — not *false*.

> **The §1 caveat lands here.** C > A means the SAE reads the AR's output more
> faithfully than a real activation (0.700 vs 0.587). So a feature counted as
> "invented" may have been in the original all along and simply invisible to the
> SAE there. The instrument is more sensitive on one side of the subtraction than
> the other, which inflates this bucket. That is a second, independent reason to
> read "invented" as *unverified*.

---

## 6. A negative result: the round trip is indiscriminate by feature type

Same 607 pairs. If the round trip destroyed *specifics* and kept *themes*, the
three buckets would have visibly different composition. Here is the composition:

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

Still Part II's population. A model is given **only the feature labels** for a
bucket and asked to describe the document — it never sees the AV's explanation.
So when its summary and the explanation agree, that agreement is evidence rather
than an echo.

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
