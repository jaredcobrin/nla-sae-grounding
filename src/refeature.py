"""Re-derive feature sets from the SAVED vectors under a different SAE.

WHY THIS IS CHEAP
roundtrip.py saved every vector family to feature_overlap_vectors.npz
(v_orig, v_ar, and their SAE reconstructions). Changing which SAE reads those
vectors therefore costs one matrix multiply — no AV generation, no AR
reconstruction, no re-sampling. The explanations and the activations are fixed;
only the instrument changes.

WHY CHANGE THE SAE AT ALL
Two different questions want two different instruments, and for each the choice
below is the CONSERVATIVE one:

  reconstruction fidelity ("does the AR beat the SAE?")  -> l0_big
      L0~129. The strongest SAE available, so "the AR reconstructs better" is
      the harder claim to make. Using a weaker SAE here would flatter our
      result. RESULTS.md section 1 therefore reports l0_big.

  feature SEMANTICS ("what kind of thing is lost?")      -> l0_small
      L0~21. Measured on our own activations: token purity 0.24 vs 0.17, and
      label-vs-wrong-label AUC gap +0.092 vs +0.008. l0_big features are too
      polysemantic to label reliably, and unreliable labels would silently
      poison every category count downstream.

Reporting both, from the same vectors, is what keeps this from being a choice
of whichever SAE gave the nicer number.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch
from safetensors.torch import load_file

from hf_paths import sae_variant_dir, L0_SMALL, L0_BIG  # noqa: E402


def encode(V, P):
    """b_dec is added on DECODE only. Subtracting it from the input was measured
    at cos 0.31 vs 0.99 earlier in this project — it destroys the signal."""
    pre = V @ P["w_enc"] + P["b_enc"]
    return torch.where(pre > P["threshold"], pre, torch.zeros_like(pre))


def jac(a: set, b: set) -> float:
    return len(a & b) / max(1, len(a | b))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dirs", nargs="+", required=True)
    ap.add_argument("--labels", nargs="+", required=True, help="display name per dir")
    ap.add_argument("--sae", default="l0_small", choices=["l0_small", "l0_big"])
    ap.add_argument("--out-name", default="feature_overlap_small.json")
    a = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)

    d = sae_variant_dir(L0_SMALL if a.sae == "l0_small" else L0_BIG)
    P = load_file(str(d / "params.safetensors"))
    print(f"[sae] {a.sae}\n")

    print(f"{'corpus':>10} {'L0 orig':>8} {'L0 ar':>7} {'shared':>7} {'lost':>6} "
          f"{'made':>6} {'kept%':>6} {'jac':>6} {'ctrl':>6} {'uniq':>6}")
    print("-" * 84)
    grand = set()
    for dd, name in zip(a.dirs, a.labels):
        dd = Path(dd)
        Z = np.load(dd / "feature_overlap_vectors.npz")
        J = json.loads((dd / "feature_overlap.json").read_text())
        v_orig = torch.from_numpy(Z["v_orig"]).float()
        v_ar = torch.from_numpy(Z["v_ar"]).float()
        A_o, A_r = encode(v_orig, P), encode(v_ar, P)
        F_o = [set(torch.nonzero(r).flatten().tolist()) for r in A_o]
        F_r = [set(torch.nonzero(r).flatten().tolist()) for r in A_r]

        # map each AR row back to its source activation, exactly as saved
        act_of = (Z["row_idx"].tolist() if "row_idx" in Z and len(Z["row_idx"]) == len(v_ar)
                  else [r["act"] for r in J["runs"]])
        if len(act_of) != len(v_ar):
            act_of = [i // (len(v_ar) // len(v_orig)) for i in range(len(v_ar))]

        runs, sh, lo, md, jj, cc = [], 0, 0, 0, [], []
        for i, fr in enumerate(F_r):
            k = int(act_of[i]) % len(F_o)
            fo = F_o[k]
            sh += len(fo & fr); lo += len(fo - fr); md += len(fr - fo)
            jj.append(jac(fo, fr))
            # Mismatched control: this AR feature set against a DIFFERENT
            # activation. Pair HALFWAY across the set, not with the neighbour --
            # stage-0 samples ~10 positions per document and writes them
            # adjacently, so `k+1` often lands on another position of the SAME
            # document. That is not a mismatched pair, and it inflated this
            # control to 0.040 where roundtrip.py's half-offset gave 0.026.
            # Same pairing rule as roundtrip.py:317 so the two files agree.
            cc.append(jac(F_o[(k + len(F_o) // 2) % len(F_o)], fr))
            runs.append({"act": k, "run": i,
                          "shared_features": sorted(fo & fr),
                          "lost_features": sorted(fo - fr),
                          "invented_features": sorted(fr - fo)})
        uniq = set().union(*F_o) | set().union(*F_r)
        grand |= uniq
        n = len(F_r)
        print(f"{name:>10} {np.mean([len(f) for f in F_o]):>8.1f} "
              f"{np.mean([len(f) for f in F_r]):>7.1f} {sh/n:>7.1f} {lo/n:>6.1f} "
              f"{md/n:>6.1f} {100*sh/max(1,sh+lo):>5.0f}% {np.mean(jj):>6.3f} "
              f"{np.mean(cc):>6.3f} {len(uniq):>6}")
        (dd / a.out_name).write_text(json.dumps(
            {"sae": a.sae, "stage1": {"F_orig": [sorted(f) for f in F_o]},
             "runs": runs,
             "totals": {"shared": sh / n, "lost": lo / n, "made": md / n,
                         "jaccard": float(np.mean(jj)), "control": float(np.mean(cc))}},
            indent=2))
    print("-" * 84)
    print(f"unique features to label across all corpora: {len(grand)}")


if __name__ == "__main__":
    main()
