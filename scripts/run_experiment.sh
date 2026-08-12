#!/usr/bin/env bash
# Reproduce the whole experiment: corpus -> results -> every reported number.
#
#   export NLA_REPO=/path/to/natural_language_autoencoders
#   export AV=... AR=...          # the nla-gemma3-12b-L32-{av,ar} snapshot dirs
#   bash scripts/run_experiment.sh
#
# ~5h on one GPU at the default N_DOCS=200, most of it stage 1: generating the
# corpus is now the dominant cost, since dropping to one explanation per
# activation cut stages 2 and 4 to a third. Each stage writes its output before
# the next starts, so a failure part-way does not cost the stages already done,
# and re-running skips the corpus if the parquet exists.
#
# The last stage writes results/summary.json and results/SUMMARY.md, which
# contain every number quoted in RESULTS.md. Nothing else needs to be computed
# by hand -- that is how four errors reached an earlier write-up.
set -euo pipefail

: "${NLA_REPO:?set NLA_REPO to a clone of kitft/natural_language_autoencoders}"
AV="${AV:?set AV to the nla-gemma3-12b-L32-av snapshot directory}"
AR="${AR:?set AR to the nla-gemma3-12b-L32-ar snapshot directory}"
# ONE ACTIVATION PER CONVERSATION, and (see RUNS below) one run per activation,
# so N_DOCS is the number of independent samples full stop. Two activations from
# one Gemma response share nearly all their context and are one cluster, not two
# observations -- an earlier run drew 50 activations from only 30 conversations
# and every interval was too narrow.
N_DOCS="${N_DOCS:-200}"
# RUNS = how many times each activation is pushed through AV -> AR. This was 5,
# on the assumption that T=1 sampling made the explanations vary enough to need
# averaging. Measured, on a completed 50-activation run, by splitting
# between-activation from within-activation variance:
#
#   quantity          ICC      within-var   between-var
#   n_shared          0.980      1.24          60.7
#   FVE               0.974      0.00185        0.0706
#   Jaccard           0.892      0.00043        0.0035
#   grounding rate    0.655      0.01164        0.0221
#
# ICC ~0.9 means the 5 explanations of one activation say substantially the same
# thing. Runs are nested inside an activation, so they are not independent
# samples and the extra ones mostly re-measure what is already known.
# Conversations ARE independent. At a fixed budget the trade is one-sided:
#
#   plan              SE(FVE)   SE(grounding)   AV+AR passes   judge units
#   120 conv x 5      0.0243       0.0143           600            600
#   200 conv x 1      0.0190       0.0130           200            200
#
# Tighter on both, and a third of the round-trip and judging cost. The only
# thing R=1 gives up is the ICC estimate above -- which does not need redoing,
# because it is already measured and recorded here.
RUNS="${RUNS:-1}"
PARQUET="${PARQUET:-acts_rollout${N_DOCS}_L32.parquet}"
OUT="${OUT:-results}"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$HERE/src"
export NLA_REPO
mkdir -p "$OUT"

# Gemma-3-12B in bf16 is 22.5GB of weights. On a 24GB card that leaves ~800MB,
# and the default CUDA allocator fragments it badly enough that cuBLAS cannot
# get workspace -- the failure is CUBLAS_STATUS_EXECUTION_FAILED, not a clean
# "out of memory", so it does not look like what it is. Measured on a 4090:
# without this, stage 1 aborts before the first conversation; with it, peak sits
# at 23,246 MiB and does not grow over 16 iterations.
# Harmless on a big card, so it is set unconditionally rather than detected.
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"

# ---- ARCHIVE ANY PREVIOUS RUN'S ARTEFACTS ------------------------------------
# A fresh clone of this repo ships the committed results of an earlier run, and
# this script writes into the same directory. If a stage then fails or is
# skipped, $OUT holds a MIX -- some files from this run, some from the last --
# and summarize_results.py will read that mix and produce a summary that is part
# new and part stale, with nothing anywhere saying so.
#
# So anything already present is moved aside before stage 1. Moved, not deleted:
# the previous run's numbers are what RESULTS.md currently quotes.
_prev=$(ls "$OUT"/feature_overlap*.json "$OUT"/grounding.json \
             "$OUT"/feature_labels.json "$OUT"/summary.json \
             "$OUT"/SUMMARY.md "$OUT"/per_example.csv \
             "$OUT"/LATENTS_BY_BUCKET.md 2>/dev/null || true)
if [ -n "$_prev" ]; then
  _arch="$OUT/previous_$(date +%Y%m%d_%H%M%S)"
  mkdir -p "$_arch"
  echo "    moving a previous run's artefacts to $_arch/"
  for f in $_prev; do mv "$f" "$_arch/"; done
  echo
fi

# ---- BACKUP AFTER EVERY STAGE ------------------------------------------------
# Rented GPU boxes disappear. One died two hours into corpus generation and took
# the parquet with it -- the expensive part of the run, with no copy anywhere.
# The pod's own disk is not a backup: it dies with the pod.
#
# Set BACKUP_REPO to a HuggingFace dataset repo and every stage's output is
# pushed there as soon as it exists, so a death costs one stage instead of all
# of them:
#
#     export BACKUP_REPO=your-username/nla-run-artifacts
#
# Needs the same `hf auth login` the models did. Unset, the script runs exactly
# as before and just warns once.
BACKUP_REPO="${BACKUP_REPO:-}"
backup () {           # backup <stage-name> <file-or-dir>...
  [ -z "$BACKUP_REPO" ] && return 0
  local stage="$1"; shift
  for f in "$@"; do
    [ -e "$f" ] || continue
    echo "    [backup] $f -> $BACKUP_REPO"
    # || true: a backup failure must never kill a run that is otherwise fine
    hf upload "$BACKUP_REPO" "$f" "$stage/$(basename "$f")" \
        --repo-type=dataset --quiet 2>&1 | tail -1 || true
  done
}
if [ -z "$BACKUP_REPO" ]; then
  echo "!! BACKUP_REPO is not set. Nothing is copied off this machine, so if it"
  echo "   dies mid-run everything is lost. See scripts/run_experiment.sh."
  echo
else
  # Check WRITE access now rather than discovering it at the first upload, hours
  # in. A read token downloads gated models perfectly well and 403s on a dataset
  # write, so "the login worked" is not evidence this will.
  python - "$BACKUP_REPO" <<'PYCHK' || exit 1
import sys
from huggingface_hub import HfApi
repo = sys.argv[1]
try:
    HfApi().create_repo(repo, repo_type="dataset", private=True, exist_ok=True)
    print(f"    [backup] {repo} ready")
except Exception as e:
    msg = str(e)
    print(f"!! BACKUP_REPO is set to {repo} but it cannot be written to.")
    if "403" in msg or "Forbidden" in msg:
        print("   Your token is READ-only. Downloading gated models needs read;")
        print("   backing up needs WRITE. Create a write token at")
        print("   https://huggingface.co/settings/tokens and `hf auth login` again.")
    else:
        print(f"   {msg[:200]}")
    print("   Fix it, or unset BACKUP_REPO to run without backups.")
    sys.exit(1)
PYCHK
fi

# ---- 1. corpus ---------------------------------------------------------------
# oasst1 + LMSYS prompts, responses generated by Gemma ITSELF -- the recipe the
# Gemma Scope 2 IT SAEs were fine-tuned on. Running on anything else is costly:
# on FineWeb this same pipeline measured a 7-point effect where these rollouts
# gave 25.
echo "=== 1/5  corpus + activations ==="
if [ -f "$PARQUET" ]; then
  echo "    $PARQUET exists, skipping (delete it to rebuild)"
else
  python "$SRC/extract_activations.py" --arm rollout \
      --n-docs "$N_DOCS" --positions-per-doc 1 --seed 42 --out "$PARQUET"
fi
# The corpus is the most expensive thing to lose: ~2h of Gemma generation at
# N_DOCS=200, and it is unreproducible if the seed or the model ever changes.
backup corpus "$PARQUET" "$PARQUET.nla_meta.yaml"

# ---- 2. round trip -----------------------------------------------------------
# AV -> explanation -> AR -> reconstruction, SAE on both ends. Saves per-example
# FVE and cosine for all four comparisons, the explanation text, the source text,
# the latent sets, and every vector family to an .npz.
echo "=== 2/5  round trip (AV -> AR) + SAE ==="
python "$SRC/roundtrip.py" --av "$AV" --ar "$AR" \
    --parquet "$PARQUET" --n "$N_DOCS" --runs "$RUNS" --out-dir "$OUT"
backup roundtrip "$OUT/feature_overlap.json" "$OUT/feature_overlap_vectors.npz"

# ---- 3. re-encode under both SAEs --------------------------------------------
# Seconds, no model. l0_big for the reconstruction claim (the STRONGER SAE, so
# "the NLA beats it" is the harder claim to make); l0_small for anything about
# latent meaning, because l0_big's labels cannot be told from wrong ones.
echo "=== 3/5  re-encode under both SAEs ==="
for S in l0_small l0_big; do
  python "$SRC/refeature.py" --dirs "$OUT" --labels rollout \
      --sae "$S" --out-name "feature_overlap_$S.json"
done
backup refeature "$OUT/feature_overlap_l0_small.json" "$OUT/feature_overlap_l0_big.json"

# ---- 4. label, then judge ----------------------------------------------------
# label_features: 3 candidates per latent, winner chosen on one held-out band and
#   REPORTED on a second disjoint band, kept only if it beats the 95th percentile
#   of a wrong-label null. Caches by latent id, so re-running is cheap.
# judge_explanations: per latent, does the explanation cover it? Seven judgements
#   per pair -- 1 matched, 3 unrelated explanations, 3 non-firing latents.
echo "=== 4/5  label latents, then judge the explanations ==="
python "$SRC/label_features.py" --dirs "$OUT" \
    --out "$OUT/feature_labels.json" --batch 6
backup labels "$OUT/feature_labels.json"
python "$SRC/judge_explanations.py" --dirs "$OUT" --names rollout \
    --labels-json "$OUT/feature_labels.json" --out "$OUT/grounding.json"
backup judge "$OUT/grounding.json"

# ---- 5. every reported number ------------------------------------------------
# Reads the artefacts above and writes summary.json + SUMMARY.md. All statistical
# choices live in that one script: per-activation clustering, the false-positive
# correction, and which comparisons get a test at all.
echo "=== 5/5  compute every reported number ==="
python "$SRC/summarize_results.py" --dir "$OUT"
backup summary "$OUT/SUMMARY.md" "$OUT/summary.json" "$OUT/per_example.csv" \
    "$OUT/LATENTS_BY_BUCKET.md"

cat <<EOF

Done. Results in $OUT/

  SUMMARY.md            every reported number, as tables    <- start here
  summary.json          the same, machine-readable
  per_example.csv       one row per (activation, explanation)
  LATENTS_BY_BUCKET.md  per activation: explanation, source text, labelled latents

Check these before believing anything:
  1. the conversation count at the top of SUMMARY.md. It must equal the
     activation count, or the activations are not independent samples and every
     confidence interval is too narrow
  2. validated label count in SUMMARY.md section 3. ~50% is expected; much lower
     means the labeller is failing, not that the latents are hard
  3. the judge's false-positive rate in section 5. Under ~10%. An earlier prompt
     scored 78% and made every downstream number void
  4. the control rows in section 2. If a control sits near its matched number,
     that measurement is not discriminating and must not be quoted

Not part of the experiment, kept for reference:
  src/describe_buckets.py     blind bucket summaries -- qualitative, unreported
  src/classify_features.py    failed its own control, see INCONCLUSIVE.md
  src/matcher_bakeoff.py      how the judge prompt was chosen (METHODOLOGY section 4)
EOF
