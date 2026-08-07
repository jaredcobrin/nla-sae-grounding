"""Which parts of an NLA explanation can be trusted?

Runs one activation through the NLA round trip, reads both ends with a sparse
autoencoder, and reports what the explanation is actually evidenced by.

  CONFIRMED   in the real activation, AND the AR recovers it from the explanation
  UNVERIFIED  the AR produces it from the explanation, but it is NOT in the
              real activation at this position
  OMITTED     in the real activation, but the AR does not recover it

NOTE ON WHAT THESE ACTUALLY MEASURE. The explanation text is never read here.
The buckets are set arithmetic on SAE feature sets:

    CONFIRMED = F_orig & F_ar     UNVERIFIED = F_ar - F_orig
    OMITTED   = F_orig - F_ar     where F_ar = SAE(AR(explanation))

So the explanation enters only THROUGH THE AR'S RECONSTRUCTION OF IT. Saying
"the explanation implies X" would attribute to the text what belongs to the AR,
and that distinction is the whole premise of this project: the AR trains on the
AV's own rollouts, so it fills in context the explanation never stated. Wording
that blurs this hides the confound the SAE exists to expose.

For a check that DOES read the explanation, see judge_explanations.py, which
shows the text to a model and asks whether it covers each feature.

UNVERIFIED IS NOT "FALSE" AND THE REPORT MUST NEVER SAY IT IS. It means the
feature is in the AR's reconstruction and was not found in the original -- which
is by construction "not checked", not "refuted". Two further reasons not to read
it as "invented":

  * The SAE reconstructs the AR's output BETTER than a real activation (FVE 0.700
    vs 0.587, and it needs fewer features to do it: L0 101 vs 120). The two sides
    of the subtraction are not read with equal sensitivity, so a feature may be
    present in the original and simply invisible to the SAE there.
  * An SAE is incomplete. Absence of a feature is weak evidence of absence of the
    thing -- a limitation the NLA paper names about its own method.

An earlier version cited "65-68% of unverified content features are genuinely in
the source document". THAT CLAIM IS WITHDRAWN -- see INCONCLUSIVE.md. It came
from a plain yes/no judge that had never been through the matcher bake-off, and
it compared features against the WHOLE DOCUMENT when an activation sampled at one
token position is not a claim about the whole document.

WHY THE NUMBERS ARE COMPUTED AND ONLY THE PROSE IS GENERATED
Feature sets, counts and coverage come from vector arithmetic and integer set
overlap -- no model judgement anywhere. A language model writes only the closing
paragraph, and the report marks that paragraph as generated. This split is
deliberate: over this project three separate LLM-judge designs produced
confident, plausible, wrong numbers, and each was caught only by a control. The
numbers here have no judge in them to be wrong.

GEMMA ONLY. The SAE was fine-tuned on Gemma-generated chat. On out-of-
distribution text the same pipeline measured a 7-point effect where Gemma
rollouts gave 25, so the tool refuses unfamiliar corpora unless overridden.

Usage:
    # your own text -- the activation is taken at its LAST token
    python src/trust_report.py --text "The Ryzen 7600 idles at 45C." \
        --av <av_path> --ar <ar_path>

    # or activations sampled from a corpus built by extract_activations.py
    python src/trust_report.py --parquet acts_rollout50_L32.parquet \
        --av <av_path> --ar <ar_path> --n 10 --out reports/
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import re
import sys
from pathlib import Path

import numpy as np
import torch
import yaml
from safetensors.torch import load_file

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
# nla_inference.py and the nla/ package come from the upstream NLA repo
# (kitft/natural_language_autoencoders). Point NLA_REPO at a clone of it, or
# place this repo inside one. nla_av.py and sampling.py are vendored here
# because this fork modified them -- nla_av.py in particular carries the Gemma
# embed-scale fix (see its docstring).
_UP = os.environ.get("NLA_REPO") or str(_HERE.parent.parent)
sys.path.insert(0, _UP)

from nla_av import AVRunner                                    # noqa: E402
from sampling import load_vectors                                 # noqa: E402
from nla.schema import load_predict_mean_baselines                    # noqa: E402
from nla_inference import NLACritic                                   # noqa: E402

from hf_paths import sae_variant_dir, L0_SMALL  # noqa: E402
SAE_VARIANT = L0_SMALL     # sparse enough to be labelable:
# l0_big runs L0~129 with token purity 0.17 and its labels cannot be told from
# wrong ones (AUC gap +0.008 vs l0_small's +0.092).

# If injection silently fails the AV describes the marker char and free-
# associates in CJK. Loudest smoke test for the whole injection path.
_CJK = re.compile(r"[　-鿿豈-﫿＀-￯]")

# ONLY CONFIRMED AND UNVERIFIED GO IN. Omitted features are things the
# explanation never said, so they say nothing about whether what it DID say can
# be trusted -- a different question, and including them invites the model to
# grade the explanation on coverage instead of on reliability. They stay in the
# report as their own section, out of this prompt.
_PROSE = """You are writing the closing paragraph of a report on how far a model's
explanation of a neural activation can be relied on.

THE EXPLANATION UNDER REVIEW:
{expl}

Independently, a sparse autoencoder read the activation directly. Every claim
the explanation makes falls into one of two groups.

CONFIRMED — the activation really contains these, and a reconstructor reading
the explanation recovers them:
{confirmed}

UNVERIFIED — a reconstructor reading the explanation produces these, but they
were NOT found in the activation at this position:
{unverified}

Write one paragraph, 4-6 sentences, telling a reader what to rely on.

Rules you must follow:
- UNVERIFIED means NOT CHECKED, never false. It means the reconstructor produced
  the feature and the sparse autoencoder did not find it in the activation --
  which can happen because the feature is absent, OR because the autoencoder
  cannot see it there. Never call an unverified claim wrong, invented, or a
  hallucination.
- Name concretely what is confirmed and what is not. Do not summarise the
  explanation back; assess it.
- If a group is empty or rests on very few features, say the evidence is thin
  rather than drawing a conclusion from it.
- Judge only reliability. Do NOT comment on what the explanation left out.
- Plain prose. No headings, no bullet points, no preamble."""


def sae_encode(V, P):
    """Gemma Scope JumpReLU. b_dec is added on DECODE only -- subtracting it from
    the input destroys the signal (measured cos 0.31 vs 0.99)."""
    pre = V @ P["w_enc"] + P["b_enc"]
    return torch.where(pre > P["threshold"], pre, torch.zeros_like(pre))


def _auto_label_batch() -> int:
    """Pick a labelling batch size that fits the card.

    MEASURED, not guessed: on a 46GB L40S with batch=6 the peak was 45,481 MiB
    -- 98.7% of the card. Model weights are only ~23GB; the rest is KV cache for
    batch x N_CAND (=3) concurrent ~2000-token generations. So the binding
    constraint is the batch, not the model, and a 40GB card OOMs at the default.
    """
    if not torch.cuda.is_available():
        return 2
    gb = torch.cuda.get_device_properties(0).total_memory / 1024 ** 3
    return 6 if gb >= 70 else 3 if gb >= 44 else 2 if gb >= 30 else 1


def label_missing(need, cache, model, tok, sae_variant, seed=0, batch=None):
    """Label features this run needs but the cache has never seen.

    WHY THIS HAS TO EXIST: an activation the tool has not run before fires
    features nobody has labelled. Without this the report can only NAME the
    features that happen to be in the shipped cache -- the first run scored 31%
    coverage for exactly this reason, because it sampled different rows than the
    labelling run had.

    It reuses label_features.py rather than reimplementing a quick version. That
    module's pipeline is the validated one: three candidate labels from whole
    exemplar passages with quantised strengths, the winner chosen on one held-out
    band, then REPORTED on a second disjoint band, and kept only if it beats the
    95th percentile of a null built by scoring each quiz with a DIFFERENT
    feature's label. A cheaper labeller here would silently reintroduce the
    failure that pipeline exists to prevent -- an earlier version could not tell
    a correct label from a wrong one (0.604 vs 0.557).

    The null is POOLED with the cache's existing nulls before the threshold is
    recomputed, so calibration does not drift as the cache grows.
    """
    import label_features as LF
    if not need:
        return cache, 0
    if batch is None:
        batch = _auto_label_batch()
        gb = (torch.cuda.get_device_properties(0).total_memory / 1024 ** 3
              if torch.cuda.is_available() else 0)
        print(f"[label] batch={batch} (auto, for a {gb:.0f}GB card)")
    print(f"[label] {len(need)} features in this run have never been labelled")
    X = load_file(str(sae_variant_dir(sae_variant)
                       / "examples.safetensors"))
    YES = [tok.encode(s, add_special_tokens=False)[0] for s in ("Yes", " Yes", "yes")]
    NO = [tok.encode(s, add_special_tokens=False)[0] for s in ("No", " No", "no")]
    cats = ", ".join(LF.CATEGORIES)
    pool = [v["label"] for v in cache.values() if v.get("label")]
    todo = sorted(need)

    for b0 in range(0, len(todo), batch):
        chunk = todo[b0:b0 + batch]
        prompts, owner = [], []
        for f in chunk:
            rng = np.random.default_rng(seed * 100003 + f)
            ps = LF.passages(f, X, tok, 0, LF.GEN_TOP, LF.N_GEN_PASSAGES, rng)
            ng = LF.neg_snips(f, X, tok, rng, 2)
            promoted = [tok.decode([int(t)]) for t in X["top_tokens"][f][:10]]
            p = LF._GEN_PROMPT.format(passages="\n".join(ps),
                                      neg="\n".join(f"  {s}" for s in ng),
                                      promoted=", ".join(repr(x) for x in promoted),
                                      fewshot=LF._FEWSHOT, cats=cats)
            prompts += [p] * LF.N_CAND
            owner += [f] * LF.N_CAND
        outs = LF.batch_gen(model, tok, prompts, 120, temp=0.9)

        cands = {}
        for f, txt in zip(owner, outs):
            m_l = re.search(r"EXPLANATION:\s*(.+)", txt)
            if not m_l:
                continue
            m_c = re.search(r"CATEGORY:\s*([a-z_,\s]+)", txt, re.I)
            cs = [c.strip().lower() for c in (m_c.group(1) if m_c else "").split(",")]
            cs = [c for c in cs if c in LF.CATEGORIES][:2] or ["other"]
            m_n = re.search(r"CONTENT:\s*(.+)", txt)
            content = (m_n.group(1).strip().strip('"')[:140] if m_n else "")
            if re.fullmatch(r"none\.?", content.strip(), re.I):
                content = ""
            lab = m_l.group(1).strip().strip('"')[:120]
            if lab:
                cands.setdefault(f, [])
                if not any(lab == c[0] for c in cands[f]):
                    cands[f].append((lab, cs, content))

        # select on band 1
        jobs, key = [], []
        for f in chunk:
            q = LF.build_quiz(f, X, tok, LF.SELECT_LO, LF.SELECT_HI,
                              np.random.default_rng(seed * 7919 + f),
                              LF.N_SEL_POS, LF.N_SEL_NEG)
            if q is None:
                continue
            for lab, cs, ct in cands.get(f, []):
                jobs.append((lab, q)); key.append((f, lab, cs, ct))
        sel = LF.score_labels(model, tok, jobs, YES, NO)
        best = {}
        for (f, lab, cs, ct), s in zip(key, sel):
            if f not in best or s > best[f][-1]:
                best[f] = (lab, cs, ct, s)

        # report on band 2 (disjoint), plus this feature's own null
        jobs, key, kind = [], [], []
        for f, (lab, cs, ct, _) in best.items():
            rng = np.random.default_rng(seed * 104729 + f)
            q = LF.build_quiz(f, X, tok, LF.REPORT_LO, LF.REPORT_HI, rng)
            if q is None:
                continue
            jobs.append((lab, q)); key.append(f); kind.append("real")
            others = [l for l in pool if l != lab]
            for wrong in (rng.choice(others, min(LF.N_NULL, len(others)), replace=False)
                          if others else []):
                jobs.append((str(wrong), q)); key.append(f); kind.append("null")
        rep = LF.score_labels(model, tok, jobs, YES, NO)
        real, null = {}, {}
        for f, k, s in zip(key, kind, rep):
            if k == "real":
                real[f] = s
            else:
                null.setdefault(f, []).append(s)

        for f in chunk:
            lab, cs, ct, _ = best.get(f, ("", ["other"], "", None))
            if lab:
                pool.append(lab)
            cache[str(f)] = {"label": lab, "categories": cs, "content": ct,
                              "promoted": [tok.decode([int(t)]) for t in X["top_tokens"][f][:8]],
                              "auc": real.get(f), "auc_null": null.get(f, [])}
        print(f"    {min(b0 + batch, len(todo))}/{len(todo)}")

    # recalibrate on the POOLED null so the bar does not drift as the cache grows
    nulls = [s for v in cache.values() for s in v.get("auc_null", [])]
    thr = float(np.percentile(nulls, 95)) if nulls else 0.756
    for v in cache.values():
        v["reliable"] = (v.get("auc") or 0) >= thr
    n_ok = sum(1 for f in todo if cache[str(f)].get("reliable"))
    print(f"[label] threshold {thr:.3f} (95th pct of {len(nulls)} wrong-label scores); "
          f"{n_ok}/{len(todo)} new labels passed")
    return cache, len(todo)


def activation_from_text(text: str, layer: int, device: str,
                         base: str = "google/gemma-3-12b-it"):
    """Extract one activation from the user's own text, at the LAST token.

    The whole-corpus path samples random positions inside a generated assistant
    response. Here the user supplies the text, so the position is fixed at the
    final token -- that is the one they can actually reason about ("what was the
    model representing when it had just read this?"), and it needs no sampling
    rule to explain.

    Loaded and released inside this function: the base model is a third 12B model
    and must not be resident while the AV or AR is.

    NOTE ON DISTRIBUTION: the SAE was fine-tuned on Gemma-generated chat. Text
    from anywhere else is out-of-distribution for it, and the same pipeline
    measured a 7-point effect on FineWeb where Gemma rollouts gave 25. The report
    says so in its header when this path is used.
    """
    import gc
    from transformers import AutoTokenizer
    from nla.arch_adapters import resolve_text_model

    tok = AutoTokenizer.from_pretrained(base)
    model, _ = resolve_text_model(base, dtype=torch.bfloat16)
    model = model.to(device).eval()
    try:
        # Chat-templated, because that is the shape the SAE and the NLA both saw.
        conv = [{"role": "user", "content": text}]
        ids = tok(tok.apply_chat_template(conv, tokenize=False),
                  return_tensors="pt", add_special_tokens=False).input_ids.to(device)
        with torch.no_grad():
            hs = model(ids, output_hidden_states=True).hidden_states
        # --layer-index L == hidden_states[L+1]; index 0 is the embedding output.
        v = hs[layer + 1][0, -1].float().cpu()
    finally:
        del model
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    return v.unsqueeze(0), [0], [text]


def check_corpus(parquet: str, force: bool) -> str | None:
    """The SAE was fine-tuned on Gemma-generated chat; other corpora degrade it."""
    side = Path(parquet + ".nla_meta.yaml")
    corpus = ""
    if side.exists():
        meta = yaml.safe_load(side.read_text()) or {}
        corpus = str(meta.get("extraction", {}).get("corpus", ""))
    ok = "oasst" in corpus.lower() or "rollout" in corpus.lower() or "gemma" in corpus.lower()
    if ok:
        return None
    msg = (f"corpus is {corpus!r}, not the Gemma-generated rollouts this SAE was "
           f"fine-tuned on. On out-of-distribution text the same pipeline measured "
           f"a 7-point effect where Gemma rollouts gave 25.")
    if not force:
        print(f"\nREFUSING TO RUN: {msg}")
        print("Re-run with --i-know-what-im-doing to proceed with a warning banner.")
        sys.exit(2)
    return msg


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--parquet", help="a corpus built by extract_activations.py")
    src.add_argument("--text", help="your own text; the activation is taken at its "
                                    "LAST token. Out-of-distribution for the SAE "
                                    "unless it reads like Gemma chat output")
    ap.add_argument("--av", required=True)
    ap.add_argument("--ar", required=True)
    ap.add_argument("--labels", default="results/feature_labels.json",
                    help="validated labels; the shipped cache is the default")
    ap.add_argument("--layer", type=int, default=32,
                    help="--layer L == hidden_states[L+1]; 32 is what the NLA "
                         "checkpoints and the SAE were both built for")
    ap.add_argument("--n", type=int, default=10, help="activations to report on")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-list", type=int, default=12, help="features shown per section")
    ap.add_argument("--writer", default="google/gemma-3-12b-it",
                    help="model that writes the closing paragraph. MUST NOT be the "
                         "AV: the AV is fine-tuned to emit explanations in one fixed "
                         "format ('Final token X opens a clause requiring Y') and "
                         "reproduces that format instead of assessing anything.")
    ap.add_argument("--label-batch", type=int, default=None,
                    help="labelling batch size. Default auto-sizes to the card: "
                         "the peak is KV cache for batch x 3 concurrent long "
                         "generations, not model weights. Lower it if you OOM.")
    ap.add_argument("--no-label", action="store_true",
                    help="do not label unseen features; they are counted but unnamed")
    ap.add_argument("--no-prose", action="store_true",
                    help="skip the generated paragraph; the computed tables stand alone")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--i-know-what-im-doing", action="store_true")
    ap.add_argument("--out", default="trust_reports",
                    help="directory for the generated reports")
    a = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)

    warn = (check_corpus(a.parquet, a.i_know_what_im_doing) if a.parquet else
            "activation taken from user-supplied text at its last token. The SAE "
            "was fine-tuned on Gemma-generated chat, so unless this text reads "
            "like that, it is out-of-distribution and the latent sets are less "
            "reliable than the numbers in RESULTS.md.")

    CACHE = json.loads(Path(a.labels).read_text())
    print(f"[labels] cache has {len(CACHE)} features, "
          f"{sum(1 for v in CACHE.values() if v.get('reliable'))} validated")

    P = load_file(str(sae_variant_dir(SAE_VARIANT)
                       / "params.safetensors"))

    if a.text:
        # Phase 0: the base model, loaded and released before the AV appears.
        print("\n[phase 0] extracting an activation from your text")
        V, row_idx, txt = activation_from_text(a.text, a.layer, a.device)
        print(f"[data] 1 activation at the last token of {len(a.text)} chars")
    else:
        V, row_idx, _ = load_vectors(a.parquet, a.n, a.seed)
        import pyarrow.parquet as pq
        txt = pq.ParquetFile(a.parquet).read(
            columns=["detokenized_text_truncated"]).column(0).to_pylist()
        print(f"[data] {len(V)} activations from {a.parquet}")

    A_orig = sae_encode(V, P)

    # ---- PHASE 1: verbalize. AV only. ----
    # THREE 12B MODELS ARE INVOLVED AND NONE OF THEM OVERLAP.
    # Holding the AV and AR together needs ~48GB, which does not fit a 46GB
    # L40S -- and holding all three needs ~72GB. Running them in phases keeps
    # the peak at ONE model (~24GB), so the whole tool fits a 24GB card.
    # Nothing is lost by doing this: the AV never needs the AR's output, and
    # the explanations are just text.
    print("\n[phase 1/3] verbalizing with the AV")
    av = AVRunner(a.av, device=a.device)
    expls = []
    for i in range(len(V)):
        torch.manual_seed(a.seed * 1000 + i)
        e = av.generate(V[i], temperature=1.0,
                                    explanation_max_tokens=200, do_sample=True)
        if e and _CJK.search(e):
            print(f"  act {i}: WARNING — CJK in output, injection may have failed")
        if not e:
            print(f"  act {i}: AV produced no explanation")
        expls.append(e)
    del av
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    print(f"  {sum(1 for e in expls if e)}/{len(expls)} explanations; AV released")

    # ---- PHASE 2: reconstruct. AR only. ----
    print("\n[phase 2/3] reconstructing with the AR")
    critic = NLACritic(a.ar, device=a.device)
    _, rawvar = load_predict_mean_baselines(a.parquet, critic.mse_scale)
    recon = []
    for i, e in enumerate(expls):
        if not e:
            recon.append(None)
            continue
        v_ar = critic.reconstruct(e).float()
        mse, cos = critic.score(e, V[i])
        recon.append((v_ar, mse, cos))
    del critic
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    print(f"  {sum(1 for r in recon if r)} reconstructions; AR released")
    reports = []
    for i in range(len(V)):
        expl = expls[i]
        if not expl or recon[i] is None:
            continue
        v_ar, mse, cos = recon[i]
        A_ar = sae_encode(v_ar.unsqueeze(0), P)[0]

        F_o = set(torch.nonzero(A_orig[i]).flatten().tolist())
        F_a = set(torch.nonzero(A_ar).flatten().tolist())
        sets = {"confirmed": F_o & F_a, "unverified": F_a - F_o, "omitted": F_o - F_a}
        # strengths are kept so features can be ranked once labels exist; naming
        # happens after the on-demand labelling pass below
        strength = {k: {f: float(A_ar[f] if k == "unverified" else A_orig[i][f])
                        for f in s_} for k, s_ in sets.items()}
        rec = {"index": i, "row": int(row_idx[i]), "explanation": expl,
               "fve": 1.0 - mse / rawvar, "cos": cos,
               "source_text": (txt[int(row_idx[i])] or "")[-1500:],
               "_sets": sets, "_strength": strength}
        reports.append(rec)
        print(f"  act {i}: FVE {rec['fve']:+.3f}  confirmed {len(sets['confirmed']):>3}"
              f"  unverified {len(sets['unverified']):>3}"
              f"  omitted {len(sets['omitted']):>3}")

    # ---- PHASE 3: label unseen features + write prose. Base model only. ----
    print("\n[phase 3/3] labelling and writing")
    from transformers import AutoModelForCausalLM, AutoTokenizer
    wtok = AutoTokenizer.from_pretrained(a.writer)
    wtok.padding_side = "left"
    if wtok.pad_token_id is None:
        wtok.pad_token = wtok.eos_token
    wmodel = AutoModelForCausalLM.from_pretrained(
        a.writer, dtype=torch.bfloat16).to(a.device).eval()

    fired = {f for r in reports for k in r["_sets"] for f in r["_sets"][k]}
    missing = {f for f in fired if str(f) not in CACHE}
    if missing and not a.no_label:
        CACHE, n_new = label_missing(missing, CACHE, wmodel, wtok, SAE_VARIANT,
                                      seed=a.seed, batch=a.label_batch)
        Path(a.labels).write_text(json.dumps(CACHE, indent=2))
        print(f"[labels] cache updated and written back to {a.labels}")
    elif missing:
        print(f"[labels] {len(missing)} features unlabelled and --no-label set; "
              f"they will be counted but not named")

    lab = {int(k): v for k, v in CACHE.items() if v.get("reliable") and v.get("label")}
    for r in reports:
        named = {k: sorted((f for f in s_ if f in lab),
                            key=lambda f: -r["_strength"][k].get(f, 0.0))
                 for k, s_ in r["_sets"].items()}
        r["counts"] = {k: {"total": len(s_), "named": len(named[k])}
                        for k, s_ in r["_sets"].items()}
        r["features"] = {k: [{"id": f, "label": lab[f]["label"],
                               "categories": lab[f]["categories"]}
                              for f in named[k][:a.max_list]] for k in r["_sets"]}
        del r["_sets"], r["_strength"]

    # ---- closing prose, the only generated part ----
    def render(k, r):
        f = r["features"][k]
        if not f:
            return "  (none with a validated label)"
        extra = r["counts"][k]["total"] - r["counts"][k]["named"]
        s = "\n".join(f"  - {x['label']}" for x in f)
        return s + (f"\n  (plus {extra} further features that could not be named)"
                    if extra else "")

    if a.no_prose:
        for r in reports:
            r["assessment"] = None
        print("\n[prose] skipped (--no-prose)")
    else:
        print(f"\n[prose] writing closing paragraphs with {a.writer}")

        # confirmed + unverified only -- see the note on _PROSE
        prompts = [_PROSE.format(expl=r["explanation"],
                                  confirmed=render("confirmed", r),
                                  unverified=render("unverified", r)) for r in reports]
        # A SEPARATE BASE MODEL, never the AV. The AV is fine-tuned to one output
        # format and, asked to assess, simply reproduces it -- the first version of
        # this script used av.model and every assessment came back as
        # "Final token 'experience' opens a clause requiring...", which assesses
        # nothing. The AR is equally unsuitable for the same reason.
        tok, model = wtok, wmodel
        for i in range(0, len(prompts), 4):
            texts = [tok.apply_chat_template([{"role": "user", "content": p}], tokenize=False,
                                              add_generation_prompt=True)
                     for p in prompts[i:i + 4]]
            enc = tok(texts, return_tensors="pt", padding=True,
                      add_special_tokens=False).to(model.device)
            with torch.no_grad():
                g = model.generate(**enc, max_new_tokens=260, do_sample=False,
                                   pad_token_id=tok.pad_token_id or tok.eos_token_id)
            for j, row in enumerate(g):
                reports[i + j]["assessment"] = tok.decode(
                    row[enc["input_ids"].shape[1]:], skip_special_tokens=True).strip()

    # ---- write ----
    for r in reports:
        c = r["counts"]
        tot = sum(x["total"] for x in c.values())
        named = sum(x["named"] for x in c.values())
        md = [f"# Trust report — activation {r['index']} (parquet row {r['row']})", ""]
        if warn:
            md += [f"> **WARNING — {warn}** Results are not reliable.", ""]
        md += [f"Reconstruction FVE `{r['fve']:+.3f}` · cosine `{r['cos']:.4f}`", "",
               "## The explanation under review", "", "> " + " ".join(r["explanation"].split()), "",
               "## Verdict", "",
               "| | features | named |", "|---|---:|---:|",
               f"| **CONFIRMED** — in the activation, and the AR recovers it "
               f"| {c['confirmed']['total']} | {c['confirmed']['named']} |",
               f"| **UNVERIFIED** — the AR produces it, but it is not in the activation here "
               f"| {c['unverified']['total']} | {c['unverified']['named']} |",
               f"| **OMITTED** — in the activation, but the AR does not recover it "
               f"| {c['omitted']['total']} | {c['omitted']['named']} |", "",
               "*These are set operations on SAE feature sets — the explanation text "
               "is never read. It enters only through the AR's reconstruction of it.*", ""]
        md += [
               f"*{named} of {tot} features ({100*named//max(1,tot)}%) have a validated label "
               f"and can be named. The rest are counted only.*", ""]
        for k, title in (("confirmed", "Confirmed"), ("unverified", "Unverified"),
                          ("omitted", "Omitted")):
            md += [f"### {title}", ""]
            md += ([f"- `f{x['id']}` {x['label']}" for x in r["features"][k]]
                   or ["- *(none with a validated label)*"])
            extra = c[k]["total"] - c[k]["named"]
            if extra:
                md += [f"- *(plus {extra} further features that could not be named)*"]
            md += [""]
        md += ["## Assessment", "",
               "*Written by a language model from the CONFIRMED and UNVERIFIED lists "
               "only — omitted features are excluded, since they concern what the "
               "explanation left out rather than whether what it said holds up. The "
               "counts and lists above are computed; only this paragraph is generated.*",
               "",
               r.get("assessment") or "*(skipped: --no-prose)*", "",
               "## Source text", "", "```", " ".join(r["source_text"].split())[-1200:], "```", "",
               "---", "",
               "**Unverified is not false.** A feature lands here when the AR's "
               "reconstruction contains it and the original activation does not appear to. "
               "Two reasons that is weaker than it sounds: the SAE reconstructs the AR's "
               "output better than a real activation (FVE 0.700 vs 0.587), so it reads the "
               "two sides with unequal sensitivity; and an SAE is incomplete, so a missing "
               "feature is weak evidence. Treat unverified as *not checked*, never as "
               "*refuted*.", ""]
        (out / f"activation_{r['index']:03d}.md").write_text("\n".join(md))

    (out / "summary.json").write_text(json.dumps(
        {"config": vars(a), "corpus_warning": warn, "reports": reports}, indent=2))
    tot = {k: sum(r["counts"][k]["total"] for r in reports)
           for k in ("confirmed", "unverified", "omitted")}
    n = sum(tot.values())
    print(f"\nwrote {len(reports)} reports to {out}/")
    print(f"  overall: confirmed {100*tot['confirmed']//max(1,n)}%  "
          f"unverified {100*tot['unverified']//max(1,n)}%  "
          f"omitted {100*tot['omitted']//max(1,n)}%")


if __name__ == "__main__":
    main()
