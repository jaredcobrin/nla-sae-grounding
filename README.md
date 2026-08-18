# Does the AV's final paragraph carry more meaning, or just reconstruct better?

A natural language autoencoder (NLA) reads one activation out of a language
model and writes a sentence or two describing it. The
[NLA paper](https://transformer-circuits.pub/2026/nla/) names the obvious worry
in its own limitations: because the verbalizer (AV) is a full language model, it
can invent plausible detail beyond what the activation actually contains. Its own
metric, FVE, cannot settle this — during RL the reconstructor (AR) trains on the
AV's own rollouts, so the two can agree on a code that neither the activation nor
the language independently supports.

loops (LessWrong, 15 May 2026, on this same checkpoint) found that the AV writes
to a stable three-part shape, and that the final paragraph — describing what the
final token is doing — carries most of the round trip's FVE: removing it costs
far more reconstruction error than removing the first two parts. That is a claim
about FVE. It leaves open the question this repo tests: **is the final
paragraph's higher FVE because it says more that is actually true of the
activation, or only because it is easier for the AR to reconstruct from?**

A **sparse autoencoder**, trained on Gemma independently of the NLA and never
seeing its output, is used as a witness neither the AV nor the AR can influence.

## Methodology, briefly

- **Gemma-3-12B-IT, layer 32**, 200 activations from 200 distinct conversations,
  one explanation each. Full steps: [METHODOLOGY.md](METHODOLOGY.md).
- Each explanation is cut once into `full`, `no_final` (parts 1–2), and
  `final_only` (part 3) — a paired comparison, since it is one explanation split
  three ways, not three separately generated ones.
- The SAE encodes both the original activation and the AR's reconstruction of
  each variant, giving **shared** / **lost** / **made** latent sets with no text
  or judge involved.
- An LLM judge separately checks whether the explanation's *text* actually
  states each latent the SAE found — validated against a wrong-label null and a
  false-positive null, both reported alongside every rate.

## Result

| | full explanation | first two paragraphs | final paragraph |
|---|---:|---:|---:|
| **1. FVE** | +0.691 | +0.268 (39% of full) | +0.582 (**84%** of full) |
| **2. latents recovered** — SAE vs SAE, no text | 70.2% | 30.1% (43% of full) | 58.9% (**84%** of full) |
| **3. grounded, of labeled** F_orig latents | 43.0% | 19.6% (46% of full) | 41.6% (**97%** of full) |
| **4. grounded, of ALL** F_orig latents | 19.5% | 8.9% (46% of full) | 18.9% (**97%** of full) |

Rows 1–2 need no judge or labels; rows 3–4 do. Full numbers, controls, and every
caveat: **[RESULTS.md](RESULTS.md)**.

## What this shows

Two measurements obtained independently of each other — raw SAE latent overlap
with no text involved, and an LLM judge reading text against labelled latents —
agree: the final paragraph keeps ~84% of the round trip's raw signal and ~97% of
what a reader can confirm the explanation actually states. This supports loops's
finding rather than merely restating it: the final paragraph's higher FVE
corresponds to more of the activation's real content being conveyed, not only to
text the AR happens to rebuild well. The correspondence holds **between the parts
of the explanation** and does not hold **between individual activations** — an
activation the AR reconstructs well is no more likely to be one whose latents the
explanation actually names (r ≈ 0, n ≈ 190, see [RESULTS.md](RESULTS.md)). FVE
predicts *where* the content is, not *which activations* got it right.

The first two paragraphs carry comparatively little: 39% of the FVE and well
under half of the grounded content, from over half the tokens. If that holds
beyond this checkpoint, it points at the training data — the warm-start format
that produces this three-part shape asks for a document description the
activation apparently does not encode as well as the final-token analysis does.
Restructuring what the pretraining data asks the AV to write, so it spends more
of its tokens on the part shown to carry the signal, is the natural next
experiment: [FUTURE_WORK.md](FUTURE_WORK.md).

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
bash scripts/run_experiment.sh          # ~5h, mostly corpus generation
```

**One activation per conversation, one explanation per activation.** `N_DOCS`
(default 200) is therefore both the number of Gemma conversations generated and
the number of *independent* samples the statistics get — nothing is nested
inside anything else. Two activations from one response share nearly all their
context, and two explanations of one activation turn out to be ~97% the same
measurement (ICC 0.97 on FVE; the decomposition is in `scripts/run_experiment.sh`
under `RUNS`). Either kind of nesting inflates the row count while narrowing
every confidence interval.

The default of 200 comes from a power calculation, not taste: at the effect size
measured in an earlier run, ~112 independent activations are the minimum before
§3's comparison can be called either way, and 200 leaves margin for activations
that drop out of a bucket comparison by having no latents in one of the buckets.
`N_DOCS=50` runs in ~1.5h but is very likely to come back inconclusive.

```bash
N_DOCS=50 bash scripts/run_experiment.sh     # faster, underpowered
```

**Where the conversations come from.** By default they are sampled from Gemma
Scope's own corpus — the `tokens` array inside the `examples.safetensors` the
setup step already downloads, holding 236,783 finished Gemma chats. It is the
same corpus the SAE's published feature exemplars point into, so it is Gemma
Scope's actual data rather than our reconstruction of their recipe, and the text
is identical for anyone re-running.

The alternative regenerates that corpus locally — sampling oasst1 + LMSYS
prompts and having Gemma write each response — which is ~400 decode steps per
conversation and adds roughly three hours:

```bash
ARM=rollout bash scripts/run_experiment.sh   # regenerate instead of sampling
```

Both write a parquet named for the arm, so switching cannot silently reuse the
other one's activations. `METHODOLOGY.md` §2 records the one caveat: the shipped
corpus may be in-sample for the SAE, which makes finding 1 harder to win rather
than easier.

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
bake-off: a 4.6% false-positive rate, against 78.3% for the plain yes/no wording
it replaced.

Sections 2 and 4 answer different questions, and the gap between them is the
point: **58% of SHARED latents are never stated in the explanation** — the AR
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

- **n = 200 activations from 200 separate conversations**, one model, one
  layer, one corpus. `SUMMARY.md` states the conversation count, and it
  must equal the activation count or the intervals are too narrow.
- **An earlier run's activations were selected on the outcome metric** by a gate
  scoring FVE 0.73–0.77. That gate is removed; this run's activations are
  ungated (`gate_log` is a one-shot health check, not a filter), but the FVE
  distribution should still be read in full rather than as a single mean —
  `results/SUMMARY.md` §1 prints the min/median/max.
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
README.md           this file — the question, the result, setup, how to run
RESULTS.md          the full result set, with every control and caveat
METHODOLOGY.md      the steps, in order, that produce those numbers
FUTURE_WORK.md      three follow-up directions, with prior art
NOTICE               what is upstream vs. original, per Apache-2.0

src/                the pipeline, one file per stage (see src/README.md)
  extract_activations.py    stage 1 — build the corpus
  roundtrip.py               stage 2 — AV -> explanation -> AR, + the paragraph split
  refeature.py               stage 3 — re-encode under the other SAE
  label_features.py         stage 4 — auto-interp + validation
  judge_explanations.py     stage 5 — does the text convey each latent?
  summarize_results.py      stage 6 — every number -> summary.json + SUMMARY.md
  explanation_parts.py      the full/no_final/final_only split, standalone
  example_reports.py        six worked examples, no GPU
  nla_av.py, sampling.py, hf_paths.py    vendored/modified upstream code

trust_tool/         the chat tool — app.py, session.py, trust_report.py
scripts/            run_experiment.sh — reproduce everything, stages 1-6
results/            every artefact the numbers come from (see results/README.md)
  SUMMARY.md               every number in RESULTS.md, as tables
  LATENTS_BY_BUCKET.md     all 200 activations, latent by latent
  example_reports/         six activations followed end to end
```
