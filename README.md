# Evaluating the Legitimacy of Natural Language Autoencoder Explanations Using Sparse Autoencoders

**For the write up, visit [NLA_SAE_Evaluation_Write_Up.pdf](NLA_SAE_Evaluation_Write_Up.pdf).**

Jared Cobrin, September 2026

## TLDR

Natural Language Autoencoders (Fraser-Taliente et al., 2026) take in an
activation, produce an explanation (thoughts) for it through the AV (activation
verbalizer), and then rebuild that activation using the AR (activation
reconstructor). It was found by loops (2026) that reconstruction error increases
significantly when the final paragraph of the NLA explanation is ablated.
Reconstruction, however, is not a good measure of how grounded the text is to the
activation. To test groundedness, I split a set of 200 explanations into three
variants (the first two paragraphs, the final paragraph, and the full
explanation) and did two tests using an SAE (sparse autoencoder):

1. How many of the original activation's SAE latents were recovered by each
   variant's reconstruction.
2. An LLM judge checked which of the original activation's labeled latents
   (features) were stated in each variant's text.

| | Full explanation | First two paragraphs | Final paragraph |
|---|---:|---:|---:|
| FVE | 0.69 | 0.27 | 0.58 |
| Test 1: latents recovered | 70% | 30% | 59% |
| Test 2: features stated in text | 43% | 20% | 42% |

The final paragraph contains a significant amount of grounded content, and the
first two paragraphs seem to have very little grounded content despite being 44%
of the length of the text of the full explanation. The bulk of these findings
heavily relies on the assumption that NLAs and SAEs find a different structure.

**FVE does not predict grounding across explanations.** Among the 188 full
explanations with at least three judged features, the correlation between an
explanation's FVE and the share of its activation's features it states is
r = -0.01 (95% CI -0.16 to 0.13). The top quartile of FVE (mean 0.87) states 43%
of features and the bottom quartile (mean 0.42) also states 43%. FVE cannot be
used to tell how grounded any one explanation is. See Section 4 of the write-up;
the per-activation points are in `results/fve_vs_grounding_points.csv`
(`scripts/fve_vs_grounding_points.py`).

## Method

- Gemma-3-12B-IT, layer 32, 200 activations from Gemma Scope 2's example corpus,
  one explanation each, run through the original NLA repo
  ([kitft/natural_language_autoencoders](https://github.com/kitft/natural_language_autoencoders)).
- Each explanation is cut once, at the start of the final paragraph (which always
  begins with "Final token"), into the three variants. Each variant is run
  through the AR.
- SAE: Gemma Scope 2, layer 32, `l0_small` (about 21 latents fire per token).
- **Test 1** uses no text and no judge. A latent counts as recovered if it is
  active in the original activation and still active in the reconstruction.
- **Test 2** labels each latent with an auto interp method, keeps the labels that
  pass validation (1,771 of 3,328, 53%), and has Gemma-3-12B-IT judge whether each
  variant's text states each feature. A baseline of features that did not fire
  was stated only 4.6% of the time.

## Limitations

- The SAE is independent of the NLA, but not a source of ground truth, as a true
  claim may have no matching latent.
- Test 2 covers only 53% of latents, so it is possible that the ones which were
  not validated favour the first two paragraphs.
- Across full explanations, FVE does not predict how many features are stated
  (r = -0.01, 95% CI -0.16 to 0.13, n = 188), so FVE is not a reliable measure of how grounded any given
  explanation is.
- Small sample: one model, one layer, one explanation each, 200 activations.

## Reproducing

Python 3.10 or newer, `transformers<5`, and a GPU with at least 24 GB of VRAM
(the full pipeline was only run on a 46 GB card). Gemma-3-12B-IT is gated, so
accept its licence and run `hf auth login` first.

```bash
git clone https://github.com/jaredcobrin/nla-sae-grounding.git
cd nla-sae-grounding
pip install -r requirements.txt

# upstream NLA code, which this repo uses but does not vendor
git clone https://github.com/kitft/natural_language_autoencoders.git ../nla_upstream
export NLA_REPO=$(cd ../nla_upstream && pwd)

# models (~63GB). HF_HOME should point at a disk with room for them
export AV=$(hf download kitft/nla-gemma3-12b-L32-av)
export AR=$(hf download kitft/nla-gemma3-12b-L32-ar)
hf download google/gemma-3-12b-it
python -c "from huggingface_hub import snapshot_download as d; \
  d('google/gemma-scope-2-12b-it', allow_patterns=[\
  'resid_post_all/layer_32_width_16k_l0_small/*',\
  'resid_post_all/layer_32_width_16k_l0_big/*'])"

bash scripts/run_experiment.sh    # ~5h, mostly corpus generation
```

Every number comes out in `results/SUMMARY.md`. The individual stages are in
[src/README.md](src/README.md). `trust_tool/` is a small chat app that shows the
same checks on each turn of a conversation.

## Credit

The NLA is not mine. The verbalizer, reconstructor, injection mechanism and
training code are
[kitft/natural_language_autoencoders](https://github.com/kitft/natural_language_autoencoders)
(Copyright 2026 Anthropic PBC, Apache-2.0), and the SAE is Google's Gemma Scope 2.
`src/nla_av.py` is derived from upstream and modified. The rest is mine. See
[NOTICE](NOTICE). Apache-2.0.
