# Measurements that did not meet the bar

Two experiments were run, produced numbers that looked like results, and are
**not reported in [RESULTS.md](RESULTS.md)**. They are kept here in full — with
what they found and why it does not count — because a repo that only shows its
successes is not telling you how its numbers were made.

Both share a root cause worth stating once:

> **An activation is not a summary of its document.** These activations are
> sampled at one token position. What the model represents *there* is not
> obliged to correspond to the document as a whole. Both experiments below judge
> features against **the whole source text**, so they ask a question the
> activation was never making a claim about. No amount of prompt engineering
> fixes a question that is aimed at the wrong object.

The code is still in the repo (`src/classify_features.py`), still runs, and still
prints its own control. Nothing in `RESULTS.md` depends on it.

---

## Test 1 — is the feature actually in the source document?

**The question.** For each feature, show a model the source document and the
feature's label, and ask whether what the feature responds to is really in the
text. Run it twice: once against the activation's **own** document, once against
a **different** one as a control.

**What it found** (607 feature–activation pairs):

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

Narrowed to content-bearing features in the `made` bucket:

| | own | control |
|---|---:|---:|
| made · content · specific | 65% | 30% |
| made · content · generic | 68% | 25% |

**The headline it produced, which is now withdrawn:** *"two-thirds of 'invented'
features are genuinely in the source document — the AR reconstructs
document-level context, not position-specific state."*

### Why it does not count

**1. The question is aimed at the wrong object.** See the note above. A feature
firing at token 300 is about the model's state at token 300. Asking whether it is
"in the document" tests something else entirely, and a positive answer would not
mean what the headline claimed it meant.

**2. The prompt is the exact shape that already failed here.** It asks a plain
yes/no:

```
PRESENT: is what this detector responds to ACTUALLY IN the document excerpt
above? Judge only against the excerpt shown. Be strict — answer NO if the
excerpt does not contain it...
```

In the matcher bake-off ([METHODOLOGY.md](METHODOLOGY.md)) the plain-yes/no
variant scored a **78.3% false-positive rate** — it said yes to four out of five
features that provably were not present. It was replaced by the graded
`CLEARLY`/`PROBABLY`/`UNCLEAR`/`NO` scheme, which scored 5.7%. **This prompt never
went through that bake-off**, and "be strict" is not a substitute for measuring
whether a prompt is strict.

**3. Its own control shows the bias.** A judge that calls **47.8%** of labels
present in documents they have nothing to do with is close to a coin flip. Some
of that is the ill-posed question and some is yes-bias; the experiment cannot
separate them, which is the problem.

**4. It did not survive a smaller run.** On a 6-activation pass the gap fell from
+30.0 to **+5.5**, and the script refused to report:

```
!! GAP TOO SMALL. The accuracy axis is not discriminating and must
   not be reported. Everything below inherits it.
```

That guard working is the one genuinely good outcome here. But a +30 that becomes
+5.5 on a subsample is not a stable measurement.

### What it would take to make this real

Drop the document comparison entirely and compare against **the local context the
activation was actually taken from** — a window of tokens around the sampled
position, not the whole text. Then put that prompt through the same bake-off the
matcher went through: candidate wordings, measured FPR against features that
never fired, and a graded output rather than yes/no.

---

## Test 2 — does the round trip destroy specifics and keep themes?

**The question.** Classify every feature on two axes — `GRAMMAR` vs `CONTENT`,
and `GENERIC` vs `SPECIFIC` — then compare the composition of the `shared`,
`lost` and `made` buckets. If the round trip preserved themes and destroyed
details, `lost` should be visibly richer in content+specific features.

**What it found** (same 607 pairs):

| bucket | n | content+specific | content+generic | grammar+specific | grammar+generic |
|---|---:|---:|---:|---:|---:|
| shared | 366 | 22% ±4 | 24% ±4 | 16% ±4 | 37% ±5 |
| lost | 128 | 23% ±7 | 26% ±8 | 20% ±7 | 31% ±8 |
| made | 113 | 18% ±7 | 25% ±8 | 17% ±7 | 41% ±9 |

Differences against `shared`, in sigma:

| cell | lost | made |
|---|---:|---:|
| content+specific | 0.2 | −1.1 |
| content+generic | 0.5 | 0.2 |
| grammar+specific | 0.8 | 0.1 |
| grammar+generic | −1.3 | 0.6 |

**Every difference is under 1.3σ** — a null. The intuitive story, that themes
survive and specifics are lost, does not appear in the aggregate, even though
hand-picked examples supporting it are easy to find (`Nginx`, `"tomato"`,
temperature values all sit in `lost`).

A secondary finding: lost content+specific features scored 57% on the accuracy
axis against shared's 80%, a 24-point gap at 2.4σ — suggesting some "lost"
features were **SAE misfires** the AR simply did not reproduce.

### Why it does not count

**1. It has no null of its own.** The `GRAMMAR`/`CONTENT` and
`GENERIC`/`SPECIFIC` axes are LLM judgements with **no control run at all** — no
shuffled labels, no wrong-label baseline, nothing. Every other number in this
project is reported against a null. These are not, which by this repo's own
standard makes them weaker than Test 1, not stronger.

**2. A null result from an unvalidated instrument is doubly weak.** "No
difference between buckets" and "an instrument that cannot detect the difference"
produce identical output. Without a positive control — a case where the axes are
*known* to differ, which the classifier is then shown to detect — the null is
uninterpretable. This is the most important flaw here and it applies no matter
how the prompt is worded.

**3. The secondary finding inherits Test 1 entirely.** The 57%-vs-80% comparison
uses the accuracy axis, which is Test 1's presence judgement. It cannot be more
reliable than its input.

**4. Same prompt, same call.** Both axes come from the same
`classify_features.py` call as Test 1 and share its provenance.

### What it would take to make this real

Build a positive control first: hand-label a few hundred features on both axes,
and measure the classifier against that ground truth. If it recovers hand labels
well, the null becomes meaningful. Until then this is an untested instrument
returning "no effect", which is not a finding.

---

## What was kept from all this

Two things survive and are used in `RESULTS.md`:

- **The `UNVERIFIED` name.** The tool does not call the third bucket "invented".
  That naming no longer rests on Test 1 — it rests on the construction (the
  bucket *is* "the AR produced it and we did not find it in the original") and on
  §1's C > A, which shows the SAE reads the AR's output more faithfully than a
  real activation, so a feature may be present and simply invisible to the SAE.
  That is an argument from the measurement setup, not from an LLM's opinion.
- **The guard that killed Test 1.** `classify_features.py` still refuses to print
  its results when its control stops separating. It fired on a real run. That
  behaviour is worth keeping in any measurement that leans on a judge.
