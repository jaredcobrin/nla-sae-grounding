"""Auto-interp every SAE feature that fired in any feature_overlap run.

WHY LABELS NEED SCORING
"40% of features change through the AV->AR round trip" says nothing about WHAT
changes. Labels turn that into "which KINDS of thing survive", which is the
usable form of the question. But a generated label is a hypothesis, not a
measurement. The auto-interp literature (Bills et al. 2023; EleutherAI /
Neuronpedia) is built around that: GENERATE an explanation, then SCORE it on
held-out data. Category counts computed from unscored labels inherit their
errors silently.

This project has already been burned by exactly that. An earlier labeller called
a feature promoting 'polygonal/tetragonal/globular' a "Software code, likely
JavaScript" feature. It was not hallucinating — it faithfully summarised
exemplars that genuinely contradicted the feature's own promoted tokens. No
inspection of the label alone would have caught it. A scorer does.

THE CONTROL THAT REBUILT THIS FILE
Version 1 reported 0.596 balanced accuracy, 33% "reliable". Then the obvious
control: score each label against a DIFFERENT feature's data. A deliberately
WRONG label scored 0.557 against the right label's 0.604 — a gap of +0.047,
not significant at n=24. The scorer could not tell right from wrong, so the
reliability flag measured nothing. Three separate causes, all mine:

  1. NEGATIVES WERE ADVERSARIAL. They were other features' TOP exemplars —
     maximally-activating tokens — while the positives came from ranks 120-300
     and were weak. Negatives often looked MORE feature-like than positives.
     Fixed: uniformly random positions, the EleutherAI fuzzing standard.
  2. ARGMAX THREW AWAY THE SIGNAL. Greedy Yes/No is one bit per item. Fixed:
     logP(Yes)-logP(No) from the first-token logits, scored by AUC.
  3. THE SAE WAS TOO DENSE. l0_big runs L0~129 with token purity 0.17; its
     features are polysemantic and not labelable at any prompt quality. l0_small
     runs L0~21, purity 0.24, and the label-vs-wrong-label gap goes +0.008 ->
     +0.092 on identical prompts.

  Fixes 1+2 together took the gap +0.047 -> +0.122 on l0_big. Fix 3 is why this
  now defaults to l0_small. See refeature.py for why using l0_small HERE and
  l0_big for the reconstruction claim is the conservative choice on both.

RELIABILITY IS CALIBRATED, NOT ASSUMED
Version 1 called a label reliable at bal_acc >= 0.70, a number picked by feel.
Here every feature is ALSO scored with a wrong label, and the pooled
wrong-label AUCs form an empirical null. The threshold is that null's 95th
percentile, so "reliable" means a measured 5% false-positive rate rather than a
threshold chosen to make the coverage look good.

GENERATOR CHOICES (each measured, none free)
A first attempt at fixing quality by prompting alone — reasoning, whole
passages, few-shot, best-of-3 — moved accuracy 0.596 -> 0.609, i.e. nothing.
They are kept because they cost little and help once the SAE is sparse enough
to be labelable, but they were NOT the bottleneck and should not be credited as
the fix.

  1. REASON FIRST. The model states what the marked tokens have in common
     before committing to a label. The largest known gain for small labellers.
  2. WHOLE PASSAGES, NOT ISOLATED HITS. Exemplars are grouped by source
     sequence so one passage shows every token the feature fires on, with
     strengths. Seeing which tokens fire AND which do not, in the same text, is
     far more informative than N disjoint snippets.
  3. FEW-SHOT. Two worked examples, one good and one deliberately vague. Small
     models copy format aggressively; showing the failure mode suppresses it.
  4. BEST-OF-N. Three candidate labels, scored, best one kept. Uses the scorer
     (which works) as a filter on the generator (which is weak).

  THE BIAS THIS WOULD OTHERWISE INTRODUCE: picking a label by its score and then
  reporting that score is selection on the outcome. So the held-out exemplars
  are split into two DISJOINT bands — SELECT_LO..SELECT_HI chooses the winner,
  REPORT_LO..REPORT_HI reports it. The published number never sees the data used
  to select. Without this split, best-of-N inflates the reported accuracy by
  roughly the spread of the candidates.

SCORING is detection ("fuzzing"), not simulation: one yes/no per snippet, which
avoids list-parsing failures and answer-order artefacts, and unlike simulation
is stable on features with few high-activation tokens. Balanced accuracy, so a
model that answers "yes" to everything gets 0.5, not 0.9.

Cached globally by feature id — one SAE serves all three corpora, so feature
1234 means the same thing everywhere and ~40% of features recur. Safe to
interrupt and resume; this pod has reset four times.

Usage:
    python src/label_features.py \
        --dirs results results/rollout \
               results/wildchat \
        --out results/feature_labels.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import torch
from safetensors.torch import load_file
from transformers import AutoModelForCausalLM, AutoTokenizer

from hf_paths import sae_variant_dir, L0_SMALL, L0_BIG  # noqa: E402

CATEGORIES = [
    "syntax",          # function words, connectives, grammatical particles
    "formatting",      # whitespace, punctuation, markup, layout
    "named_entity",    # a specific person, place, organisation, product
    "topic_domain",    # subject matter: medicine, sports, cooking, finance
    "genre_register",  # kind of text: news, forum post, tutorial, review
    "sentiment_tone",  # emotion, politeness, stance, intensity
    "language",        # non-English tokens, translation, multilingual
    "code_technical",  # source code, maths, scientific notation
    "numeric",         # numbers, dates, quantities, ordinals
    "other",
]

N_CAND = 3                      # candidate labels per feature (best-of-N)
N_GEN_PASSAGES = 6              # passages shown to the generator
GEN_TOP = 40                    # generator draws passages from ranks 0..GEN_TOP
SELECT_LO, SELECT_HI = 40, 120  # band that CHOOSES the winning candidate
REPORT_LO, REPORT_HI = 120, 300 # band that REPORTS it — disjoint, so unbiased
N_SEL_POS, N_SEL_NEG = 6, 6     # selection quiz: small, it only has to rank 3 candidates
N_POS, N_NEG = 16, 16           # reporting quiz: 256 pairs, so per-feature AUC is
                                # not quantised into the 9 values an 8-item quiz allows.
                                # At n=24 the measured gap swung +0.122 -> +0.008 between
                                # two feature samples; that noise is what this fixes.
N_NULL = 2                      # wrong labels per feature, to build the empirical null

_FEWSHOT = """Here are two worked examples, so you can see what counts as useful.

GOOD — "fires on the word immediately after an opening parenthesis in citations"
  Specific. Names the token AND the context. You could apply it to new text.

BAD — "fires on text containing punctuation"
  Useless. Almost all text contains punctuation, so this predicts nothing. Never
  write an explanation this broad."""

_GEN_PROMPT = """A feature inside a language model fires on certain tokens. Below are passages
where it fires. Tokens it fires on are marked [[token|strength]] on a 0-10 scale.
Every other token in these passages did NOT make it fire — that contrast is
your main evidence.

{passages}

For contrast, passages where this feature is silent everywhere:
{neg}

Tokens it pushes the model to output next (read from its weights, independent of
the text above):
{promoted}

{fewshot}

Now do the same. Reply in exactly this format:

COMMON: <what do the marked tokens share? one sentence. Consider the token
itself, and what comes immediately before it.>
EXPLANATION: <under 12 words. Name the trigger. Must be specific enough to
predict new text.>
TRIGGER: <the grammatical or positional pattern alone, e.g. "a noun following a
verb" or "sentence-initial". No subject matter.>
CONTENT: <what the surrounding text is ABOUT, when this feature fires — the
subject matter, entities, or tone. e.g. "theft and property crime", "GPU
hardware specifications", "apologetic customer-service register".
Write exactly NONE if the feature is purely grammatical and fires regardless of
what the text is about. NONE is a valid and common answer — do not invent
subject matter that is not there.>
CATEGORY: <one or two of: {cats}; comma-separated only if genuinely two>"""

_SCORE_PROMPT = """A feature inside a language model is described as:
"{label}"

Here is a piece of text with one token marked [[like this]]:
{snip}

Does this feature fire on that marked token? Answer only Yes or No."""


def passages(f, X, tok, lo, hi, k, rng, width=48):
    """Group a feature's exemplars by source sequence and render whole passages.

    A single sequence often contains several of the feature's firing tokens.
    Showing them together — with every non-firing token visible between them —
    lets the labeller see the contrast that defines the feature. Isolated
    one-token snippets hide exactly that.
    """
    acc, sid, pos = X["activations"][f], X["seq_ids"][f], X["positions"][f]
    order = torch.argsort(acc, descending=True)
    amax = float(acc[order[0]]) or 1.0
    by_seq = defaultdict(list)
    for j in order[lo:hi]:
        j = int(j)
        if float(acc[j]) <= 0:
            continue
        by_seq[int(sid[j])].append((int(pos[j]), float(acc[j])))
    if not by_seq:
        return []
    seqs = sorted(by_seq, key=lambda s: -max(a for _, a in by_seq[s]))[:k * 2]
    if len(seqs) > k:
        seqs = [seqs[i] for i in rng.choice(len(seqs), k, replace=False)]

    out = []
    for s in seqs:
        hits = sorted(by_seq[s])
        centre = hits[0][0]
        a, b = max(0, centre - width // 2), min(X["tokens"].shape[1], centre + width // 2)
        seq = X["tokens"][s]
        marks = {p: v for p, v in hits if a <= p < b}
        buf = []
        for p in range(a, b):
            t = tok.decode([int(seq[p])])
            if p in marks:
                buf.append(f"[[{t}|{max(1, min(10, round(10 * marks[p] / amax)))}]]")
            else:
                buf.append(t)
        out.append("  ..." + "".join(buf).replace("\n", " ") + "...")
    return out


def one_snip(f, j, X, tok, width=40):
    s, p = int(X["seq_ids"][f][j]), int(X["positions"][f][j])
    seq = X["tokens"][s]
    a, b = max(0, p - width), min(X["tokens"].shape[1], p + 4)
    pre = tok.decode([int(t) for t in seq[a:p]]).replace("\n", " ")[-200:]
    hit = tok.decode([int(seq[p])])
    post = tok.decode([int(t) for t in seq[p + 1:b]]).replace("\n", " ")[:40]
    return f"...{pre}[[{hit}]]{post}..."


def neg_snips(f, X, tok, rng, n, width=40):
    """Uniformly random positions in random sequences — the fuzzing standard.

    NOT other features' top exemplars. That was the original design and it was
    backwards: those are maximally-activating tokens while the positives come
    from ranks 120-300 and are weak, so the negatives could look MORE
    feature-like than the positives. Switching to random negatives alone moved
    the label-vs-wrong-label gap from +0.047 to +0.078.

    Contamination: with L0~21 of 16384, a random position has ~0.13% chance of
    also firing this feature. Negligible against a 32-item quiz.
    """
    nseq, slen = X["tokens"].shape
    out = []
    for _ in range(n):
        s, p = int(rng.integers(0, nseq)), int(rng.integers(width + 1, slen - 5))
        seq = X["tokens"][s]
        pre = tok.decode([int(t) for t in seq[p - width:p]]).replace("\n", " ")[-200:]
        post = tok.decode([int(t) for t in seq[p + 1:p + 5]]).replace("\n", " ")[:40]
        out.append(f"...{pre}[[{tok.decode([int(seq[p])])}]]{post}...")
    return out


def build_quiz(f, X, tok, lo, hi, rng, n_pos=N_POS, n_neg=N_NEG):
    acc = X["activations"][f]
    order = torch.argsort(acc, descending=True)
    pool = [int(j) for j in order[lo:hi] if float(acc[j]) > 0]
    if len(pool) < n_pos:
        return None
    pos = [one_snip(f, j, X, tok) for j in rng.choice(pool, n_pos, replace=False)]
    items = [(s, 1) for s in pos] + [(s, 0) for s in neg_snips(f, X, tok, rng, n_neg)]
    perm = rng.permutation(len(items))
    return [items[i] for i in perm]


def auc(scores: list[float], truth: list[int]) -> float:
    """Rank-based, so it uses the model's confidence rather than a thresholded
    Yes/No. Ties count half. 0.5 = the label ranks firing tokens no better than
    random ones."""
    P = [s for s, t in zip(scores, truth) if t == 1]
    N = [s for s, t in zip(scores, truth) if t == 0]
    if not P or not N:
        return 0.5
    return sum((a > b) + 0.5 * (a == b) for a in P for b in N) / (len(P) * len(N))


def batch_gen(model, tok, prompts, max_new, temp=0.0):
    if not prompts:
        return []
    texts = [tok.apply_chat_template([{"role": "user", "content": p}],
                                      tokenize=False, add_generation_prompt=True)
             for p in prompts]
    enc = tok(texts, return_tensors="pt", padding=True, add_special_tokens=False).to(model.device)
    kw = dict(do_sample=True, temperature=temp, top_p=0.95) if temp > 0 else dict(do_sample=False)
    with torch.no_grad():
        g = model.generate(**enc, max_new_tokens=max_new, pad_token_id=tok.pad_token_id, **kw)
    return [tok.decode(r[enc["input_ids"].shape[1]:], skip_special_tokens=True) for r in g]


@torch.no_grad()
def _margins(model, tok, prompts, yes_ids, no_ids, bs=64):
    """logP(Yes) - logP(No) at the first generated position.

    A single forward pass, no generation and no parsing. Continuous, so AUC can
    use the model's confidence; argmax Yes/No discarded that and cost ~0.03 of
    discriminative gap."""
    out = []
    for i in range(0, len(prompts), bs):
        texts = [tok.apply_chat_template([{"role": "user", "content": p}], tokenize=False,
                                          add_generation_prompt=True) for p in prompts[i:i + bs]]
        enc = tok(texts, return_tensors="pt", padding=True,
                  add_special_tokens=False).to(model.device)
        lg = model(**enc).logits[:, -1, :].float().log_softmax(-1)
        out += (torch.logsumexp(lg[:, yes_ids], -1)
                - torch.logsumexp(lg[:, no_ids], -1)).tolist()
    return out


def score_labels(model, tok, jobs, yes_ids, no_ids):
    """jobs: list of (label, quiz_items) -> list of AUCs."""
    prompts, owner = [], []
    for i, (lab, items) in enumerate(jobs):
        for snip, _ in items:
            prompts.append(_SCORE_PROMPT.format(label=lab, snip=snip))
            owner.append(i)
    if not prompts:
        return []
    m = _margins(model, tok, prompts, yes_ids, no_ids)
    per = defaultdict(list)
    for i, v in zip(owner, m):
        per[i].append(v)
    return [auc(per[i], [t for _, t in items]) for i, (_, items) in enumerate(jobs)]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dirs", nargs="+", required=True)
    ap.add_argument("--labeller", default="google/gemma-3-12b-it")
    ap.add_argument("--out", required=True)
    ap.add_argument("--batch", type=int, default=6)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--sae", default="l0_small",
                    help="l0_small (L0~21) is labelable; l0_big (L0~129) is not — "
                         "measured label-vs-wrong-label AUC gap +0.092 vs +0.008")
    a = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)

    want: set[int] = set()
    for d in a.dirs:
        j = json.loads((Path(d) / f"feature_overlap_{a.sae}.json").read_text())
        for fs in j["stage1"]["F_orig"]:
            want |= set(fs)
        for r in j["runs"]:
            want |= set(r["shared_features"]) | set(r["lost_features"]) | set(r["invented_features"])
    want = sorted(want)

    out_path = Path(a.out)
    cache = json.loads(out_path.read_text()) if out_path.exists() else {}
    todo = [f for f in want if str(f) not in cache]
    if a.limit:
        todo = todo[:a.limit]
    print(f"[data] {len(want)} unique features over {len(a.dirs)} corpora | "
          f"{len(cache)} cached | {len(todo)} to do")
    if not todo:
        print("nothing to do")
        return

    d = sae_variant_dir(f"layer_32_width_16k_{a.sae}")
    X = load_file(str(d / "examples.safetensors"))
    tok = AutoTokenizer.from_pretrained(a.labeller)
    tok.padding_side = "left"
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(a.labeller, dtype=torch.bfloat16).to("cuda").eval()
    YES = [tok.encode(s, add_special_tokens=False)[0] for s in ("Yes", " Yes", "yes")]
    NO = [tok.encode(s, add_special_tokens=False)[0] for s in ("No", " No", "no")]
    cats = ", ".join(CATEGORIES)
    t0 = time.time()
    # pool of already-assigned labels, drawn from to build each feature's null
    pool = [v["label"] for v in cache.values() if v.get("label")]

    for b0 in range(0, len(todo), a.batch):
        chunk = todo[b0:b0 + a.batch]

        # ---- Stage A: N candidate labels per feature ----
        prompts, owner = [], []
        for f in chunk:
            rng = np.random.default_rng(a.seed * 100003 + f)
            ps = passages(f, X, tok, 0, GEN_TOP, N_GEN_PASSAGES, rng)
            ng = neg_snips(f, X, tok, rng, 2)
            promoted = [tok.decode([int(t)]) for t in X["top_tokens"][f][:10]]
            p = _GEN_PROMPT.format(passages="\n".join(ps), neg="\n".join(f"  {s}" for s in ng),
                                   promoted=", ".join(repr(x) for x in promoted),
                                   fewshot=_FEWSHOT, cats=cats)
            for _ in range(N_CAND):
                prompts.append(p)
                owner.append(f)
        outs = batch_gen(model, tok, prompts, 120, temp=0.9)

        cands = defaultdict(list)
        for f, txt in zip(owner, outs):
            m_l = re.search(r"EXPLANATION:\s*(.+)", txt)
            if not m_l:
                continue
            m_c = re.search(r"CATEGORY:\s*([a-z_,\s]+)", txt, re.I)
            cs = [c.strip().lower() for c in (m_c.group(1) if m_c else "").split(",")]
            cs = [c for c in cs if c in CATEGORIES][:2] or ["other"]
            lab = m_l.group(1).strip().strip('"')[:120]
            # TRIGGER/CONTENT split. Downstream grounding matches on CONTENT only.
            # 71% of labels in the previous run described a grammatical position
            # ("Nouns describing attributes following..."), and matching an
            # explanation against those produced false positives on surface form
            # alone — an item was called grounded because it contained an
            # adjective and the label mentioned adjectives. Separating the two at
            # generation time removes that at the source instead of filtering it
            # downstream, where it could not be fully removed (159 such labels
            # were categorised topic_domain and survived the content filter).
            m_t = re.search(r"TRIGGER:\s*(.+)", txt)
            m_n = re.search(r"CONTENT:\s*(.+)", txt)
            content = (m_n.group(1).strip().strip('"')[:140] if m_n else "")
            if re.fullmatch(r"none\.?", content.strip(), re.I):
                content = ""
            if lab and not any(lab == c[0] for c in cands[f]):
                cands[f].append((lab, cs, (m_t.group(1).strip()[:120] if m_t else ""), content))

        # ---- Stage B: SELECT the winning candidate, on band 1 ----
        jobs, key = [], []
        for f in chunk:
            rng = np.random.default_rng(a.seed * 7919 + f)
            q = build_quiz(f, X, tok, SELECT_LO, SELECT_HI, rng, N_SEL_POS, N_SEL_NEG)
            if q is None:
                continue
            for lab, cs, tg, ct in cands[f]:
                jobs.append((lab, q))
                key.append((f, lab, cs, tg, ct))
        sel = score_labels(model, tok, jobs, YES, NO)
        best = {}
        for (f, lab, cs, tg, ct), s in zip(key, sel):
            if f not in best or s > best[f][-1]:
                best[f] = (lab, cs, tg, ct, s)

        # ---- Stage C: REPORT on band 2, plus the per-feature NULL ----
        # Band 2 is disjoint from band 1, so the reported AUC never sees the data
        # that chose the label. The null uses the SAME quiz with other features'
        # labels, so it absorbs every label-independent artefact — chiefly that
        # SAE-activating tokens are systematically more "interesting" than random
        # ones, which lifts any plausible label above 0.5.
        jobs, key, kind = [], [], []
        for f, (lab, cs, _tg, _ct, _s) in best.items():
            rng = np.random.default_rng(a.seed * 104729 + f)
            q = build_quiz(f, X, tok, REPORT_LO, REPORT_HI, rng)
            if q is None:
                continue
            jobs.append((lab, q)); key.append(f); kind.append("real")
            others = [l for l in pool if l != lab] or [
                c[0] for g in chunk if g != f for c in cands[g]]
            for wrong in (rng.choice(others, min(N_NULL, len(others)), replace=False)
                          if others else []):
                jobs.append((str(wrong), q)); key.append(f); kind.append("null")
        rep = score_labels(model, tok, jobs, YES, NO)
        real, null = {}, defaultdict(list)
        for f, k, s in zip(key, kind, rep):
            (real.__setitem__(f, s) if k == "real" else null[f].append(s))

        for f in chunk:
            lab, cs, tg, ct, s_sel = best.get(f, ("", ["other"], "", "", None))
            if lab:
                pool.append(lab)
            cache[str(f)] = {
                "label": lab, "categories": cs,
                "trigger": tg, "content": ct,   # content == "" -> purely grammatical
                "promoted": [tok.decode([int(t)]) for t in X["top_tokens"][f][:8]],
                "auc": real.get(f), "auc_null": null.get(f, []),
                "select_auc": s_sel, "n_candidates": len(cands[f]),
            }
        out_path.write_text(json.dumps(cache, indent=2))

        n = b0 + len(chunk)
        el = time.time() - t0
        f0 = chunk[0]
        c0 = cache[str(f0)]
        print(f"[{n:>5}/{len(todo)}] {el/60:5.1f}m eta {(el/n)*(len(todo)-n)/60:4.0f}m  "
              f"f{f0} auc={c0['auc']} [{'/'.join(c0['categories'])}] {c0['label'][:46]}")

    # ---- calibrate reliability against the empirical null ----
    nulls = sorted(s for v in cache.values() for s in v.get("auc_null", []))
    ok = [v for v in cache.values() if v.get("auc") is not None]
    thr = float(np.percentile(nulls, 95)) if nulls else 0.7
    for v in cache.values():
        v["reliable"] = (v.get("auc") or 0) >= thr
    out_path.write_text(json.dumps(cache, indent=2))

    print(f"\nlabelled {len(cache)} features")
    if ok and nulls:
        aucs = [v["auc"] for v in ok]
        rel = [v for v in ok if v["reliable"]]
        print(f"AUC  matched {np.mean(aucs):.3f}   null (wrong labels) {np.mean(nulls):.3f}"
              f"   gap {np.mean(aucs)-np.mean(nulls):+.3f}")
        print(f"reliability threshold = 95th pct of null = {thr:.3f}  "
              f"(so 5% of these pass by chance)")
        print(f"validated labels: {len(rel)}/{len(ok)} ({100*len(rel)/len(ok):.0f}%)"
              f" — every downstream table must be restricted to these")
    val = [v for v in cache.values() if v["reliable"]]
    with_c = sum(1 for v in val if v.get("content"))
    if val:
        print(f"\nof {len(val)} validated labels, {with_c} ({100*with_c/len(val):.0f}%) carry a "
              f"CONTENT field;\n  the other {len(val)-with_c} are purely grammatical and are "
              f"excluded from grounding\n  (reported as coverage loss, not counted as ungrounded)")
    c = Counter(cat for v in val for cat in v["categories"])
    print("\ncategories among VALIDATED labels:")
    for k, v in c.most_common():
        print(f"  {k:<16} {v:>5}")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
