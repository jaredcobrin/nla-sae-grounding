# Results

All numbers from **50 Gemma-3-12B-IT layer-32 activations**, 5 sampled
explanations each, on Gemma-generated rollouts (oasst1 + LMSYS prompts, responses
from Gemma itself — the corpus Gemma Scope 2's IT SAEs were fine-tuned on).

Raw artefacts for every table are in [`results/`](.).

> ### Read this before the tables
>
> **Two sections report shared / lost / made counts, and the numbers look like
> they disagree.** They do not — each counts a different population:
>
> | § | one row = | which features | shared / lost / made |
> |---|---|---|---|
> | **2** | one of 250 (activation × explanation) pairs | **all** of them | means **14.1 / 5.8 / 5.1** |
> | **4** | the same 250 pairs | only those with a **validated label** | **1840 / 630 / 562** |
>
> §4 drops unlabelled features because it asks *"does the explanation cover this
> feature?"* — unanswerable if you cannot say what the feature detects. That
> removes ~50%, exactly the label coverage in §3. And §2 reports **means** where
> §4 reports **totals**: 14.1 × 250 = 3529, of which 1840 carry a label.
>
> ### Which SAE produced which number
>
> **Two different SAEs are used in this file**, and it matters — they are
> separately trained dictionaries, not two settings of one knob.
>
> | § | what | SAE | features/activation |
> |---|---|---|---|
> | **1** | the four FVE scores, and L0 119.9 / 101.3 | **`l0_big`** | ~120 |
> | **2** | the kept/lost/made counts | **both**, side by side | ~21 and ~120 |
> | **3** | labelling | `l0_small` | ~21 |
> | **4** | conveyed rates, the 2×2, the AUC stratification | **`l0_small`** | ~21 |
> | **5** | blind descriptions | `l0_small` | ~21 |
> | — | `trust_report.py`, the tool | `l0_small` | ~21 |
>
> `l0_big` is used where **reconstruction fidelity** is the question, because it
> reconstructs better. `l0_small` is used everywhere a feature has to be *named*,
> because at ~120 features per activation the labels are not reliable — the
> measured label-vs-wrong-label AUC gap is **+0.092 at `l0_small` against +0.008
> at `l0_big`**. Full reasoning in [METHODOLOGY.md](METHODOLOGY.md).
>
> **Consequence, stated plainly:** §1's C > A asymmetry is measured on `l0_big`
> only. §4 runs on `l0_small`. The artefact `refeature.py` writes for `l0_small`
> contains feature sets but **no reconstruction scores**, so whether that
> asymmetry holds at `l0_small` is **not established here**. Where §4 and the tool
> invoke it, treat it as a plausible transfer, not a measured one.
>
> ### Two experiments are deliberately not here
>
> A source-document presence check and a bucket-composition analysis were run,
> produced publishable-looking numbers, and **did not meet the bar**. They are in
> [INCONCLUSIVE.md](INCONCLUSIVE.md) with their full numbers and the reasons —
> chiefly that both judged features against the **whole document**, when an
> activation sampled at one token position is not a claim about the whole
> document.

---

## 1. Four reconstruction scores

Four FVE numbers, all on the same 50 activations. **B is the NLA's own round-trip
score**: activation → AV writes an explanation → AR rebuilds an activation from
that text. It is the number the NLA paper reports for its own system.

| | what is being reconstructed, from what | SAE used | FVE |
|---|---|---|---|
| **A** | the activation, from **the SAE's features** | `l0_big` | 0.587 |
| **B** | the activation, from **two sentences of English** — *this is the NLA* | **none** | **0.739** |
| **C** | the AR's output, from **the SAE's features** | `l0_big` | 0.700 |
| **D** | the activation, from the SAE's reading of the AR's output | `l0_big` | 0.494 |

**B does not involve the SAE at all** — it is activation → AV → text → AR →
activation, scored directly. So B is fixed no matter which SAE is chosen; only
A, C and D would move.

`l0_big` is the variant selected for reconstruction fidelity (~120 active
features against `l0_small`'s ~21), so **A is the SAE at its strongest**, which
makes B > A the conservative form of that comparison. Re-running A at `l0_small`
would be expected to score lower and widen the gap — *expected*, not measured;
these are separately trained dictionaries, and the check is item 0 in
[FUTURE_WORK.md](FUTURE_WORK.md).

### B > A, by 0.152

The NLA round trip reconstructs an activation **better than this SAE does** —
measured on the corpus that SAE was fine-tuned on.

Both are lossy compressions of the same vector, so the comparison is fair in that
sense, but they were built for different purposes: the SAE is optimised for sparse
*decomposition*, the NLA for *reconstruction*. This says the NLA reconstructs
better. It does not say English is a better representation than a feature basis.

### C > A: the SAE reads the AR's output better than a real activation, by 0.113

Same SAE, same dictionary, two different inputs. It reconstructs the AR's output
to 0.700 and a real activation to only 0.587.

**L0 — how many dictionary features actually switch on** — points the same way,
and is a genuinely separate quantity: a count, not a reconstruction score.

| | features used (L0) | reconstruction (cosine) |
|---|---|---|
| real activation | 119.9 | 0.99424 |
| AR output | **101.3** | **0.99581** |

**Fewer features, better fit.** These normally trade off — more dictionary
entries means more of the vector captured — so the AR's output using ~19 fewer
features *and* landing closer is the notable part.

> **Only the L0 column is independent evidence.** The cosine column is the FVE
> above restated: `FVE = 1 − mean(MSE)/rawvar` and `MSE = 2(1−cos)`, so cosine is
> fixed once FVE is known. Both values here reproduce to five decimals from the
> FVE column. It is shown because cosine is the stable quantity when `rawvar`
> amplifies FVE, not because it corroborates anything. An earlier version of this
> file called the whole table "a second, independent measurement" — that was
> wrong for one of its two columns.

No mechanism is claimed. What matters downstream is only the fact of it: **the
two sides of every feature comparison in this file are not read by the SAE with
equal fidelity** — it captures more of the AR's output than of the original.

That asymmetry is part of why the tool calls its third bucket `UNVERIFIED` rather
than "invented": a feature the SAE fails to find in the original may still be
there.

**But note the boundary.** This is measured on `l0_big`; the tool and §4 run on
`l0_small`, where it has not been measured — `refeature.py` writes feature sets
without reconstruction scores. The `UNVERIFIED` name does not depend on it: the
bucket is *by construction* "the AR produced it and we did not find it in the
original", which is unchecked rather than false, and an SAE is incomplete in any
case. Measuring the asymmetry at `l0_small` is one of the cheap open items in
[FUTURE_WORK.md](FUTURE_WORK.md) — the saved vectors are enough, no GPU needed.

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

## 2. More features are kept at low sparsity than at high sparsity

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

**What is measured:** the round trip keeps 71% of features under an SAE that
fires ~21 per activation, and 57% under one that fires ~120, both far above their
mismatched controls.

The natural reading is "coarse features survive, fine-grained ones don't", but
these two SAEs differ in more than granularity — they are separately trained
dictionaries with different thresholds and different reconstruction quality
(§1: cos 0.9937 at `l0_big`). Nothing here isolates granularity as the cause.

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

## 4. Shared features are conveyed by the explanation more often than lost or made ones

Judged **against the explanation text**. One question, asked once per (feature,
explanation) pair: *does this explanation cover this feature?*

**Population: 3,032 pairs** — the 250 activation × explanation pairs, restricted
to features carrying a validated label, because you cannot ask whether a text
covers a feature you cannot describe.

| bucket | n | **conveyed** | not conveyed | unknown | mean label AUC |
|---|---:|---:|---:|---:|---:|
| **shared** | 1840 | **46%** | 50% | 4% | 0.872 |
| **lost** | 630 | **31%** | 66% | 3% | 0.856 |
| **made** | 562 | **35%** | 60% | 5% | 0.858 |
| **REAL** | 2470 | 42% | 54% | 4% | — |

**`REAL` is `shared` + `lost` = 1840 + 630.** Those are the features genuinely
present in the original activation. `made` is excluded from it precisely because
those features are *not* in the original — they appear only in the AR's output.

### Correcting for the judge's own error rate

The judge is not perfect. Measured against features that **provably did not fire**
in the activation — where the correct answer is always "not covered" — it
still said "covered" **5.7%** of the time. Those are false positives, and some of
the 42% above are exactly that kind of mistake.

Removing them, with the formula the script itself prints:

$$\frac{0.422 - 0.057}{1 - 0.057} = \mathbf{38.7\%}$$

**So about 39% of what is in the activation reaches the explanation** — a little
under two-fifths, not "about half".

> An earlier version of this file said "~43%" and called it corrected. It was
> not: correcting *lowers* the number, and 43% is above the raw 42.2%. The raw
> rate had been rounded the wrong way and mislabelled. The direction of a
> correction is worth checking — it is the kind of error that survives review
> because it looks like it has already been through one.

### What is actually established

Against the judge's measured **5.7% false-positive floor**, `shared` at 46% is
**8.1× the floor**. The separations between buckets:

| comparison | difference | 95% CI | verdict |
|---|---:|---|---|
| shared vs lost | +14.5 pts | [+10.2, +18.8] | **solid**, +6.4σ |
| shared vs made | +10.9 pts | [+6.3, +15.4] | **solid**, +4.6σ |
| made vs lost | +3.6 pts | **[−1.7, +9.0]** | **cannot be called**, p = 0.18 |

**The result is this correlation: features shared between the activation and its
reconstruction are conveyed by the explanation more often than features in either
of the other two buckets.**

`made` does sit above `lost` on the point estimate — 35.1% against 31.4% — but
its interval includes zero *and* includes `lost` being higher. At p = 0.18 a gap
that size turns up by chance about one run in five. **The ordering
shared > made > lost is what these 50 activations happened to show; only the
first step of it is established.**

That is a correlation between an SAE's reading of an activation and the text an
independent language model wrote about it. It is what the pipeline was built to
measure. Anything beyond it — *why* the buckets differ, *what* the AV is doing —
is not measured here.

### One thing the same data rules out

It is tempting to read `shared` 46% vs `lost` 31% as *"mentioned features
survive, unmentioned ones don't."* **That conditions the wrong way round.** 46% is
the share of *survivors* that were mentioned; that claim needs the share of
*mentioned features* that survived. Same 2×2, different number:

| features genuinely in the activation | survived | lost | total |
|---|---:|---:|---:|
| **conveyed** by the explanation | 845 | 198 | 1043 |
| **not conveyed** | 995 | 432 | 1427 |

| | |
|---|---|
| P(survives \| conveyed) | **81.0%** |
| P(survives \| not conveyed) | **69.7%** |
| difference | **+11.3 points**, +6.4σ, odds ratio **1.85** |

So being conveyed is associated with survival, but does not determine it. The two
off-diagonal cells say so directly:

- **995 features (40%)** were not conveyed and survived anyway — the largest cell
  in the table, and **54% of everything that survived**.
- **198 features (8%)** were conveyed and lost anyway.

**No mechanism is offered for either.** An earlier version of this file asserted
that the explanation is the only channel between AV and AR, so an unmentioned
feature "has nothing to be rebuilt from". The 995 cell falsifies that, and
nothing here establishes what replaces it. The AR could be inferring those
features from the passage's subject; the judge could be under-detecting what the
explanation conveys; the SAE could be reading the two vectors differently (§1,
C > A). This data cannot separate those.

> **What this means for the tool.** `trust_report.py` marks a feature CONFIRMED
> when it is in the activation and in the AR's reconstruction — exactly what it
> says, and the README already states the explanation text is never read. This
> table puts a number on the distance between those: for **54%** of CONFIRMED
> features, the explanation did not visibly convey them. **CONFIRMED means the
> round trip preserved it, not that the explanation said it.**

### Is that gap just better labels? No.

`shared` features do carry slightly better labels — mean AUC **0.872** against
**0.856** for `lost`, which at these sample sizes is **+5.0σ**. Real, so it has to
be ruled out as the cause.

Holding label quality fixed by comparing only within matched AUC bands:

| label AUC band | shared conveyed | lost conveyed | gap |
|---|---:|---:|---:|
| 0.756–0.82 | 38% (n=507) | 23% (n=213) | **+15** |
| 0.82–0.86 | 44% (n=300) | 32% (n=105) | **+12** |
| 0.86–0.90 | 43% (n=334) | 35% (n=116) | **+8** |
| 0.90–1.00 | 54% (n=683) | 36% (n=187) | **+18** |

**The gap holds in every band**, and the weighted within-band gap is **+14.0
points** against a raw gap of +14.5. Label quality accounts for roughly **half a
point** of it. The 0.016 AUC difference is simply far too small to move a
15-point conveyance gap — and every bucket sits well above the 0.756 validation
threshold anyway.

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

## 5. Qualitative: blind descriptions

A model is given **only the feature labels** for a bucket and asked to describe
what they collectively point at — it never sees the AV's explanation. So when its
summary and the explanation agree, that agreement is evidence rather than an echo.

This is qualitative and read by eye. It is here because it is legible, not
because it is a measurement.

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
- **Some "lost" features may be SAE misfires** rather than things the bottleneck
  destroyed. The experiment that tried to measure this did not meet the bar —
  [INCONCLUSIVE.md](INCONCLUSIVE.md), Test 2 — so the size of the effect is
  unknown, not zero.
- **Nothing here checks whether a feature is "true" of the source text.** The two
  attempts are in [INCONCLUSIVE.md](INCONCLUSIVE.md). An activation at one token
  position is not a claim about the whole document, so that comparison was
  measuring the wrong thing.
- **Surviving the round trip is not evidence the explanation carried it.** 54% of
  surviving features were never visibly conveyed by the text (§4); the AR infers
  them from the passage's subject. Every "kept" and "confirmed" number in this
  repo therefore measures *the AR's prior plus the explanation*, not the
  explanation alone. Separating the two would need an AR trained independently of
  the AV — which the released checkpoints do not provide.
- **"Invented" features are measured on a vector already closer to the SAE's
  dictionary than a real activation** (§1, C > A), so the two sides are not quite
  like-for-like.
- **The confabulation phenomenon is not a new finding.** The NLA paper documents
  it. What is new here is checking it against SAE features.
- **The prior-art check was not exhaustive.**
