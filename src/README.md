# The pipeline

`bash scripts/run_experiment.sh` runs stages 1–5 in order. Each script's
docstring explains what it does and what broke in earlier versions — those notes
are the point, not decoration.

| # | script | does | GPU |
|---|---|---|---|
| 1 | `extract_activations.py` | builds the corpus. `--arm saecorpus` (default) samples Gemma Scope's own shipped chats; `--arm rollout` regenerates them with Gemma instead, which takes hours. **One activation per conversation** — see `--positions-per-doc` | yes |
| 2 | `roundtrip.py` | AV → explanation → AR → reconstruction, SAE on both ends. Saves per-example FVE and cosine for four comparisons, the explanation, the source text, the latent sets, and every vector family. Also runs the **paragraph ablation** (three variants per explanation) and the **near-miss sweep** | yes |
| 3 | `refeature.py` | re-encodes the saved vectors under the other SAE, including the near-miss neighbours. Seconds | no |
| 4 | `label_features.py` | auto-interp: 3 candidates, held-out scoring, wrong-label null | yes |
| 5 | `judge_explanations.py` | per latent, does the explanation cover it? Graded, against two nulls. Judges the two **segments** and derives `full` as their union, so coverage is monotonic | yes |
| — | `example_reports.py` | six single activations written out end to end, from the committed artefacts. No model, no GPU | no |
| 6 | `summarize_results.py` | **every number in `RESULTS.md`** → `summary.json` + `SUMMARY.md`, each section per variant | no |
| — | `explanation_parts.py` | splits an explanation into `full` / `no_final` / `final_only`. Anchored on the paragraph naming the final token — 200/200 on this run | no |
| — | `compare_prompts.py` | scores candidate judge prompts on identical pairs: monotonicity, FPR spread, AUC. How prompt A was chosen | yes |

**The tool lives in [`../trust_tool/`](../trust_tool/)** — a chat window that
reports on every turn, plus the original command-line version over a stored
corpus. It imports `nla_av`, `sampling` and `hf_paths` from here.

**Not part of the experiment**, kept for reference:

| | | |
|---|---|---|
| `matcher_bakeoff.py` | how the stage-5 judge prompt was chosen (METHODOLOGY §4) |
| `classify_features.py` | failed its own control — see [INCONCLUSIVE.md](../INCONCLUSIVE.md) |

## Vendored, and why

`nla_av.py` and `sampling.py` are copied in rather than imported, because this
fork modified them.

**`nla_av.py`** carries the **Gemma embed-scale fix**: `get_input_embeddings()`
returns the embedding *module*, and calling it runs
`Gemma3TextScaledWordEmbedding.forward()`, which **already** multiplies by
`√hidden_size`. Multiplying again made every token embedding 62× too large and
produced repetition loops even with no injection — invisible on Qwen, whose scale
is 1.0.

**`sampling.py`** holds `load_vectors`, the seeded row sampler. Hand-rolled
selection was tried twice and was wrong both times: rows `0..n` gave several
positions of a **single document**, and first-row-per-document systematically
picked the **earliest, least-context** position in each — measured at FVE 0.64
against 0.76 for properly sampled rows.

`nla_inference.py` and the `nla/` package come from the upstream repo
(`kitft/natural_language_autoencoders`). Set `NLA_REPO` to a clone.

## Conventions every script follows

- **Nothing is reported without its null** — any rate that a broken measurement
  could also produce is computed twice, once on real data and once on mismatched,
  and both are printed.
- **The numbers contain no model judgement.** Latent sets, counts and overlaps
  are vector arithmetic and integer set operations. Where a language model is
  used, its output is marked as generated.
- **Nothing is selected on the outcome metric.** An earlier version resampled
  seeds until mean FVE landed in a band — selection on the very quantity being
  reported. It is now a one-shot health check that warns and continues. The
  shipped `results/feature_overlap.json` predates that change and its `gate_log`
  really is a gate log; [`RESULTS.md`](../RESULTS.md) lists it as a limitation.
- **One activation per conversation.** Two positions in one Gemma response share
  nearly all their context and are one cluster, not two samples. `load_vectors`
  takes at most one row per `doc_id`, and `SUMMARY.md` prints the conversation
  count so a clustered sample cannot pass unnoticed.
- **Coverage is stated.** ~50% of latents have a validated label. The rest are
  counted in every total and never named.
