# Verification log

What was actually run against real weights from this repo's layout, what broke,
and what was fixed. Written during testing rather than reconstructed afterwards.

**Why this file exists.** Everything in `src/` was moved, renamed and edited when
this repo was assembled: files renamed, two modules vendored, all imports
repointed, a new SAE path resolver added, and `trust_report.py` restructured. All
of it compiled and imported. **None of it had touched real weights from this
layout** before the session below.

**Outcome: it works, after three fixes.** Two were real bugs that would have hit
anyone cloning the repo. One was a wrong claim in the README.

---

## Machine

```
GPU        NVIDIA L40S, 46,068 MiB          driver 550.127.05
Python     3.11.10
torch      2.4.1+cu124
storage    /workspace on network FS, 130 TB free
```

The L40S was chosen deliberately to test the cheap-hardware claim. It is
advertised as 48 GB but exposes **46,068 MiB**, which turned out to matter.

---

## Setup, exactly as run

```bash
# 1. environment
mkdir -p /workspace/hf
cat > /workspace/env.sh <<'EOF'
export HF_HOME=/workspace/hf
export HF_HUB_CACHE=/workspace/hf/hub
export NLA_REPO=/workspace/natural_language_autoencoders
export HF_TOKEN=<your token>          # gemma-3-12b-it is gated
EOF
. /workspace/env.sh

# 2. dependencies. transformers<5 is required, not preference -- 5.x tokenizes
#    the CJK injection marker differently and the NLA config assertion fails.
pip install --break-system-packages -q "transformers<5" safetensors accelerate \
    pyarrow pyyaml datasets orjson huggingface_hub

# 3. the upstream repo, for nla_inference.py and the nla/ package
cd /workspace && git clone https://github.com/kitft/natural_language_autoencoders.git

# 4. models (~63 GB, ~20 min)
python3 - <<'EOF'
from huggingface_hub import snapshot_download as d
for r in ["google/gemma-3-12b-it",
          "kitft/nla-gemma3-12b-L32-av",
          "kitft/nla-gemma3-12b-L32-ar"]:
    d(r)
d("google/gemma-scope-2-12b-it", allow_patterns=[
    "resid_post_all/layer_32_width_16k_l0_small/*",
    "resid_post_all/layer_32_width_16k_l0_big/*"])
EOF
```

Total download **63 GB**; with working space, **150 GB of storage is comfortable**.

---

## What broke, and what it cost

### 1. AV + AR do not fit on a 46 GB card — the README was wrong

The README claimed 48 GB was enough. Two 12B models in bf16 are ~48 GB of
weights alone, and the card exposes 46 GB. It would have OOM'd on the hardware
the README recommended.

**Fix — restructure `trust_report.py` into three phases, one model at a time:**

```
phase 1   AV only     verbalize all activations -> explanations (text)
          del av; torch.cuda.empty_cache()
phase 2   AR only     reconstruct from those explanations
          del critic; torch.cuda.empty_cache()
phase 3   base only   label unseen features, write the closing prose
```

Nothing is lost: the AV never needs the AR's output, and explanations are just
strings. Peak drops from ~72 GB (all three) to one model plus its working memory.

### 2. The real memory peak was not the models

After the restructure, peak was still **45,481 MiB — 98.7% of the card**. Model
weights are only ~23 GB, visible in the early samples.

The culprit was `_margins(..., bs=64)` in `label_features.py`: **64 concurrent
forward passes over ~2000-token scoring prompts.** KV cache, not weights.

**Fix — `_auto_score_batch()` sizes the batch to the card:**

| card | scoring batch |
|---|---|
| ≥70 GB | 64 |
| ≥44 GB | 24 |
| ≥30 GB | 12 |
| else | 6 |

The same treatment for the generation batch (`_auto_label_batch`) saved only
1.3 GB, which is how we know scoring was the real cost.

**Measured effect:**

```
batch=64 (hardcoded)   peak 45,481 MiB   98.7% of the card
batch=24 (auto)        peak 28,941 MiB   62.8%
```

### 3. The corpus sidecar had been lost with an earlier pod

`trust_report.py` reads `<parquet>.nla_meta.yaml` to confirm the corpus is
Gemma-generated before running. The file was never pulled off a pod that has
since been terminated — the **second** time metadata was lost this way.

Reconstructed from the parquet itself, and every field is verifiable from it:
500 rows, 50 distinct `doc_id`s of the form `rollout:oasst1+lmsys:N`, `d_model`
3840, `activation_layer` 32. The corpus gate then passed.

**Lesson worth carrying:** the parquet and its sidecar travel separately and get
separated. The pipeline should write metadata *into* results, not only beside
inputs.

---

## The runs

Three runs, each a full end-to-end pass of the tool.

```bash
cd /workspace/NLA_V2 && . /workspace/env.sh
AV=$(ls -d /workspace/hf/hub/models--kitft--nla-gemma3-12b-L32-av/snapshots/*)
AR=$(ls -d /workspace/hf/hub/models--kitft--nla-gemma3-12b-L32-ar/snapshots/*)

python3 src/trust_report.py \   # now trust_tool/trust_report.py
    --parquet /workspace/acts_rollout50_L32.parquet \
    --av $AV --ar $AR \
    --labels /workspace/labels_cache.json \
    --n 4 --seed 55 --out /workspace/test_reports3
```

| run | n | seed | peak VRAM | confirmed / unverified / omitted |
|---|---|---|---|---|
| 1 | 5 | 7 | 45,481 MiB | 56% / 20% / 22% |
| 2 | 4 | 21 | 44,205 MiB | 53% / 11% / 34% |
| 3 | 4 | 55 | **28,941 MiB** | 56% / 21% / 21% |

Run 3 is the current code. All three produced coherent reports; the difference is
memory, not output.

### Sample output

```
[labels] cache has 1698 features, 854 validated
[data] 4 activations from /workspace/acts_rollout50_L32.parquet

[phase 1/3] verbalizing with the AV
  4/4 explanations; AV released

[phase 2/3] reconstructing with the AR
[NLACritic] 33 layers  d_model=3840  mse_scale=61.97
  4 reconstructions; AR released
  act 3: FVE +0.825  confirmed  20  unverified   3  omitted  10

[phase 3/3] labelling and writing
[label] batch=3 (auto, for a 45GB card)
[label] 57 features in this run have never been labelled

wrote 4 reports to /workspace/test_reports3/
  overall: confirmed 56%  unverified 21%  omitted 21%
```

---

## Checks

| check | result |
|---|---|
| `hf_paths.py` resolves the SAE from a normal HF cache | **pass** — the fix for the hardcoded `/workspace/hf` path works |
| imports with `NLA_REPO` set | **pass** — vendored `nla_av.py` / `sampling.py` resolve |
| corpus gate accepts Gemma rollouts | **pass**, after reconstructing the sidecar |
| FVE values sane | **pass** — 0.708–0.849 across 13 activations, consistent with the 0.739 mean in `RESULTS.md` |
| **no CJK in any explanation** | **pass** — the injection path survived the move. This is the loudest smoke test for the whole stack |
| on-demand labelling of unseen features | **pass** — 74, then 57 new features labelled and cached |
| cache written back and reused | **pass** — grew 1,624 → 1,698 features between runs |
| report structure and wording | **pass** — the corrected bucket wording appears in output |
| peak VRAM within a 46 GB card | **pass after fix** — 28.9 GB |

---

## Corrected hardware requirement

The README said 48 GB. **Measured: 24 GB is enough**, because the batch now
auto-sizes and no two 12B models are ever resident together.

| stage | resident | peak |
|---|---|---|
| `trust_report.py` | one 12B model at a time | **~29 GB** on a 46 GB card |
| labelling / judging / describing | one base model | ~24 GB + batch |
| `roundtrip.py` | **AV + AR together — still ~48 GB** | not yet restructured |

**`roundtrip.py` has not been given the phase treatment.** It interleaves AV and
AR inside a seed-search gate, so splitting it is not a mechanical change. On a
46 GB card it will OOM. This is the main known gap.

---

---

# Session 2 — the rest of the pipeline, on a 24 GB card

The first session tested `trust_report.py` only. This one ran **every remaining
stage** end to end from this layout, then cleaned up what the walk-through turned
up. Same machine as session 1 (L40S, 46,068 MiB).

## 4. `roundtrip.py` did not fit, and the fix was not the obvious one

`roundtrip.py` holds the AV and the AR at once — ~48 GB of weights. The first
session listed this as the main known gap.

**What it needed was not a memory trick.** The AV and AR were interleaved because
an **FVE gate** resampled seeds until the mean landed in a band, which needs both
models inside the retry loop. That gate had to go anyway: it selects activations
on the very metric being reported. Removing it made the script sequential for
free —

```
phase 1   AV only     verbalize every activation -> explanations
phase 2   AR only     reconstruct from those explanations
phase 3   SAE only    encode both ends
```

The FVE is still computed and printed, now as a **one-shot health check** that
warns and continues. Both AV/AR scripts now follow the same one-model-at-a-time
shape.

**Measured peak: 23,393 MiB.** Polled once a second across a full run, on an
otherwise idle card. Two earlier attempts at this number were thrown away: one
poller only spanned part of the run (peak 9.5 GB, below a single model's
weights — obviously not a whole run), and one spanned two overlapping jobs and
read 42.3 GB. A memory number is only as good as the window it was sampled over.

**What removing the gate exposes.** Session-2 run, no gate:

```
act 0: FVE +0.430   confirmed  5   unverified 2   omitted 5
act 1: FVE +0.854   confirmed 21   unverified 5   omitted 6
act 2: FVE +0.780   confirmed 14   unverified 2   omitted 7
```

`act 0` at 0.430 is the kind of activation the gate used to discard. The tool
handles it correctly — it reports far fewer confirmed features, which is the
honest answer for an activation the round trip barely preserved. This is why
`RESULTS.md` lists the gate as a limitation on the n=50 numbers: those were
produced by the gated code and are easier than average by construction.

## 5. The four unrun stages: all pass

Full chain on 6 activations from this layout.

| stage | result |
|---|---|
| `roundtrip.py` | **pass** — peak **23,393 MiB**, `untagged 0/6`, `CJK 0/6`, SAE (`l0_big`) `L0 136.0` / `recon cos 0.9937`, health check 0.7416 |
| `refeature.py` | **pass** — seconds, no GPU |
| `judge_explanations.py` | **pass** — 1015 judgements in 1.6 min |
| `describe_buckets.py` | **pass** — 36 summaries in 0.6 min |
| `classify_features.py` | **pass**, and see below |

**The judge revalidated itself on fresh data**, which is the check that matters:

```
false-positive rate    2.8%     (n=50 run: 5.7%; baseline prompt: 78.3%)
matcher AUC            0.796    vs unrelated explanations
                       0.814    vs non-firing features
self-consistency       92.5%
```

**`classify_features.py` refused to report a result — correctly.** Its accuracy
axis is own-text vs different-text, and at this n the control was too close:

```
judged present in its OWN text         65.8%
judged present in a DIFFERENT text     60.3%   <- control
gap                                    +5.5

!! GAP TOO SMALL. The accuracy axis is not discriminating and must
   not be reported. Everything below inherits it.
```

The n=50 run gave +30.0. The guard fired on a 6-activation smoke test and
suppressed its own headline rather than printing a number built on a control that
had stopped separating. **This is the single most reassuring thing in this log** —
the controls are load-bearing, not decoration.

Treat every session-2 number as a smoke test at n=6. `RESULTS.md` is the n=50 run.

## 6. Dead code found by walking every file

| file | found | done |
|---|---|---|
| `sampling.py` | 351 lines, **~46 used**. The rest was a standalone baseline-FVE CLI inherited from the previous project, plus the upstream `nla/` imports it alone needed | stripped to **92 lines**; the file now has no upstream dependency |
| `label_features.py`, `refeature.py` | rebuilt the SAE path as `f"layer_32_width_16k_{arg}"` while importing the `L0_SMALL`/`L0_BIG` constants meant for it — layer and width duplicated in three places | derive from the constants; `--sae` now has `choices=` |
| 7 files | unused imports (`defaultdict`, `json`, `time`, unused SAE constants) | removed |
| `roundtrip.py` `--seed` | help text still said *"starting seed for the gate"* | rewritten to say why there is no retry loop |
| `src/README.md` | still documented the FVE gate as a convention | rewritten |

Re-run after the strip: identical behaviour, 12/12 files compile, no dead imports
remain.

## 7. The walk-through found a bug in a control

Cross-checking every published number against its artefact turned up a real one.
`RESULTS.md` §2 puts `l0_small` and `l0_big` side by side, but their control
columns came out of two scripts that paired the control **differently**:

```
roundtrip.py:317   j = (i + len(V) // 2) % len(V)     halfway across the set
refeature.py:94    (k + 1) % len(F_o)                 the NEXT activation
```

Stage-0 samples ~10 positions per document and writes them adjacently, so
`k + 1` frequently landed on **another position of the same document**. That is
not a mismatched pair. It inflated the `l0_big` control to **0.040** where
`roundtrip.py` gave **0.026** — and the disagreement between two files that
should have matched is what exposed it.

`refeature.py` now uses the same half-offset. Regenerated on the same saved
vectors (no GPU, seconds):

| | before | after | `roundtrip.py` |
|---|---|---|---|
| `l0_small` control | 0.0159 | **0.0089** | — |
| `l0_big` control | 0.0396 | **0.0263** | **0.0263** ✓ |

The two independent paths now agree to four decimals. The error was
**conservative** — a too-high control makes the result look weaker, so no claim
was inflated — but a control that quietly stops being a control is exactly the
failure this repo is supposed to catch. `RESULTS.md` §2 is updated: the
separation is 17–65×, not the 20–35× previously stated.

**Not changed, and why:** `extract_activations.py` keeps its `wildchat` arm. It
looks out of place in a Gemma-only repo, but it produces the third column of the
corpus table in `RESULTS.md` §1, and the corpus check in `trust_report.py` warns
rather than refuses.

---

## What remains untested

- **`extract_activations.py`** — needs oasst1 and LMSYS downloads and ~25 minutes
  of generation; skipped in both sessions because the corpus parquet exists.
- **`matcher_bakeoff.py`** — the diagnostic that chose the judge prompt. Its
  output is already recorded in `METHODOLOGY.md`; not re-run.
- **A cold clone on a machine with no HuggingFace cache** — `hf_paths.py` was
  exercised against a populated cache and, separately, against an empty one for
  its error message, but not through a real cold start.
- **Anything at n=50 from this layout.** The published numbers come from the
  original runs; this repo has reproduced the *pipeline*, at small n, not the
  results.
