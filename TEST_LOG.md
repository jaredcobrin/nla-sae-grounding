# Verification log

A record of what was actually run against real weights from this repo's layout,
what broke, and what was fixed. Written live during testing rather than
reconstructed afterwards.

**Why this file exists.** Everything in `src/` was moved, renamed, and edited
when this repo was assembled from the working version: files renamed, two
modules vendored, all imports repointed, a new SAE path resolver added, and
`trust_report.py` changed to free the AV and AR before loading the writer. All
of it compiles and imports. **None of it had touched real weights from this
layout** before the session below.

---

## What is being tested, and why in this order

| # | test | what it would catch |
|---|---|---|
| 1 | environment + model download | wrong `transformers` version; gated-model access |
| 2 | `hf_paths.py` resolves the SAE | the fix for the hardcoded `/workspace/hf` path — this is the change most likely to fail on a fresh machine |
| 3 | imports with `NLA_REPO` set | the vendored `nla_av.py` / `sampling.py` and the upstream dependency |
| 4 | `trust_report.py` on 5 activations | **the main test.** Exercises AV, AR, SAE, on-demand labelling, and prose in one run |
| 5 | peak VRAM stays ≤ 48 GB | the `del av, critic` added to make a 48 GB card viable — untested |
| 6 | no CJK in any explanation | the loudest smoke test for the injection path (see `nla_av.py` docstring) |
| 7 | regenerate example reports | the shipped examples predate a wording fix and contradict the current code |

## Known risks going in

- **`hf_paths.py`** has only ever been tested on its *failure* path (the error
  message when the SAE is absent). Its success path is unrun.
- **`del av, critic`** — freeing may not actually release if a reference is held
  somewhere I did not spot. If peak stays ~72 GB, the 48 GB claim in the README
  is wrong and must be corrected.
- **Python ≥ 3.10** is required by the upstream `nla/` package (`str | None`).
  Verified locally only by *failing* on 3.9.
- The example reports in `results/example_reports/` were generated with the old
  bucket wording ("implied by the explanation"). They are stale by design until
  step 7.

---

## Session log

*(filled in during testing)*

### Environment

_pending_

### 1. Setup and downloads

_pending_

### 2. SAE path resolution

_pending_

### 3. Imports

_pending_

### 4. Trust report

_pending_

### 5. VRAM

_pending_

### 6. Injection sanity (CJK check)

_pending_

### 7. Example reports regenerated

_pending_

---

## Outcome

_pending_

## Fixes made during testing

_pending_

## What remains untested

_pending_
