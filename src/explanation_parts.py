"""Split an AV explanation into the parts whose contributions we want to measure.

WHY THIS EXISTS
The AV writes to a stable three-part shape:

    1. what kind of document this is        "Structured guide format signals a
                                             summary/comparison breakdown..."
    2. what it is about                     "The phrase "I've organized them,
                                             divided" sets up..."
    3. what the FINAL TOKEN is doing        "Final token "divided" opens a
                                             organizational preamble..."

Part 3 is a different kind of claim from parts 1-2: it is about the single token
the activation sits on, where the other two are about the surrounding document.
If part 3 alone carries most of the reconstruction signal, then the NLA is doing
next-token description rather than context summarisation, and every downstream
result should be read in that light. Splitting the explanation is how that gets
measured, using the pipeline that already exists rather than a new metric.

HOW THE SPLIT IS ANCHORED
Not on paragraph count. Measured over 250 real explanations:

    exactly 3 paragraphs                                  245/250  (98%)
    the phrase "final token" appears at least once        250/250  (100%)
    ...appears more than once (would be ambiguous)          0/250
    exactly one paragraph contains it, and not the first  250/250  (100%)

So the anchor is the phrase, and it is strictly better than counting paragraphs.
The five explanations that are not three paragraphs are a real edge case worth
keeping: the final token is itself a newline, so the AV writes

    Final token "

    " ends a transitional header...

which splits itself in two. Anchoring on the phrase rejoins those correctly;
counting paragraphs would have put half of part 3 into `no_final` and quietly
corrupted both variants.

Every split records which method produced it, so a run where the format drifts
shows up in the summary instead of silently degrading.
"""

from __future__ import annotations

import re

_ANCHOR = "final token"
# Sentence boundary: a ., ! or ? followed by whitespace and a capital or quote.
# Deliberately conservative -- it is only used by the fallback path.
_SENT = re.compile(r'(?<=[.!?])\s+(?=["“(]?[A-Z])')


def split_explanation(text: str | None) -> dict:
    """Split into `full`, `no_final` (parts 1-2) and `final_only` (part 3).

    Returns a dict with the three variants, the `method` that produced them, and
    the paragraph/sentence counts that method saw. `no_final` is None when the
    text cannot be split at all -- callers must handle that rather than feeding
    an empty string to the AR, which would score as a failed extraction and be
    indistinguishable from a broken injection.
    """
    if not text or not text.strip():
        return {"full": text, "no_final": None, "final_only": None,
                "method": "empty", "n_paragraphs": 0, "n_sentences": 0}

    text = text.strip()
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    sents = _SENT.split(text)
    base = {"full": text, "n_paragraphs": len(paras), "n_sentences": len(sents)}

    # 1. ANCHOR: the paragraph that talks about the final token, and everything
    #    after it. Requires the anchor to appear in exactly one paragraph and not
    #    the first -- otherwise there is no "parts 1-2" left to keep.
    hits = [i for i, p in enumerate(paras) if _ANCHOR in p.lower()]
    if len(hits) == 1 and hits[0] > 0:
        i = hits[0]
        return {**base, "method": "anchor",
                "no_final": "\n\n".join(paras[:i]),
                "final_only": "\n\n".join(paras[i:])}

    # 2. FALLBACK: last paragraph. Used when the anchor is missing, duplicated,
    #    or lands in paragraph 0.
    if len(paras) >= 2:
        return {**base, "method": "last_paragraph",
                "no_final": "\n\n".join(paras[:-1]),
                "final_only": paras[-1]}

    # 3. FALLBACK: sentence position, for a single-paragraph explanation. The
    #    last sentence stands in for part 3.
    if len(sents) >= 2:
        return {**base, "method": "last_sentence",
                "no_final": " ".join(sents[:-1]).strip(),
                "final_only": sents[-1].strip()}

    # 4. Nothing to split. One sentence, one paragraph.
    return {**base, "method": "unsplittable", "no_final": None, "final_only": None}


#: The variants every downstream stage is run on, in report order.
VARIANTS = ("full", "no_final", "final_only")


def split_report(splits: list[dict]) -> dict:
    """Aggregate the per-explanation split records into something reportable.

    The success rate is the number that matters: `anchor` is the intended path,
    and a run where it drops means the AV's output format moved and the ablation
    is comparing something other than what this docstring claims.
    """
    n = len(splits)
    by_method: dict[str, int] = {}
    for s in splits:
        by_method[s["method"]] = by_method.get(s["method"], 0) + 1
    usable = sum(1 for s in splits if s.get("no_final") and s.get("final_only"))
    return {
        "n": n,
        "by_method": dict(sorted(by_method.items(), key=lambda kv: -kv[1])),
        "anchor_rate": by_method.get("anchor", 0) / n if n else None,
        "usable": usable,
        "usable_rate": usable / n if n else None,
    }
