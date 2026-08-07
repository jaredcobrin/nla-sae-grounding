# Measurements that did not meet the bar

Two experiments ran, produced numbers that looked like results, and are **not
reported in [RESULTS.md](RESULTS.md)**. They are kept here because a repo that
shows only its successes is not telling you how its numbers were made.

Both fail for the same reason:

> **An activation is not a summary of its document.** These activations are
> sampled at one token position. What the model represents *there* has no
> obligation to correspond to the document as a whole. Both experiments judge
> latents against **the whole source text**, so they ask a question the activation
> was never making a claim about. No prompt engineering fixes a question aimed at
> the wrong object.

`src/classify_features.py` still runs and still prints its own control. Nothing in
`RESULTS.md` depends on it.

---

## Test 1 — is the latent actually in the source document?

Show a model the source document and a latent's label; ask whether the thing the
latent responds to is really in the text. Once against the activation's **own**
document, once against a **different** one as a control. 607 pairs:

```
judged present in its OWN document        77.8%
judged present in a DIFFERENT document    47.8%   <- control
gap                                       +30.0
```

| bucket | own | control | gap |
|---|---:|---:|---:|
| shared | 80% | 46% | +34 |
| lost | 73% | 46% | +27 |
| made | 78% | 56% | +22 |

**The headline this produced, now withdrawn:** *"two-thirds of 'invented' latents
are genuinely in the source document — the AR reconstructs document-level context,
not position-specific state."*

**Why it does not count.** Beyond the wrong-object problem above, the prompt asks
a plain **yes/no** — the exact design that scored a **78.3% false-positive rate**
in the matcher bake-off before being replaced by the graded scheme
([METHODOLOGY.md](METHODOLOGY.md) §4). This one never went through that bake-off,
and "be strict" is not a substitute for measuring whether a prompt is strict. Its
own control shows the bias: **47.8% of labels judged present in documents they
have nothing to do with** is close to a coin flip. On a 6-activation run the gap
fell from +30.0 to **+5.5** and the script refused to report — the guard working
is the one good outcome here, but a +30 that becomes +5.5 on a subsample is not a
stable measurement.

**To make it real:** drop the document comparison and compare against the **local
context window** the activation was actually taken from. Then put that prompt
through the same bake-off the matcher went through.

---

## Test 2 — does the round trip destroy specifics and keep themes?

Classify every latent `GRAMMAR`/`CONTENT` and `GENERIC`/`SPECIFIC`, then compare
bucket composition. If the round trip kept themes and destroyed details, `lost`
should be richer in content+specific latents. Same 607 pairs:

| bucket | n | content+specific | content+generic | grammar+specific | grammar+generic |
|---|---:|---:|---:|---:|---:|
| shared | 366 | 22% ±4 | 24% ±4 | 16% ±4 | 37% ±5 |
| lost | 128 | 23% ±7 | 26% ±8 | 20% ±7 | 31% ±8 |
| made | 113 | 18% ±7 | 25% ±8 | 17% ±7 | 41% ±9 |

**Every difference against `shared` is under 1.3σ** — a null. The intuitive story
does not appear in the aggregate, even though hand-picked examples supporting it
are easy to find (`Nginx`, `"tomato"`, temperature values all sit in `lost`).

**Why it does not count.** The two axes are model judgements with **no control at
all** — no shuffled labels, no baseline, nothing. Every other number in this
project is reported against a null; these are not, which by this repo's own
standard makes them weaker than Test 1, not stronger. And **a null result from an
unvalidated instrument is doubly weak**: "no difference between buckets" and "an
instrument that cannot detect the difference" produce identical output. A
secondary finding — lost content+specific latents scoring 57% on accuracy against
shared's 80% — uses Test 1's presence axis and inherits all of its problems.

**To make it real:** hand-label a few hundred latents on both axes and measure the
classifier against that ground truth. Until then this is an untested instrument
returning "no effect", which is not a finding.

---

## What survived

**The `UNVERIFIED` name.** The tool does not call its third bucket "invented", and
that no longer rests on Test 1. It rests on the construction — the bucket *is*
"the AR produced it and we did not find it in the original", which is unchecked
rather than false — and on `RESULTS.md` §1's C > A, where the SAE reads the AR's
output more faithfully than a real activation, so a latent may be present and
simply invisible to the SAE. That is an argument from the measurement setup, not
from a model's opinion.

**The guard that killed Test 1.** `classify_features.py` still refuses to print
when its control stops separating. It fired on a real run.
