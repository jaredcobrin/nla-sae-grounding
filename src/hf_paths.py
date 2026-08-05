"""Locate the Gemma Scope SAE in whatever HuggingFace cache this machine uses.

Every script here needs the SAE weights and exemplar store. An earlier version
hardcoded a pod-specific path (`/workspace/hf/hub/...`), which works on exactly
one machine and fails instantly for anyone who clones the repo.

Resolution order:
  1. $GEMMA_SCOPE_DIR             an explicit override, pointing at the snapshot
  2. $HF_HUB_CACHE                the modern variable
  3. $HF_HOME/hub                 the older one
  4. ~/.cache/huggingface/hub     the default

If the SAE is missing the error says how to fetch it, rather than surfacing as a
StopIteration from `next(dir.iterdir())` fifty lines later.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO = "google/gemma-scope-2-12b-it"
_REPO_DIR = "models--google--gemma-scope-2-12b-it"

# Sparsity variants for layer 32, width 16k. Both are used, for different
# questions -- see METHODOLOGY.md section 3.
L0_SMALL = "layer_32_width_16k_l0_small"   # ~21 active features: labelable
L0_BIG = "layer_32_width_16k_l0_big"       # ~120 active: strongest reconstruction


def _cache_roots():
    if os.environ.get("HF_HUB_CACHE"):
        yield Path(os.environ["HF_HUB_CACHE"])
    if os.environ.get("HF_HOME"):
        yield Path(os.environ["HF_HOME"]) / "hub"
    yield Path.home() / ".cache" / "huggingface" / "hub"


def sae_snapshot() -> Path:
    """Directory containing `resid_post_all/`. Raises with instructions if absent."""
    override = os.environ.get("GEMMA_SCOPE_DIR")
    if override:
        p = Path(override)
        if (p / "resid_post_all").is_dir():
            return p
        raise FileNotFoundError(
            f"GEMMA_SCOPE_DIR={override} has no resid_post_all/ inside it")

    for root in _cache_roots():
        snaps = root / _REPO_DIR / "snapshots"
        if snaps.is_dir():
            for s in sorted(snaps.iterdir()):
                if (s / "resid_post_all").is_dir():
                    return s

    raise FileNotFoundError(
        f"could not find {REPO} in any HuggingFace cache.\n"
        f"  searched: {', '.join(str(r) for r in _cache_roots())}\n"
        f"  fetch the two variants this repo uses with:\n\n"
        f"    python -c \"from huggingface_hub import snapshot_download as d; \"\\\n"
        f"      \"d('{REPO}', allow_patterns=['resid_post_all/{L0_SMALL}/*',\"\\\n"
        f"      \"'resid_post_all/{L0_BIG}/*'])\"\n\n"
        f"  or set GEMMA_SCOPE_DIR to a snapshot directory you already have.")


def sae_variant_dir(variant: str = L0_SMALL) -> Path:
    """Directory holding params.safetensors and examples.safetensors."""
    d = sae_snapshot() / "resid_post_all" / variant
    if not d.is_dir():
        have = sorted(p.name for p in (sae_snapshot() / "resid_post_all").iterdir())
        raise FileNotFoundError(
            f"SAE variant {variant!r} not downloaded.\n  present: {have}")
    return d
