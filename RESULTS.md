# Results

**50 Gemma-3-12B-IT layer-32 activations, 5 sampled explanations each** — 250
(activation, explanation) pairs — on Gemma-generated rollouts (oasst1 + LMSYS
prompts, responses from Gemma itself).

How any of this was measured, and why: **[METHODOLOGY.md](METHODOLOGY.md)**.
Raw artefacts: [`results/`](.). Experiments that did not meet the bar:
[INCONCLUSIVE.md](INCONCLUSIVE.md).

**Two SAEs are used.** `l0_big` (~120 active latents) for §1; `l0_small` (~21)
for §3, §4, §5 and the tool; both in §2. They are separately trained
dictionaries, and results do not automatically transfer between them.

---

## 1. Four reconstruction scores

**B is the NLA's own round-trip score** — activation → AV writes an explanation →
AR rebuilds an activation from that text.

| | what is reconstructed, from what | SAE | FVE |
|---|---|---|---|
| **A** | the activation, from **the SAE's latents** | `l0_big` | 0.587 |
| **B** | the activation, from **two sentences of English** | none | **0.739** |
| **C** | the AR's output, from **the SAE's latents** | `l0_big` | 0.700 |
| **D** | the activation, from the SAE's reading of the AR's output | `l0_big` | 0.494 |

**B > A by 0.152.** The NLA round trip reconstructs an activation better than
this SAE does, on the corpus the SAE was fine-tuned on. B uses no SAE, so it is
unchanged by the choice of variant.

**C > A by 0.113.** The same SAE reconstructs the AR's output better than a real
activation. Latent counts go the same way:

| | latents on (L0) | reconstruction (cosine) |
|---|---|---|
| real activation | 119.9 | 0.99424 |
| AR output | **101.3** | **0.99581** |

Fewer latents and a closer fit, where the two normally trade off.

Three things to note when reading the above:

- Cosine is not separate evidence — `FVE = 1 − 2(1−cos)/rawvar`, so it is fixed
  once FVE is known. Only **L0** is independent.
- `rawvar` is 0.0279 here, so FVE magnifies cosine by **71.7×**: the C > A gap is
  0.0016 in cosine.
- C > A is measured on `l0_big` only. §4 and the tool use `l0_small`, where it has
  not been measured ([FUTURE_WORK.md](FUTURE_WORK.md) item 0).

### The same comparison on three corpora (n=10, earlier pass)

| | FineWeb | **Rollouts** | WildChat |
|---|---|---|---|
| A · SAE | 0.4575 | **0.5652** | 0.4702 |
| B · NLA | 0.7355 | **0.7493** | 0.7251 |
| gap B−A | +0.278 | **+0.184** | +0.255 |
| gap C−A | +0.157 | **+0.105** | +0.172 |

Both gaps keep their sign on every corpus. The SAE scores highest on rollouts,
the distribution it was fine-tuned on. (`rawvar` for this run is 0.0308, a 65.0×
multiplier — different sample, different constant.)

---

## 2. Latent overlap under both SAEs

The same 250 pairs, re-encoded under each SAE. Identical vectors — only the
dictionary changes.

**`l0_small`** — ~21 active latents per activation

| | total | mean/pair | share |
|---|---:|---:|---:|
| **shared** | 3,529 | 14.1 | **56.5%** |
| **lost** | 1,441 | 5.8 | 23.1% |
| **made** | 1,280 | 5.1 | 20.5% |
| *total* | *6,250* | *25.0* | |

**`l0_big`** — ~120 active latents per activation

| | total | mean/pair | share |
|---|---:|---:|---:|
| **shared** | 17,125 | 68.5 | **44.9%** |
| **lost** | 12,850 | 51.4 | 33.7% |
| **made** | 8,202 | 32.8 | 21.5% |
| *total* | *38,177* | *152.7* | |

**Against the control.** Many latents fire on almost any text, so the counts
above mean nothing until you know what two *unrelated* vectors would share. Same
measurement, scoring each reconstruction against a **different** activation:

| Jaccard | `l0_small` | `l0_big` |
|---|---:|---:|
| matched — reconstruction vs its own activation | **0.576** | **0.450** |
| mismatched control — vs a different activation | 0.009 | 0.026 |
| ratio | **65×** | **17×** |

Unrelated pairs share essentially nothing. Integer set arithmetic on latent IDs —
no judge, no labels, nothing to calibrate.

`l0_big` is used for the reconstruction scores in §1; `l0_small` for labelling
and everything downstream of it, because labels generated at `l0_big` fail
validation.

---

## 3. Label coverage

```
labels attempted    1,624
  mean AUC            0.742     over all attempts, including rejects
  wrong-label null    0.499     chance
  threshold           0.756     95th percentile of the null

validated (kept)      816 / 1,624   (50%)
  mean AUC            0.873
  median              0.875
```

**0.742 is not the quality of the labels in use** — it averages over every
attempt, half of which fail validation and are discarded. Those actually used
average **0.873**.

The unvalidated 50% are **counted in every total but never named**. A report
resting on 4 of 15 latents says so.

---

## 4. Conveyance: does the explanation cover each latent?

**3,032 (latent, explanation) pairs** — the 250 pairs restricted to latents
with a validated label. `CLEARLY` + `PROBABLY` are collapsed to "conveyed".

| bucket | n | **conveyed** | not conveyed | unknown | mean label AUC |
|---|---:|---:|---:|---:|---:|
| **shared** | 1840 | **45.9%** | 50% | 4% | 0.872 |
| **lost** | 630 | **31.4%** | 66% | 3% | 0.856 |
| **made** | 562 | **35.1%** | 60% | 5% | 0.858 |
| **REAL** = shared+lost | 2470 | 42.2% | 54% | 4% | — |

`REAL` is the latents genuinely in the original activation; `made` is excluded
because those appear only in the AR's output.

**Corrected for the judge's 5.7% false-positive rate**, `(0.422 − 0.057)/0.943` =
**38.7%** of what is in the activation reaches the explanation.

### Separations

| comparison | difference | 95% CI | |
|---|---:|---|---|
| shared vs lost | +14.5 pts | [+10.2, +18.8] | +6.4σ |
| shared vs made | +10.9 pts | [+6.3, +15.4] | +4.6σ |
| made vs lost | +3.6 pts | [−1.7, +9.0] | p = 0.18 |

`shared` at 45.9% is **8.1×** the judge's 5.7% false-positive floor. `made` and
`lost` cannot be separated — that interval includes zero and includes `lost`
being higher.

### Conveyance against survival

The bucket rates above are P(conveyed | outcome). The same pairs, conditioned the
other way:

| latents in the activation | survived | lost | total |
|---|---:|---:|---:|
| **conveyed** | 845 | 198 | 1043 |
| **not conveyed** | 995 | 432 | 1427 |

| | |
|---|---|
| P(survives \| conveyed) | **81.0%** |
| P(survives \| not conveyed) | **69.7%** |
| difference | +11.3 pts, +6.4σ, odds ratio **1.85** |

**995 latents (40% of the total, and 54% of everything that survived) were not
conveyed and survived anyway.** 198 (8%) were conveyed and lost anyway. No
mechanism for either is established here.

> For the tool: `trust_report.py` marks a latent CONFIRMED when it is in the
> activation and in the AR's reconstruction. For **54%** of those, the explanation
> did not visibly convey it. CONFIRMED means the round trip preserved it, not that
> the explanation said it.

### Label quality is not the explanation for the gap

`shared` labels score higher than `lost` labels — 0.872 vs 0.856, +5.0σ. Within
matched AUC bands:

| label AUC band | shared conveyed | lost conveyed | gap |
|---|---:|---:|---:|
| 0.756–0.82 | 38% (n=507) | 23% (n=213) | +15 |
| 0.82–0.86 | 44% (n=300) | 32% (n=105) | +12 |
| 0.86–0.90 | 43% (n=334) | 35% (n=116) | +8 |
| 0.90–1.00 | 54% (n=683) | 36% (n=187) | +18 |

Weighted within-band gap **+14.0 points** against a raw +14.5.

### By category

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

### Judge validation

| grade | on real latents | on latents that never fired | % real |
|---|---:|---:|---:|
| CLEARLY | 1043 | 376 | 74% |
| PROBABLY | 324 | 147 | 69% |
| UNCLEAR | 36 | 34 | 51% |
| NO | 1629 | 8539 | 16% |

Base rate 25%. `NO` falls below it.

```
false-positive rate    5.7%      the prompt this replaced scored 78.3%
matcher AUC            0.807     vs unrelated explanations
                       0.836     vs features that never fired
self-consistency       89.2%     across 5 explanations of one activation
```

---

## 5. Blind descriptions (qualitative)

A model given **only the latent labels** for a bucket, never the explanation.

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

Read by eye, not scored. The buckets are thin — `shared` averages 7.3 labelled
latents, `lost` 2.6, `made` 2.3 — and on 2–3 labels the describer over-reaches
about 10% of the time.

---

## Limitations

- **n = 50 activations**, one model, one layer, one corpus. The 250 pairs are
  50 × 5 sampled explanations, so effective n is nearer 50 than 250.
- **The FVE gate selected on the outcome metric.** These activations were chosen
  to score 0.73–0.77, so they are easier than average by construction. Every seed
  tried is logged. The gate has since been removed from the code.
- **~50% label coverage.** The unnamed half may behave differently.
- **SAE incompleteness.** A claim can be true with no corresponding latent;
  absence of a latent is weak evidence.
- **Surviving the round trip is not evidence the explanation carried it** — 54%
  of survivors were not conveyed (§4). Every "kept" and "confirmed" number
  measures the AR's prior plus the explanation, not the explanation alone.
  Separating them needs an AR trained independently of the AV.
- **The two sides of the latent comparison are read with unequal fidelity**
  (§1, C > A), so "made" counts are not like-for-like.
- **Nothing here checks whether a latent is true of the source text.** Both
  attempts are in [INCONCLUSIVE.md](INCONCLUSIVE.md).
- **The confabulation phenomenon is not a new finding** — the NLA paper documents
  it. What is new here is checking it against SAE features.
