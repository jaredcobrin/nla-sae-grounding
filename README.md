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

**3. The AV conveys about 43% of what is in the activation, and what it mentions
is what survives.**

| | features | clearly conveyed by the explanation |
|---|---|---|
| survived the round trip | 1840 | **46%** |
| destroyed by the round trip | 630 | **31%** |

The explanation is the only channel between AV and AR, so a feature it never
mentions has nothing to be rebuilt from.

**4. "Invented" features are mostly not invented.** Of features present in the
reconstruction but absent from the original activation, **65–68% are genuinely in
the source document** — just not at the sampled token position (control: 25–30%).
The AR reconstructs *document-level context*, not *position-specific state*.

**5. A negative result that kills a plausible story.** Confirmed, lost and
invented features have **statistically identical composition** across
grammar/content × generic/specific (every difference < 1.3σ). The round trip does
not preferentially destroy "specifics" or preserve "themes". It is indiscriminate
with respect to feature type.

Full numbers, controls and caveats: **[RESULTS.md](RESULTS.md)**.

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

Three 12B models are involved, but never more than two at once — `trust_report.py`
releases the AV and AR before loading the writer.

| stage | models resident | VRAM |
|---|---|---|
| `roundtrip.py` | AV + AR | **~48 GB** |
| `trust_report.py` | AV + AR, then writer alone | **~48 GB** peak |
| everything else | one base model | **~24 GB** |

So **48 GB is the binding requirement** — an A6000, L40S or A40 is enough; an
80 GB A100 is not needed. If you only want to run labelling, judging or
descriptions against already-computed feature sets, 24 GB suffices.

**Storage: ~150 GB.** Roughly 24 GB each for the base model, AV and AR; ~2.6 GB
for the two SAE variants (weights plus their exemplar stores); the rest is the
HuggingFace datasets cache for oasst1/LMSYS and working space.

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

## Layout

```
README.md          this file
METHODOLOGY.md     how each measurement works, and what broke on the way there
RESULTS.md         every number, with its control and its caveats
src/               the pipeline, one file per stage (see src/README.md)
scripts/           run_pipeline.sh — the documented order
results/           every artefact the numbers come from (see results/README.md)
```

Every script's docstring explains what it does, what went wrong in earlier
versions, and why it is built the way it is.
