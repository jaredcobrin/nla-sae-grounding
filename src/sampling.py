"""Seeded activation sampling from a parquet.

Two things, both small, both load-bearing.

WHY `load_vectors` EXISTS RATHER THAN A SLICE
Row selection was hand-rolled twice and was wrong both times:

  * `rows[0:n]` returned several positions from a SINGLE document. stage-0
    extraction writes rows grouped by document, so the first n rows are ten
    positions of doc 0 rather than a sample of the corpus.
  * first-row-per-document systematically picked the EARLIEST position in every
    document — the one with the least left-context, which decodes to the least
    meaningful activation. Measured at FVE 0.64 against 0.76 for properly
    sampled rows, across three seeds. That is a large enough gap to look like a
    real finding if nobody checks the sampler.

So it reads a pool and takes a seeded random sample. Same `--seed` always
selects the same rows, which is what makes a baseline run and a treatment run
a *paired* comparison rather than two different datasets.

WHY `FAILED_EXTRACTION_MSE` IS 2.0 AND NOT 0 OR NaN
When the AV emits no well-formed `<explanation>` tag pair there is nothing to
score. Training penalises that case with reward −2.0 (`reward.py:38`), i.e.
MSE 2.0 — the value an orthogonal prediction would get. Reusing it here keeps a
tag-miss from being scored more favourably at evaluation than in training, which
is what would happen if the row were dropped or scored as an empty string.

Vendored from the previous repo's `baseline_fve.py`, which also carried a
standalone baseline-FVE CLI. That CLI is not here: `roundtrip.py` computes the
same number as its startup health check, and shipping a second path to it would
be two things to keep in agreement.
"""

from __future__ import annotations

import numpy as np
import pyarrow.parquet as pq
import torch

ACTIVATION_COLUMN = "activation_vector"

# Training's penalty for an unparseable rollout (reward.py:38 uses -2.0 as the
# reward, i.e. MSE = 2.0 — the orthogonal-equivalent). Reusing the same value
# keeps a tag-miss from being scored more favourably here than in training.
FAILED_EXTRACTION_MSE = 2.0


def load_vectors(
    parquet_path: str, n: int, seed: int, pool_cap: int = 50_000
) -> tuple[torch.Tensor, list[int], list[int | None]]:
    """Read up to `pool_cap` rows, then random-sample `n` of them.

    Random-sampling rather than head-slicing matters: extraction writes rows
    grouped by document, so the first n rows come from only a handful of docs
    and are not representative. Seeded, so the same `seed` selects the same rows.

    Returns (vectors [n, d] float32, chosen row indices, n_raw_tokens or Nones).
    """
    pf = pq.ParquetFile(parquet_path)
    cols = set(pf.schema_arrow.names)
    want = [ACTIVATION_COLUMN] + (["n_raw_tokens"] if "n_raw_tokens" in cols else [])

    chunks: list[np.ndarray] = []
    positions: list[int | None] = []
    total = 0
    for batch in pf.iter_batches(batch_size=8192, columns=want):
        col = batch.column(ACTIVATION_COLUMN)
        # .flatten() -> values buffer; works for both FixedSizeList (what
        # extraction writes) and variable-length ListArray.
        flat = col.flatten().to_numpy(zero_copy_only=False).astype(np.float32)
        chunks.append(flat.reshape(len(col), -1))
        if "n_raw_tokens" in want:
            positions.extend(batch.column("n_raw_tokens").to_pylist())
        else:
            positions.extend([None] * len(col))
        total += len(col)
        if total >= pool_cap:
            break

    pool = np.concatenate(chunks, axis=0)
    assert len(pool) > 0, f"no rows in {parquet_path!r}"
    if n > len(pool):
        print(f"[warn] requested n={n} but parquet has {len(pool)} rows — using all")
        n = len(pool)

    idx = np.random.default_rng(seed).choice(len(pool), size=n, replace=False)
    idx.sort()          # keep parquet order for readable logs
    return (
        torch.from_numpy(pool[idx]),
        idx.tolist(),
        [positions[i] for i in idx],
    )
