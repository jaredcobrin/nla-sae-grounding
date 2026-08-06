# Future work

Everything in [RESULTS.md](RESULTS.md) is **correlational**. It measures which
latents co-occur with which text, never whether any of it is load-bearing. The
proposals here are ordered by how much they change that, and the last one is
causal.

**Most of this needs no new GPU time.** `roundtrip.py` saves every vector family
to `feature_overlap_vectors.npz` for exactly this reason:

| array | shape | what it is |
|---|---|---|
| `v_orig` | [50, 3840] | the sampled activations |
| `v_orig_sae` | [50, 3840] | SAE reconstruction of each |
| `v_ar` | [250, 3840] | the AR's output per explanation |
| `v_ar_sae` | [250, 3840] | SAE reconstruction of each of those |
| `row_idx`, `run_idx` | — | index arrays joining back to the JSON |

Having `v_orig_sae` matters: it lets the SAE's own reconstruction error be
subtracted out, so an effect can be attributed to the AR rather than to SAE
lossiness.

`feature_overlap.json` also carries **per-latent activation strengths** for the
50 original activations (`stage1.strengths`, latent ID → strength, `l0_big`),
plus `sae_cos` and `sae_fve` per activation. The AR outputs' strengths are *not*
stored, but `v_ar` is in the `.npz`, so they are one encode away — no GPU.

**What is NOT on disk anywhere:** reconstruction quality under `l0_small`.
`refeature.py` writes only `F_orig`, in this repo and in every earlier run. Hence
item 0.

---

## 0. The cheap one: does C > A hold at `l0_small`?

`RESULTS.md` §1 measures the SAE reconstructing the AR's output better than a
real activation (FVE 0.700 vs 0.587, L0 101 vs 120) — but **only at `l0_big`**.
Section 4, and the tool, run on `l0_small`, where `refeature.py` writes latent
sets without reconstruction scores. The caveat is currently carried across that
boundary untested.

Encode and decode `v_orig` and `v_ar` under `l0_small`, report cosine and L0 for
each. Minutes of CPU once the SAE weights are downloaded, and it either confirms
a caveat the file leans on or removes it.

Checked before writing this: **no artefact in this repo or in any earlier run
carries it.** `refeature.py` has only ever written `F_orig`, so there is no
shortcut — it has to be computed.

---

## 1. Give each bucket a direction

**The idea.** A latent is currently just an integer ID. But the SAE
reconstruction is a *linear* sum of decoder vectors weighted by activation
strength, so each bucket can be turned back into a direction in activation space:

```
d_shared = Σ  acts[f] · w_dec[f]     for f in shared
d_lost   = Σ  acts[f] · w_dec[f]     for f in lost
d_made   = Σ  acts[f] · w_dec[f]     for f in made      (using the AR's strengths)
```

These three sum to the SAE's reconstruction, so it is a genuine decomposition
rather than a heuristic.

**What it buys.** Every bucket comparison in this repo is a *count*. Directions
let you ask geometric questions instead:

- How large is `d_lost` relative to `d_shared`? Losing 5 marginal latents is not
  the same as losing 5 strong ones, and counts cannot tell them apart.
- What is the angle between `d_made` and `d_shared`? If they are near-orthogonal,
  the AR is adding something unrelated; if aligned, it is over-expressing a theme
  already present.
- Is `d_made` consistent *across activations*? A shared direction would suggest a
  systematic bias in the AR rather than per-example noise. Take the top principal
  component of `d_made` over all 250 runs and see how much variance it carries.

**Watch out for.** Decoder vectors are **not orthogonal**, so these directions
are not independent components and their norms are not additive. And latent
strengths are not comparable across latents without normalisation — a latent
with a naturally large activation scale will dominate any raw sum.

---

## 2. Read the residual through the unembedding

**The idea.** Take the direction the AR got wrong:

```
δ = v_ar − v_orig
```

and push it through the model's unembedding matrix (`logit lens`) to see which
tokens that direction promotes and suppresses.

**What it buys.** It converts an abstract error vector into something readable.
If `δ` consistently promotes tokens like a topic label while suppressing
specific named entities, that is a legible characterisation of what the AR adds
and drops — and one that does **not** route through a language-model judge, which
is where three separate measurements in this project went wrong.

**Watch out for.**

- **Layer 32 is not the last layer.** These activations sit at layer 32 of 48, so
  the unembedding is a rough proxy — 16 more layers act on that direction before
  logits. Statements should be about "what this direction looks like at layer 32",
  not "what the model will say".
- **Subtract the SAE's own error first.** Use `v_orig_sae` to estimate what
  reconstruction noise alone looks like through the same lens, and difference
  against it. Otherwise you will read SAE lossiness as an AR effect.
- **Norm.** `δ` has no reason to be unit-norm; compare directions, not magnitudes.
- Gemma-3 ties embeddings and applies a √d scale — see the embed-scale note in
  `src/nla_av.py` before touching the embedding matrix.

---

## 3. The causal one: steer with it

**The idea.** Add `δ` (or `d_made`) back into Gemma at layer 32 during a normal
forward pass, and see what changes in the generated text.

**Why this is the most valuable item here.** Everything in `RESULTS.md` is
correlational — it establishes that certain latents co-occur with certain text.
Steering asks whether the direction *does* anything. If adding `d_made` makes the
model produce the content the AV confabulated, that is evidence the AR's addition
is a real, functional direction rather than a reconstruction artefact. If nothing
happens, that is evidence it is noise. **Both outcomes are informative**, which is
the mark of a worthwhile experiment.

**The controls this needs — without them it proves nothing.**

- **A norm-matched random direction.** Injecting any large vector perturbs
  generation. The comparison is against a random direction of identical norm, not
  against no injection.
- **A scale sweep.** Report behaviour across injection strengths, not one
  hand-picked value that happened to look good.
- **The SAE-error direction as a second control** — `v_orig_sae − v_orig`. If
  steering with SAE reconstruction error produces a similar effect, the result is
  about perturbation, not about the AR.
- **Blind scoring.** Whoever judges whether the output "contains the confabulated
  content" must not know which condition produced it.

**Watch out for.** Injection at one layer with the wrong scale produces
degenerate output — repetition loops, or the CJK failure mode documented in
`CLAUDE.md`. Establish the range where generation stays coherent *before*
interpreting anything.

---

## 4. Fixing what is in INCONCLUSIVE.md

Both discarded experiments in [INCONCLUSIVE.md](INCONCLUSIVE.md) failed for the
same reason: they judged latents against the **whole source document**, when an
activation sampled at one token position is not a claim about the whole document.

The repair is the same for both — compare against the **local context window**
around the sampled position instead, and put the prompt through the bake-off in
[METHODOLOGY.md](METHODOLOGY.md) rather than trusting a plain yes/no. For the
composition analysis, additionally build a hand-labelled positive control, since
a null result from an unvalidated instrument cannot be distinguished from an
instrument that cannot detect the effect.

---

## 5. Everything the current results cannot separate

Stated as open questions rather than limitations, because each is answerable:

- **Prior versus channel.** 54% of latents the round trip preserves were never
  visibly conveyed by the explanation (§4). Separating "the AR inferred it" from
  "the judge under-detected it" would need an AR trained independently of the AV,
  which the released checkpoints do not provide — or a judge validated against
  human-labelled ground truth on the same pairs.
- **Granularity versus dictionary.** §2 compares `l0_small` and `l0_big` as if
  they differed only in sparsity. They are separately trained dictionaries with
  different thresholds and reconstruction quality. Sweeping several widths at
  fixed L0, or several L0s at fixed width, would separate the two.
- **n = 50, one model, one layer.** The cheapest generalisation is other layers of
  the same model, since Gemma Scope 2 covers all 48 and the NLA layer-sensitivity
  question is one the paper names as open.
