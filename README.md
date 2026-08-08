# Can you trust what a Natural Language Autoencoder says about an activation?

A natural language autoencoder (NLA) reads one activation out of a language model
and writes a sentence or two about what it contains. The
[NLA paper](https://transformer-circuits.pub/2026/nla/) names the obvious worry in
its own limitations:

> **Excessive expressivity:** Because the AV is a full language model, it has the
> capacity to make additional inferences beyond what is stored in an activation.

The paper's own metric cannot settle it. During RL the reconstructor (AR) trains
on the verbalizer's (AV's) own rollouts, so it is not an independent judge of
whether the AV invented something — the pair can agree on a code neither the
activation nor the language supports. A **sparse autoencoder reads the activation
directly**, and is independent.

---

## This repo does two things

**1. It reproduces the experiment.** One command runs corpus → round trip → SAE →
labelling → judging → statistics, and writes every number in
[RESULTS.md](RESULTS.md) to a file.

```bash
bash scripts/run_experiment.sh          # ~2.5h, one 24GB GPU
```

**2. It ships a tool you can talk to.** [`trust_tool/`](trust_tool/) opens a chat
window: you converse with Gemma, and after every turn you see what the NLA says
the model was representing — and which parts of that the SAE corroborates.

```bash
python trust_tool/app.py --av $AV --ar $AR      # then open localhost:8000
```

| verdict | meaning |
|---|---|
| **CONFIRMED** | in the activation, **and** the AR recovers it from the explanation |
| **UNVERIFIED** | the AR produces it from the explanation; the SAE did not find it in the activation |
| **OMITTED** | in the activation; the AR does not recover it |

These are set operations on SAE latent sets, not readings of the text —
`F_orig ∩ F_ar`, `F_ar \ F_orig`, `F_orig \ F_ar`. **The explanation is never
read**; it enters only through the AR's reconstruction of it. **UNVERIFIED means
*not checked*, never *false*.**

**You converse rather than paste text on purpose.** The SAE is fine-tuned on chat
whose assistant turns Gemma wrote itself, so having Gemma write the conversation
keeps the input in-distribution — on FineWeb the same pipeline measured a 7-point
effect where these rollouts gave 25. You still choose the subject.

Details and caveats: [`trust_tool/README.md`](trust_tool/README.md). Worked
command-line examples: [`results/example_reports/`](results/example_reports/).

---

## The findings

**1. The NLA round trip reconstructs an activation better than the SAE does.**

| | FVE |
|---|---|
| SAE reconstruction vs original | 0.587 |
| **AV → text → AR** vs original | **0.739** |

Measured on the corpus the SAE was itself fine-tuned on, using the stronger of
its two variants — the conservative setting for this comparison.

**2. Latent overlap survives the round trip, far above chance.**

| Jaccard | `l0_small` | `l0_big` |
|---|---:|---:|
| rebuild vs its own activation | 0.576 | 0.450 |
| rebuild vs an **unrelated** activation | 0.009 | 0.026 |
| ratio | **65×** | **17×** |

Integer set arithmetic on latent IDs. No judge, no labels, nothing to calibrate —
the most robust number here.

**3. The latents that survive are the ones the explanation talks about.**

| bucket | latents | mentioned in the explanation |
|---|---:|---:|
| **shared** | 1,840 | **45.9%** |
| made | 562 | 35.1% |
| lost | 630 | 31.4% |

`shared` is **8.0×** the judge's measured 5.75% false-positive rate. Compared per
activation across the 50 (not by pooling the pairs, which would overstate
confidence ~2.5×), `shared` beats `lost` by **+11.2 points** (t = 2.56) and `made`
by **+12.6** (t = 2.42). `made` vs `lost` is not distinguishable.

**This is a correlation between an SAE's reading of an activation and text an
independent model wrote about it.** What it implies about the AV is not settled
here.

Full numbers and caveats: **[RESULTS.md](RESULTS.md)** · How it was measured:
**[METHODOLOGY.md](METHODOLOGY.md)** · Experiments that failed their own controls:
**[INCONCLUSIVE.md](INCONCLUSIVE.md)**

---

## Why you should believe any of it

Every measurement is reported **against its own null**, because three designs here
produced confident, plausible, wrong numbers, and each was caught only by a
control:

- an auto-interp scorer where a **deliberately wrong label scored 0.557 against a
  correct label's 0.604** — near-blind, and its "33% of labels are reliable" meant
  nothing
- a matcher that judged **78% of latents present in activations they never fired
  in**
- a "90% of claims survive" figure that was **49%** once the bucketing rule
  stopped counting a claim as surviving when most of its support was destroyed

Each failure, its control, and what the fix changed: **[METHODOLOGY.md](METHODOLOGY.md)**.

---

## Setup

**Python ≥ 3.10.** Also needs a clone of
[`kitft/natural_language_autoencoders`](https://github.com/kitft/natural_language_autoencoders)
— point `NLA_REPO` at it. `transformers` must be `<5`; 5.x tokenizes the CJK
injection marker differently and the NLA config assertion fails at startup.

```bash
pip install -r requirements.txt
export NLA_REPO=/path/to/natural_language_autoencoders
export AV=$(huggingface-cli download kitft/nla-gemma3-12b-L32-av)
export AR=$(huggingface-cli download kitft/nla-gemma3-12b-L32-ar)

python -c "from huggingface_hub import snapshot_download as d; \
  d('google/gemma-scope-2-12b-it', allow_patterns=[\
  'resid_post_all/layer_32_width_16k_l0_small/*',\
  'resid_post_all/layer_32_width_16k_l0_big/*'])"
```

Models: `google/gemma-3-12b-it` (gated), `kitft/nla-gemma3-12b-L32-{av,ar}`,
`google/gemma-scope-2-12b-it`. **150 GB storage.**

| | VRAM | |
|---|---|---|
| the experiment (`run_experiment.sh`) | **24 GB** | measured ([TEST_LOG.md](TEST_LOG.md)) — every stage loads, uses and releases one 12B model at a time |
| the chat tool, responsive | ~72 GB | all three models resident, so a turn is fast |
| the chat tool, `--phase` | **24 GB** | loads and releases per turn; costs a minute or two per reply |

---

## Scope, honestly

- **n = 50 activations**, one model, one layer, one corpus.
- **These activations were selected on the outcome metric** — a gate chose ones
  scoring FVE 0.73–0.77, so they are easier than average. Every seed is logged and
  the gate has been removed from the code.
- **Gemma only.** On FineWeb, out-of-distribution for the SAE, the same pipeline
  measured a 7-point effect where these rollouts gave 25. The tool warns on other
  corpora.
- **~50% of latents have a validated label.** The rest are counted but unnamed.
- **The SAE is incomplete** — a claim can be true with no latent to match it, so
  absence is weak evidence.
- **The confabulation finding is not new.** The NLA paper documents it. What is
  new here is checking it against SAE latents.
- The prior-art check was **not exhaustive**.

---

## Credit

**The NLA is not mine.** The verbalizer, reconstructor, injection mechanism and
training code are
[`kitft/natural_language_autoencoders`](https://github.com/kitft/natural_language_autoencoders)
(Copyright 2026 Anthropic PBC, Apache-2.0), the code companion to the NLA paper by
Fraser-Taliente, Kantamneni, Ong et al. The SAE is Google's Gemma Scope 2.

| | |
|---|---|
| **Not redistributed** | `nla/` and `nla_inference.py` — you clone them and point `NLA_REPO` at them |
| **Derived and modified** | `src/nla_av.py` — calls upstream's injection primitives; adds the Gemma embed-scale fix. Change notice in its docstring, per Apache-2.0 §4(b) |
| **Mine** | the rest of `src/`, all of `trust_tool/`, `results/`, `scripts/`, and the documentation |

**The finding that NLA explanations confabulate is also not mine** — the paper
documents it. Mine is the question of whether those claims correspond to active
SAE latents, the pipeline that measures it, and the controls.

Apache-2.0, to match upstream. Full breakdown in [NOTICE](NOTICE).

---

## Layout

```
RESULTS.md          every number, with its control and its caveats
METHODOLOGY.md      how each measurement works, and what broke on the way there
INCONCLUSIVE.md     experiments that produced numbers and failed their controls
FUTURE_WORK.md      what the saved vectors make answerable next
TEST_LOG.md         what was run against real weights, and what broke
src/                the experiment, one file per stage (see src/README.md)
trust_tool/         the chat tool (see trust_tool/README.md)
scripts/            run_experiment.sh — reproduce everything
results/            every artefact the numbers come from (see results/README.md)
```
