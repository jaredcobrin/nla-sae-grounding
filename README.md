# Can you trust what a Natural Language Autoencoder says about an activation?

A natural language autoencoder (NLA) reads one activation from a language model
and writes a sentence or two about what it contains. The
[NLA paper](https://transformer-circuits.pub/2026/nla/) names the obvious worry
in its own limitations:

> **Excessive expressivity:** Because the AV is a full language model, it has the
> capacity to make additional inferences beyond what is stored in an activation.

The paper's own metric cannot settle this. During RL the reconstructor (AR) is
trained on the verbalizer's (AV's) own rollouts, so it is not an independent
judge of whether the AV invented something — the pair can agree on a code that
neither the activation nor the language supports. A **sparse autoencoder reads
the activation directly**, and is independent.

This repo does that check, and ships a tool that runs it on demand.

---

## What was measured

These are measurements, not explanations of them. Where a reading is tempting but
not established, that is said rather than implied.

**1. The NLA round trip reconstructs an activation better than this SAE does.**

| | FVE |
|---|---|
| SAE reconstruction vs original | **0.587** |
| **AV → text → AR** reconstruction vs original | **0.739** |

50 Gemma-3-12B-IT layer-32 activations, on the corpus the SAE was *itself
fine-tuned on*. The ordering held on all three corpora tried in an earlier n=10
pass. Both are lossy compressions of the same vector, but they were built for
different jobs — sparse decomposition versus reconstruction — so this is a
statement about reconstruction, not about English being a better representation
than a feature basis.

**2. The round trip preserves most features, far above its control.**

**Tested on 50 activations × 5 explanations = 250 (activation, explanation)
pairs**, the same vectors read by both SAEs — only the dictionary changes.

| | `l0_small` (~21 features/activation) | | | `l0_big` (~120 features/activation) | | |
|---|---:|---:|---:|---:|---:|---:|
| | **total** | **mean/pair** | **share** | **total** | **mean/pair** | **share** |
| **shared** | 3,529 | 14.1 | 56.5% | 17,125 | 68.5 | 44.9% |
| **lost** | 1,441 | 5.8 | 23.1% | 12,850 | 51.4 | 33.7% |
| **made** | 1,280 | 5.1 | 20.5% | 8,202 | 32.8 | 21.5% |
| *total* | *6,250* | *25.0* | | *38,177* | *152.7* | |

| | `l0_small` | `l0_big` |
|---|---:|---:|
| **kept** = shared/(shared+lost) | **71.0%** | **57.1%** |
| Jaccard vs mismatched control | 0.576 vs 0.009 — **65×** | 0.450 vs 0.026 — **17×** |

Integer set arithmetic on SAE feature IDs. No judge, no labels, nothing to
calibrate — which is why this is the most robust number here.

The 14-point difference in kept rate is close to a straight trade between
`shared` and `lost`. **The `made` share barely moves — 20.5% vs 21.5%** — so
about a fifth of what the AR produces is absent from the original under either
dictionary. These are separately trained dictionaries, not two settings of a
granularity knob, so nothing here supports reading the gap as "coarse features
survive, fine-grained ones don't".

**3. The main finding: features the round trip keeps are conveyed by the
explanation more often than features it loses or adds.**

| bucket | features | conveyed by the explanation |
|---|---|---|
| **shared** — in the activation *and* the reconstruction | 1840 | **46%** |
| **made** — only in the reconstruction | 562 | 35% |
| **lost** — in the activation, gone from the reconstruction | 630 | 31% |

`shared` is **8.1×** the judge's measured 5.7% false-positive floor, and beats
`made` by +4.6σ and `lost` by +6.4σ. **`made` vs `lost` is not distinguishable**
(+3.6 points, 95% CI [−1.7, +9.0]).

**This is a correlation between an SAE's reading of an activation and text an
independent model wrote about it.** What it implies about the AV's behaviour is
not settled by this data — see [RESULTS.md §4](RESULTS.md), which also shows that
**54% of everything the round trip preserves was never visibly conveyed by the
explanation**, and offers no mechanism for it.

Full numbers, controls and caveats: **[RESULTS.md](RESULTS.md)**.
Two experiments that produced good-looking numbers and **did not meet the bar**
are written up in **[INCONCLUSIVE.md](INCONCLUSIVE.md)**.

---

## The tool

`src/trust_report.py` takes an activation and returns what its explanation is
actually evidenced by:

| verdict | meaning |
|---|---|
| **CONFIRMED** | in the real activation, **and the AR recovers it** from the explanation |
| **UNVERIFIED** | **the AR produces it** from the explanation, but it is not in the activation here |
| **OMITTED** | in the real activation, but **the AR does not recover it** |

These are set operations on SAE feature sets — `F_orig ∩ F_ar`, `F_ar \ F_orig`,
`F_orig \ F_ar`, where `F_ar = SAE(AR(explanation))`. **The explanation text is
never read.** It enters only through the AR's reconstruction of it, and that
distinction matters: the AR trains on the AV's own rollouts and demonstrably
fills in context the explanation never stated (result 4). Saying "the explanation
implies X" would attribute to the text what belongs to the AR.

For a check that *does* read the explanation, `src/judge_explanations.py` shows
the text to a model and asks whether it covers each feature — that is where the
46% / 31% figures in result 3 come from.

**UNVERIFIED does not mean false** — see result 4. It means *not checked*.

Worked examples: [`results/example_reports/`](results/example_reports/).

---

## Why you should believe any of this

Every measurement in this repo is reported **against its own null**, because
three separate designs here produced confident, plausible, wrong numbers and each
was caught only by a control:

- an auto-interp scorer where a **deliberately wrong label scored 0.557 against a
  correct label's 0.604** — near-blind, and its "33% of labels are reliable" meant
  nothing
- a claim-matcher that judged **78% of features present in activations they never
  fired in**
- a "90% of claims survive" figure that was **49%** once the bucketing rule stopped
  counting a claim as surviving when most of its support was destroyed

The methodology section documents each failure, what the control was, and what
the fix changed. **[METHODOLOGY.md](METHODOLOGY.md)**

---

## Running it

**Requires Python ≥ 3.10** — the upstream `nla/` package uses `str | None`
syntax. Also requires a clone of
[`kitft/natural_language_autoencoders`](https://github.com/kitft/natural_language_autoencoders);
point `NLA_REPO` at it.

```bash
pip install -r requirements.txt
export NLA_REPO=/path/to/natural_language_autoencoders

# fetch the two SAE variants (both are used, for different questions)
python -c "from huggingface_hub import snapshot_download as d; \
  d('google/gemma-scope-2-12b-it', allow_patterns=[\
  'resid_post_all/layer_32_width_16k_l0_small/*',\
  'resid_post_all/layer_32_width_16k_l0_big/*'])"

# 1. build a corpus: oasst1 + LMSYS prompts, responses generated by Gemma itself
python src/extract_activations.py --arm rollout --n-docs 50 --out acts.parquet

# 2. round trip + SAE on both ends
python src/roundtrip.py --av <av> --ar <ar> --parquet acts.parquet --n 50 --out-dir results/

# 3-5. labels, judging, descriptions
bash scripts/run_pipeline.sh          # everything, ~2.5h on one 80GB GPU

# the tool
python src/trust_report.py --parquet acts.parquet --av <av> --ar <ar> \
    --labels results/feature_labels.json --n 5 --out my_reports/
```

Models: `google/gemma-3-12b-it`, `kitft/nla-gemma3-12b-L32-{av,ar}`,
`google/gemma-scope-2-12b-it`.

### Hardware

**24 GB VRAM, 150 GB storage** — measured, not estimated. See
[TEST_LOG.md](TEST_LOG.md) for the run this comes from.

Three 12B models are involved but **never more than one at a time**:
`trust_report.py` runs in phases, releasing the AV before loading the AR and the
AR before loading the writer. Batch sizes auto-size to the card.

| stage | resident | measured peak |
|---|---|---|
| `roundtrip.py` | one model at a time | **23.4 GB** |
| `trust_report.py` | one model at a time | **23.7 GB** |
| labelling / judging / describing / classifying | one base model | ~24 GB |

Two things testing changed:

- **the memory peak was batch, not weights.** Model weights are ~23 GB, but a
  hardcoded scoring batch of 64 over ~2000-token prompts pushed peak to 98.7% of
  a 46 GB card. Batches now auto-size to the device.
- **no two 12B models are ever resident together.** Both `roundtrip.py` and
  `trust_report.py` run in phases, releasing the AV before loading the AR. This
  needed the FVE gate to go — see [METHODOLOGY.md](METHODOLOGY.md) — which was
  worth doing on its own merits.

`transformers` must be `<5`: 5.x tokenizes the CJK injection marker differently
and the NLA config assertion fails at startup.

---

## Scope, honestly

- **n = 50 activations**, one model, one layer. Every number here is from that.
- **Gemma only.** The SAE was fine-tuned on Gemma-generated chat; on FineWeb the
  same pipeline measured a 7-point effect where Gemma rollouts gave 25. The tool
  refuses other corpora unless overridden.
- **~50% of features have a validated label.** The rest are counted but unnamed.
  That is the validation bar working, not a bug.
- **The SAE is not complete.** A claim can be true and have no corresponding
  feature. Absence of a feature is weak evidence.
- **The confabulation finding is not new.** The NLA paper already documents
  explanations with "verifiably false claims about the context" that are
  "typically thematically faithful". What is new here is checking whether those
  claims correspond to SAE features, and how much of an explanation is evidenced.
- The prior-art check was **not exhaustive**.

---

## Credit — what is mine and what is not

**The NLA itself is not mine.** The verbalizer, the reconstructor, the injection
mechanism and the training code are
[`kitft/natural_language_autoencoders`](https://github.com/kitft/natural_language_autoencoders)
(Copyright 2026 Anthropic PBC, Apache-2.0), the code companion to
[the NLA paper](https://transformer-circuits.pub/2026/nla/) by Fraser-Taliente,
Kantamneni, Ong et al. The SAE is Google's Gemma Scope 2. I wrote none of that.

| | |
|---|---|
| **Not redistributed here** | `nla/` and `nla_inference.py` — required at runtime, but you clone them yourself and point `NLA_REPO` at them |
| **Derived and modified** | `src/nla_av.py` — calls upstream's injection primitives and follows its recipe; adds the Gemma embed-scale fix. Change notice in its docstring, per Apache-2.0 §4(b) |
| **Mine** | the other 11 files in `src/`, everything in `results/` and `scripts/`, and all the documentation |

**The finding that NLA explanations confabulate is also not mine** — the paper
documents it. What is mine is the question of whether those claims correspond to
active SAE features, the pipeline that measures it, and the controls.

This repo is Apache-2.0 to match upstream. Full breakdown in [NOTICE](NOTICE).

---

## Layout

```
README.md          this file
LICENSE            Apache-2.0
NOTICE             attribution — what is upstream, what is derived, what is mine
RESULTS.md         every number, with its control and its caveats
INCONCLUSIVE.md    experiments that produced numbers and did not meet the bar
FUTURE_WORK.md     what the saved vectors make answerable next
METHODOLOGY.md     how each measurement works, and what broke on the way there
TEST_LOG.md        what was actually run against real weights, and what broke
src/               the pipeline, one file per stage (see src/README.md)
scripts/           run_pipeline.sh — the documented order
results/           every artefact the numbers come from (see results/README.md)
```

Every script's docstring explains what it does, what went wrong in earlier
versions, and why it is built the way it is.
