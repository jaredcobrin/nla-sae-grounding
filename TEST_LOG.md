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

python3 src/trust_report.py \
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

## What remains untested

- **`roundtrip.py`, `judge_explanations.py`, `describe_buckets.py`,
  `classify_features.py`, `refeature.py`, `extract_activations.py`** — none run
  from this layout. They import cleanly and their inputs are already in
  `results/`, but the full `run_pipeline.sh` has not been executed here.
- **`roundtrip.py` on ≤48 GB** — expected to fail, see above.
- **`extract_activations.py`** — needs oasst1 and LMSYS downloads and ~25 minutes
  of generation; skipped because the corpus parquet already exists.
- **A cold clone on a machine with no HuggingFace cache** — `hf_paths.py` was
  exercised against a populated cache and, separately, against an empty one for
  its error message, but not through a real cold start.
