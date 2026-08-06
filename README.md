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

## The headline results

**1. Two sentences of English preserve an activation better than a 16,384-feature
sparse autoencoder does.**

| | FVE |
|---|---|
| SAE reconstruction vs original | **0.587** |
| **AV → text → AR** reconstruction vs original | **0.739** |

Measured on 50 Gemma-3-12B-IT layer-32 activations, on the corpus the SAE was
*itself fine-tuned on*. Reproduced across three corpora (FineWeb, Gemma rollouts,
WildChat) in an earlier n=10 pass.

**2. The round trip keeps the gist and drops the detail.**

| SAE | features per activation | kept through the round trip |
|---|---|---|
| `l0_small` | ~21 (coarse) | **71%** |
| `l0_big` | ~120 (fine-grained) | **57%** |

**3. The AV's explanation tracks what is really in the activation — it is not
free-associating.**

| bucket | features | conveyed by the explanation | |
|---|---|---|---|
| **shared** — in the activation *and* the reconstruction | 1840 | **46%** | **8.1×** the judge's false-positive floor |
| **lost** — in the activation, gone from the reconstruction | 630 | **31%** | shared beats this by **+6.4σ** |
| **made** — only in the reconstruction | 562 | **35%** | shared beats this by **+4.6σ** |

If the AV were free-associating, features really in the activation would be
"conveyed" at about the judge's 5.7% error rate and all three buckets would look
alike. They do not. The judge behind this was chosen by a measured bake-off; the
prompt it replaced had a 78.3% false-positive rate.

**But being mentioned is not what makes a feature survive.** Of features genuinely
in the activation, being conveyed raises survival from **69.7% to 81.0%** — real
(+6.4σ) but far from decisive. **54% of everything that survives the round trip
was never visibly conveyed by the explanation at all.** The AR reconstructs it
from the passage's general subject instead — pattern completion from a model
trained on the AV's own rollouts. That is the confound this project exists to
expose, and [RESULTS.md §4](RESULTS.md) puts a size on it.

**4. The same thing, with no language model anywhere in the measurement.**
Feature overlap between the original activation and the reconstruction is
**65× its mismatched control** (`l0_small`; 17× at `l0_big`). This is integer set
arithmetic on SAE feature IDs — no judge, no labels, nothing to calibrate.

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
TEST_LOG.md        what was actually run against real weights, and what broke
METHODOLOGY.md     how each measurement works, and what broke on the way there
RESULTS.md         every number, with its control and its caveats
src/               the pipeline, one file per stage (see src/README.md)
scripts/           run_pipeline.sh — the documented order
results/           every artefact the numbers come from (see results/README.md)
```

Every script's docstring explains what it does, what went wrong in earlier
versions, and why it is built the way it is.
