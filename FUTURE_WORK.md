# Future work

Everything in [RESULTS.md](RESULTS.md) is correlational: it shows the final
paragraph's higher FVE tracks more grounded content, not why. Three directions
follow from that, each targeting a different stage of the pipeline.

---

## 1. Restructure the pretraining format

The first two paragraphs — document type and subject — carry **39% of the
round trip's FVE and under half its grounded content, from over half the
tokens** ([RESULTS.md](RESULTS.md)). The warm-start data asks the AV for a
three-part shape; on this checkpoint, two of those three parts do not appear to
encode much of what is genuinely in the activation.

The natural test is a pretraining format that asks for less document framing and
more of whatever the final paragraph is doing well, then rerunning the same
SAE-witness methodology on the result. If the central table's gap narrows, the
original three-part shape was costing grounded content rather than adding
context; if it does not, the final paragraph's advantage is about *position*
(nearest the injected token) rather than *content*, and restructuring the format
elsewhere would not help.

## 2. Reward truthfulness directly, not only reconstruction

Even the best-performing variant here never exceeds 43% conveyed of labelled
F_orig latents, or 19.5% of all of them ([RESULTS.md](RESULTS.md), the central
table). Most of what is genuinely in the activation is never stated, in the
most favourable case this project measured.

Seong Pyo Hong ("Fixing rewards for NLA to reduce confabulation," LessWrong, 24
July 2026) targets this directly: the standard NLA reward never penalises an
unfaithful claim, since it only checks whether the AR can decode the AV's
description, not whether the description is accurate. Adding a factuality term —
checking named entities against the source — moved a fact-checking score from
0.124 to 0.417 over 800 training steps with FVE unchanged (~0.41), and an LLM
judge preferred the new model's outputs 83.6% of the time against 54.5% for the
baseline.

This project's SAE-based grounding measure is a second, independent way to score
the same thing a truthfulness-reward run would need to validate against: not
"does an entity-matcher find the claim in the text," but "does an independent
model of the activation confirm the claim was there."

## 3. Train the base model for decodability, not only the AV and AR

Separately from what this project measured, NLA explanations are consistently
weak on specifics — a name or detail is often swapped for a plausible
substitute even when the surrounding topic is right. That is consistent with
activations simply not being *built* to be linearly readable by a downstream
model, in which case no amount of AV/AR training closes the gap.

Hiskias Dingeto ("Train the Model, Not the Reader: Decodability Supervision for
Verifiable Activation Explanations," arXiv:2607.20379, 22 July 2026) proposes
RECAP: train the base model itself with auxiliary linear probes that keep
designated content decodable from its hidden states, rather than only training
better readers of whatever the base model happens to produce. Verification
coverage of designated content moved from 37% to 100%, and under an adversary
optimizing for a high reconstruction score while inserting false claims, a
RECAP-trained probe still flagged the lies at AUC 0.95 against 0.51 for a
control probe trained the ordinary way.

If a base model trained this way were paired with an NLA AV/AR, the same
central-table methodology here would test the direct question: does raising the
activation's own decodability raise the ceiling on grounded content, or does the
bottleneck stay wherever it currently is?
