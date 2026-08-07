"""Say in English what the round trip kept, destroyed, and invented.

NOT PART OF THE REPORTED EXPERIMENT. This works and it has a control, but its
output is qualitative -- read by eye, not scored -- so RESULTS.md does not quote
it. It is kept because it is the most legible thing in the repo: it turns a pile
of latent labels into a paragraph, blind to the AV's explanation, so agreement
between the two is evidence rather than an echo. See METHODOLOGY.md section 6.

WHY THIS EXISTS
Every previous stage asked a model to JUDGE ("does this explanation cover this
feature?"), and three designs in a row had calibration problems — the first said
yes to 78% of features that were not there. This asks a model to DESCRIBE
instead. No threshold, no yes/no, nothing to calibrate. It turns ~20 feature
labels into a paragraph a person can read, and the comparison against the AV
explanation is then done by eye.

THE BLINDING IS THE POINT
The describer never sees the AV explanation. Everything it writes comes from the
feature labels alone. So when the summary and the AV explanation agree, that
agreement is evidence rather than an echo.

THE CONTROL IS NOT OPTIONAL
Given twenty labels, a language model will manufacture a coherent story out of
anything, including a random pile of grammatical patterns. So every bucket is
ALSO summarised from a DIFFERENT activation's features. If a real summary cannot
be told from its control, the summaries are fluency rather than signal and
nothing here means anything. Both are printed side by side, unlabelled in the
JSON ordering, so the comparison is honest.

WHAT TO EXPECT — stated in advance so it is not an excuse afterwards
The category audit found every category is 57-87% grammatical-position labels
("prepositions following a noun"), not subject matter. So the LOST summaries in
particular may come out vague. That is not a failure of this method: it would
mean the round trip mostly destroys grammatical detail rather than content,
which is a finding.

COVERAGE IS REPORTED, NOT HIDDEN
Only 353 of 755 features have a validated label. The unlabelled ones are counted
in each prompt ("plus N further features with no reliable label") so the reader
knows what fraction of the evidence the summary actually rests on.

Usage:
    python src/describe_buckets.py \
        --dirs results results/rollout \
               results/wildchat \
        --names fineweb rollout wildchat \
        --labels-json results/feature_labels.json \
        --out results/bucket_descriptions.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

BUCKETS = {
    "shared": ("kept", "These were present in the model's internal state AND survived "
                       "being described in words and reconstructed from that description."),
    "lost":   ("destroyed", "These were present in the model's internal state but did "
                            "NOT survive the round trip through a written description."),
    "made":   ("invented", "These were NOT in the original internal state. They appeared "
                           "only in the reconstruction built from the written description."),
}

_PROMPT = """A language model was reading a piece of text. At one position, its internal
state was captured and decomposed into individual detectors that were active.

Below are the detectors in one particular group. Each line is what one detector
responds to:

{labels}
{extra}
Describe, in plain English, what this group of detectors collectively tells you
about the text the model was reading. Two or three sentences.

Say what the text appears to be ABOUT and what KIND of text it is, to whatever
extent these detectors support that. Be concrete where they are concrete.

If the detectors are mostly grammatical patterns rather than subject matter, say
so plainly — "these are mostly structural, and indicate little about the
content" is a valid and useful answer. Do not invent a topic the detectors do
not support."""


def batch_gen(model, tok, prompts, max_new=150, bs=8):
    out = []
    for i in range(0, len(prompts), bs):
        texts = [tok.apply_chat_template([{"role": "user", "content": p}], tokenize=False,
                                          add_generation_prompt=True) for p in prompts[i:i + bs]]
        enc = tok(texts, return_tensors="pt", padding=True,
                  add_special_tokens=False).to(model.device)
        with torch.no_grad():
            g = model.generate(**enc, max_new_tokens=max_new, do_sample=False,
                               pad_token_id=tok.pad_token_id)
        out += [tok.decode(r[enc["input_ids"].shape[1]:], skip_special_tokens=True).strip()
                for r in g]
        print(f"    {len(out)}/{len(prompts)}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dirs", nargs="+", required=True)
    ap.add_argument("--names", nargs="+", default=None)
    ap.add_argument("--labels-json", required=True)
    ap.add_argument("--model", default="google/gemma-3-12b-it")
    ap.add_argument("--sae", default="l0_small")
    ap.add_argument("--run", type=int, default=0, help="which of the 5 runs per activation")
    ap.add_argument("--max-labels", type=int, default=24)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)
    names = a.names or [Path(d).name or "fineweb" for d in a.dirs]

    L = json.loads(Path(a.labels_json).read_text())
    lab = {int(k): v["label"] for k, v in L.items() if v.get("reliable") and v.get("label")}

    # One run per activation: shared/lost/made differ per run, so mixing runs
    # would make a single row internally inconsistent.
    units = []
    for d, nm in zip(a.dirs, names):
        d = Path(d)
        base = json.loads((d / "feature_overlap.json").read_text())
        small = json.loads((d / f"feature_overlap_{a.sae}.json").read_text())
        seen = set()
        for i, r in enumerate(small["runs"]):
            if r["act"] in seen:
                continue
            if base["runs"][i].get("run") not in (None, a.run) and i % 5 != a.run:
                continue
            seen.add(r["act"])
            units.append({"corpus": nm, "act": r["act"], "row": base["runs"][i].get("row"),
                           "explanation": (base["runs"][i].get("explanation") or "").strip(),
                           "shared": r["shared_features"], "lost": r["lost_features"],
                           "made": r["invented_features"]})
    print(f"[data] {len(units)} activations (one run each)")

    tok = AutoTokenizer.from_pretrained(a.model)
    tok.padding_side = "left"
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(a.model, dtype=torch.bfloat16).to("cuda").eval()

    rng = np.random.default_rng(a.seed)

    def render(feats):
        known = [f for f in feats if f in lab]
        rng.shuffle(known)
        shown = known[:a.max_labels]
        body = "\n".join(f"  - {lab[f]}" for f in shown) or "  (none with a reliable label)"
        n_un = len(feats) - len(known)
        extra = (f"\nPlus {n_un} further detectors whose behaviour could not be "
                 f"reliably labelled.\n" if n_un else "\n")
        return body, extra, len(shown), n_un

    prompts, key = [], []
    for i, u in enumerate(units):
        ctrl = units[(i + 7) % len(units)]          # a different activation
        for b in BUCKETS:
            for arm, src in (("real", u), ("control", ctrl)):
                body, extra, ns, nu = render(list(src[b]))
                prompts.append(_PROMPT.format(labels=body, extra=extra))
                key.append((i, b, arm, ns, nu))
    print(f"[work] {len(prompts)} summaries "
          f"({len(units)} activations x 3 buckets x real+control)")

    t0 = time.time()
    outs = batch_gen(model, tok, prompts)
    print(f"[done] {(time.time()-t0)/60:.1f} min")

    for u in units:
        u["described"] = {}
    for (i, b, arm, ns, nu), txt in zip(key, outs):
        units[i]["described"].setdefault(b, {})[arm] = {
            "text": txt, "n_labelled": ns, "n_unlabelled": nu}

    Path(a.out).write_text(json.dumps({"config": vars(a), "units": units}, indent=2))

    for u in units[:6]:
        print("\n" + "=" * 78)
        print(f"{u['corpus']}  activation {u['act']}")
        print("=" * 78)
        print("AV EXPLANATION (the describer below never saw this):")
        print("  " + u["explanation"][:400].replace("\n", " "))
        for b, (word, _) in BUCKETS.items():
            d = u["described"].get(b, {})
            print(f"\n  {b.upper()} — {word}  "
                  f"({d.get('real',{}).get('n_labelled',0)} labelled, "
                  f"{d.get('real',{}).get('n_unlabelled',0)} not)")
            print("    FROM THESE FEATURES : " + d.get("real", {}).get("text", "")[:330].replace("\n", " "))
            print("    CONTROL (other act) : " + d.get("control", {}).get("text", "")[:330].replace("\n", " "))
    print(f"\nwrote {a.out}")
    print("\nRead the CONTROL lines first. If they are as plausible as the real ones,")
    print("the summaries are language-model fluency and carry no information.")


if __name__ == "__main__":
    main()
