# Future work

Everything in [RESULTS.md](RESULTS.md) is **correlational** — it measures which
latents co-occur with which text, never whether any of it is load-bearing. These
are ordered by how much they change that; the last one is causal.

**Most need no new GPU time.** `roundtrip.py` saves every vector family to
`feature_overlap_vectors.npz` for exactly this reason:

| array | shape | |
|---|---|---|
| `v_orig` | [50, 3840] | the sampled activations |
| `v_orig_sae` | [50, 3840] | SAE reconstruction of each |
| `v_ar` | [250, 3840] | the AR's output per explanation |
| `v_ar_sae` | [250, 3840] | SAE reconstruction of each of those |

`v_orig_sae` is the useful one: it lets the SAE's own reconstruction error be
subtracted out, so an effect can be attributed to the AR rather than to SAE
lossiness. `feature_overlap.json` additionally carries per-latent activation
strengths for the 50 originals. The AR outputs' strengths are not stored, but
`v_ar` is in the `.npz`, so they are one encode away.

---

## 0. Does C > A hold at `l0_small`? (minutes of CPU)

`RESULTS.md` §1 measures the SAE reconstructing the AR's output better than a real
activation — but **only at `l0_big`**. §3 and the tool run on `l0_small`, where
`refeature.py` saves latent sets without reconstruction scores, so the caveat is
currently carried across that boundary untested. Encode and decode `v_orig` and
`v_ar` under `l0_small` and report cosine and L0.

Checked: no artefact in this repo or any earlier run carries it. It has to be
computed.

---

## 1. Give each bucket a direction

A latent is currently just an integer. But the SAE reconstruction is a **linear**
sum of decoder vectors weighted by activation strength, so each bucket can be
turned back into a direction in activation space:

```
d_bucket = Σ acts[f] · w_dec[f]   for f in bucket
```

The three sum to the SAE's reconstruction, so this is a genuine decomposition.

Every bucket comparison in this repo is a **count**. Directions allow geometric
questions instead: how large is `d_lost` against `d_shared` (losing five marginal
latents is not the same as losing five strong ones, and counts cannot tell them
apart); what is the angle between `d_made` and `d_shared`; and — most interesting
— **is `d_made` consistent across activations?** A shared direction would suggest
a systematic bias in the AR rather than per-example noise.

**Watch:** decoder vectors are not orthogonal, so the directions are not
independent components and their norms are not additive. Latent strengths are also
not comparable across latents without normalisation.

---

## 2. Read the residual through the unembedding

Take the direction the AR got wrong, `δ = v_ar − v_orig`, and push it through the
model's unembedding to see which tokens it promotes and suppresses.

This turns an abstract error vector into something readable — and crucially it
does **not** route through a language-model judge, which is where three separate
measurements in this project went wrong.

**Watch:** layer 32 of 48, so the unembedding is a rough proxy — 16 more layers
act on that direction before logits. Subtract the SAE's own error first, using
`v_orig_sae`, or you will read SAE lossiness as an AR effect. And Gemma-3 applies
a √d embed scale — see the note in `src/nla_av.py`.

---

## 3. The causal one: steer with it

Add `δ` (or `d_made`) back into Gemma at layer 32 during a normal forward pass and
see what changes in the generated text.

**This is the most valuable item here**, because everything in `RESULTS.md` is
correlational. Steering asks whether the direction *does* anything. If adding
`d_made` makes the model produce the content the AV confabulated, the AR's
addition is a real functional direction rather than a reconstruction artefact. If
nothing happens, it is noise. **Both outcomes are informative.**

**The controls this needs, without which it proves nothing:** a **norm-matched
random direction** (injecting any large vector perturbs generation); a **scale
sweep** rather than one hand-picked value; the **SAE error direction**
(`v_orig_sae − v_orig`) as a second control, so the result is about the AR and not
about perturbation in general; and **blind scoring**, so whoever judges the output
does not know which condition produced it.

**Watch:** wrong injection scale gives degenerate output — repetition loops, or
the CJK failure mode. Establish the coherent range before interpreting anything.

---

## 4. What the current results cannot separate

- **Prior versus channel.** 52.6% of latents the round trip preserves were never
  visibly conveyed by the explanation. Separating "the AR inferred it" from "the
  judge under-detected it" needs an AR trained independently of the AV, which the
  released checkpoints do not provide.
- **Granularity versus dictionary.** §2 compares `l0_small` and `l0_big` as if
  they differed only in sparsity; they are separately trained dictionaries.
  Sweeping several widths at fixed L0 would separate the two.
- **n = 200, one layer.** The cheapest generalisation is other layers of the same
  model — Gemma Scope 2 covers all 48, and layer sensitivity is a limitation the
  NLA paper names as open.
- **Both experiments in [INCONCLUSIVE.md](INCONCLUSIVE.md)**, which need the
  local context window rather than the whole document, and a bake-off for their
  prompt.
