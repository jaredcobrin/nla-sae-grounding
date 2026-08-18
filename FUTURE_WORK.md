# Future work

Three directions.

---

## 1. Restructure the pretraining format

The first two paragraphs carry 39% of the round trip's FVE and under half its
grounded content, from over half the tokens ([RESULTS.md](RESULTS.md)). The
warm-start data asks the AV for a three-part shape — document type, subject,
final token.

Worth trying: a pretraining format that asks for less document framing and more
of whatever the final paragraph is doing. Maybe that encodes more of the
activation into the text the AV writes.

## 2. Reward truthfulness directly, not only reconstruction

Even the best variant here conveys under half of the labelled latents genuinely
in the activation ([RESULTS.md](RESULTS.md), the central table).

Seong Pyo Hong, "Fixing rewards for NLA to reduce confabulation" (LessWrong, 24
July 2026): the standard NLA reward never penalises an unfaithful claim, since it
only checks whether the AR can decode the AV's description. Adding a factuality
term — checking named entities against the source — moved a fact-checking score
from 0.124 to 0.417 over 800 training steps with FVE unchanged (~0.41), and an
LLM judge preferred the new model's outputs 83.6% of the time against 54.5% for
the baseline.

Worth trying: use this project's SAE-based grounding measure as a second check
on a run like that, alongside the entity-match score.

## 3. Train the base model for decodability, not only the AV and AR

NLA explanations are often weak on specifics — a name or detail swapped for a
plausible substitute even when the surrounding topic is right.

Hiskias Dingeto, "Train the Model, Not the Reader: Decodability Supervision for
Verifiable Activation Explanations" (arXiv:2607.20379, 22 July 2026) — RECAP:
train the base model itself with auxiliary linear probes that keep designated
content decodable from its hidden states, rather than only training better
readers of whatever the base model produces. Verification coverage of
designated content moved from 37% to 100%, and under an adversary optimizing for
reconstruction score while inserting false claims, a RECAP-trained probe still
flagged the lies at AUC 0.95 against 0.51 for a control probe trained the
ordinary way.

Worth trying: pair an NLA AV/AR with a RECAP-trained base model and rerun this
project's methodology on it. Maybe a more decodable activation raises the
ceiling on grounded content.
