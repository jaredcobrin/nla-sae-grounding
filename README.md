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

This repo does two things: it **reproduces the experiment**, and it ships a
**tool you can talk to**. Setup is shared; then pick a section.

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

Each failure, its control, and what the fix changed:
**[METHODOLOGY.md](METHODOLOGY.md)**.

---

# Setup

Needed for both sections below.

**Python ≥ 3.10.** `transformers` must be `<5` — 5.x tokenizes the CJK injection
marker differently and the NLA config assertion fails at startup.

```bash
git clone https://github.com/jaredcobrin/nla-sae-grounding.git
cd nla-sae-grounding
pip install -r requirements.txt

# the upstream NLA code, which this repo uses but does not vendor
git clone https://github.com/kitft/natural_language_autoencoders.git ../nla_upstream
export NLA_REPO=$(cd ../nla_upstream && pwd)

# PUT THE MODEL CACHE ON YOUR BIG DISK BEFORE DOWNLOADING ANYTHING.
# On a rented GPU box the boot disk is typically ~20GB while the persistent
# volume is mounted elsewhere, and these models are ~63GB. Without this the
# download dies part-way with no space left. Change the path to suit your box.
export HF_HOME=/workspace/hf
export HF_HUB_CACHE=$HF_HOME/hub

# gemma-3-12b-it is gated: accept the licence on its HuggingFace page first,
# then authenticate. A token with read access is enough.
hf auth login

# models, ~63GB and about 20 minutes.
# Use `hf`, not `huggingface-cli`: the old command prints a deprecation warning
# to STDOUT, so $(...) captures the warning along with the path and AV/AR end up
# holding two lines of junk.
export AV=$(hf download kitft/nla-gemma3-12b-L32-av)
export AR=$(hf download kitft/nla-gemma3-12b-L32-ar)
hf download google/gemma-3-12b-it

python -c "from huggingface_hub import snapshot_download as d; \
  d('google/gemma-scope-2-12b-it', allow_patterns=[\
  'resid_post_all/layer_32_width_16k_l0_small/*',\
  'resid_post_all/layer_32_width_16k_l0_big/*'])"
```

**Keep `NLA_REPO`, `HF_HOME`, `HF_HUB_CACHE`, `AV` and `AR` exported** in any
shell you run this from — the scripts read all five. Putting them in a file you
can `source` saves re-deriving `AV`/`AR` later.

**On a rented box, also set `BACKUP_REPO`.** Every stage's output is pushed to a
HuggingFace dataset as soon as it exists, so if the machine disappears you lose
one stage rather than the whole run. This is not hypothetical — a pod died two
hours into corpus generation and took the parquet with it. The pod's own disk is
not a backup; it dies with the pod.

```bash
export BACKUP_REPO=your-username/nla-run-artifacts    # created on first push
```

**This needs a WRITE token, which is not the one the models needed.** Downloading
gated models works with a read token; creating a dataset returns 403. Make one at
[huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) with the
write role and `hf auth login` with it. The script checks at startup and tells you
rather than failing silently six stages in.

Leave `BACKUP_REPO` unset and the run works exactly the same, with a warning that
nothing is being copied off the machine.

**Hardware: 150 GB of storage on the disk `HF_HOME` points at, and**

| | VRAM | |
|---|---|---|
| the experiment | **24 GB minimum, 40 GB comfortable** | see below |
| the tool, responsive | ~72 GB | all three models resident, so a turn is fast |
| the tool, `--phase` | 24 GB | loads and releases per turn; a minute or two per reply |

**24 GB is genuinely tight.** Gemma-3-12B in bf16 is **22.5 GB of weights** against
24.1 GB usable — 93.6% of the card, leaving ~800 MB for everything else. On a
4090 the default allocator fragments that and cuBLAS cannot get workspace; the
run dies with `CUBLAS_STATUS_EXECUTION_FAILED`, which is an out-of-memory that
does not say so.

`scripts/run_experiment.sh` sets `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`,
which fixes it: measured peak 23,246 MiB, flat over 16 iterations with no
fragmentation growth. **The full pipeline has only been run end to end on a 46 GB
card**, so on 24 GB expect it to work but treat it as the tested floor rather
than a comfortable one.

---

# 1. Reproduce the experiment

One command: corpus → round trip → SAE → labelling → judging → every number.

```bash
bash scripts/run_experiment.sh          # ~4-5h on one 24GB GPU
```

**One activation per conversation.** `N_DOCS` (default 120) is therefore both the
number of Gemma conversations generated and the number of *independent* samples
the statistics get. Two activations from one response share nearly all their
context — they are one cluster, not two observations — so taking several per
conversation inflates the row count while narrowing every confidence interval.
Raise it for more power:

The default of 120 is set by a power calculation, not by taste: at the effect
size measured in an earlier run, ~112 independent activations are needed before
§3's comparison can be called either way. `N_DOCS=50` runs in ~2.5h but is very
likely to come back inconclusive.

```bash
N_DOCS=50 bash scripts/run_experiment.sh     # faster, underpowered
```

Results land in `results/`:

| | |
|---|---|
| **`SUMMARY.md`** | **every number quoted in [RESULTS.md](RESULTS.md)**, as tables |
| `summary.json` | the same, machine-readable |
| `per_example.csv` | one row per (activation, explanation): FVE and cosine for all four comparisons, latent counts, Jaccard and its control |
| `LATENTS_BY_BUCKET.md` | per activation: the AV's explanation, the source text, and every labelled latent grouped shared / lost / made |

**Quote from `SUMMARY.md`, never from a hand-computed figure.** Computing them
by hand is how four errors reached an earlier write-up — a correction applied in
the wrong direction, a backwards conditional, a constant borrowed from the wrong
run, and significance pooled over non-independent pairs.

Four things to check before believing any of it, in this order:

1. **the conversation count** at the top of `SUMMARY.md`. It must equal the
   activation count. If it does not, the activations are not independent samples
   and every confidence interval below is too narrow.
2. **validated label count** in §3. ~50% is expected; much lower means the
   labeller is failing, not that the latents are hard.
3. **the judge's false-positive rate** in §5. Under ~10%. An earlier prompt
   scored 78% and made every downstream number void.
4. **the control rows** in §2. If a control sits near its matched number, that
   measurement is not discriminating and must not be quoted.

Stages, if you want to run them individually — see [`src/README.md`](src/README.md).

---

# 2. Run the trust tool

Talk to Gemma. After every turn, see what the NLA says the model was
representing, and which parts of that the SAE corroborates.

```bash
python trust_tool/app.py --av $AV --ar $AR      # then open localhost:8000
```

Add `--phase` on a card that cannot hold three 12B models at once. For the
command-line version over a stored corpus instead of a conversation:

```bash
python trust_tool/trust_report.py --parquet acts.parquet --av $AV --ar $AR --n 5
```

### What each turn reports

**1. The AV's explanation** — what the NLA says that activation contained.

**2. Three latent buckets**, each with its total and every latent that has a
validated label:

| | |
|---|---|
| **SHARED** | in the original activation **and** in the AR's reconstruction — the round trip kept these |
| **LOST** | in the original, **not** in the reconstruction |
| **MADE** | in the reconstruction only, not found in the original |

Set operations on SAE latent sets — `F_orig ∩ F_ar`, `F_orig \ F_ar`,
`F_ar \ F_orig`. **The explanation is never read** for these; it enters only
through the AR's reconstruction of it. **`MADE` means *not checked*, never
*false*** — a latent lands there when the SAE did not find it in the activation,
which can mean it is absent, or that the SAE cannot see it there.

**3. All four reconstruction comparisons** (A–D), as FVE and cosine. FVE uses the
corpus `rawvar` (0.0279) — a property of the activation distribution, which one
turn cannot produce, so it is borrowed and the page says so.

**4. Does the explanation actually say it?** Every latent genuinely in the
activation, put to the graded matcher — `CLEARLY` / `PROBABLY` / `UNCLEAR` / `NO`.
**The only model judgement on the page.** Its prompt was chosen by a measured
bake-off: 5.75% false-positive rate, against 78.3% for the plain yes/no wording it
replaced.

Sections 2 and 4 answer different questions, and the gap between them is the
point: **54% of SHARED latents are never stated in the explanation** — the AR
reconstructs them from context. A latent marked SHARED but `NO` survived on the
AR's inference, not on anything the AV wrote.

### Where the activation comes from

**The last token of your message** — the end of the conversation as it stands just
before Gemma starts generating. So the report answers: *what was the model
representing when it had finished reading you?*

On turn 3 that activation encodes turns 1 and 2, because the whole conversation is
re-fed each time. Nothing is truncated: an activation already encodes every token
before it, so a conversation simply runs until the context window fills.

### Why you converse instead of pasting text

The Gemma Scope 2 SAEs are fine-tuned on chat whose assistant turns were
**generated by Gemma itself** — from their paper, *"we take open-source datasets
of user prompts and generate responses from the corresponding Gemma models."*
Pasted text is off that distribution: on FineWeb this same pipeline measured a
**7-point** effect where these rollouts gave **25**. Having Gemma write the
conversation keeps the input in-distribution. You still choose the subject.

**Two caveats.** The position is a turn boundary, where the experiment samples
*inside* a generated response — same "activation at the end of this context"
structure, different region, and the numbers above were not measured at turn
boundaries. And past turn 2 you are in a multi-turn context shape the experiment
never covered.

---

## Scope, honestly

- **n = 50 activations from 50 separate conversations**, one model, one
  layer, one corpus. `SUMMARY.md` states the conversation count, and it
  must equal the activation count or the intervals are too narrow.
- **These activations were selected on the outcome metric** — a gate chose ones
  scoring FVE 0.73–0.77, so they are easier than average. Every seed is logged and
  the gate has been removed from the code.
- **Gemma only.** The tool warns on other corpora.
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
README.md           this file — findings, setup, and how to run both halves
RESULTS.md          every number, with its control and its caveats
METHODOLOGY.md      how each measurement works, and what broke on the way there
INCONCLUSIVE.md     experiments that produced numbers and failed their controls
FUTURE_WORK.md      what the saved vectors make answerable next
TEST_LOG.md         what was run against real weights, and what broke
src/                the experiment, one file per stage (see src/README.md)
trust_tool/         the chat tool: app.py, session.py, trust_report.py
scripts/            run_experiment.sh — reproduce everything
results/            every artefact the numbers come from (see results/README.md)
```
