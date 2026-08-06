# Trust report — activation 3 (parquet row 387)

Reconstruction FVE `+0.662` · cosine `0.9953`

## The explanation under review

> Established structure signals a prompt/role description, priming a creative writing output with a sample text snippet for a tarot/spell card. The phrase "I've included the text below, with some suggestions" sets up a practical instruction, implying the reader can choose/customize 3 options for the copy. Final sentence "This is formatted for you...There are 5 paragraphs." closes a setup instruction — next tokens likely "After the text" or "Choose the one that suits you" or "At the end are also options/notes" or "I'll list them at the end." or "Then, pick the ending" referencing the actual examples.

## Verdict

| | features | named |
|---|---:|---:|
| **CONFIRMED** — in the activation, and the AR recovers it | 8 | 3 |
| **UNVERIFIED** — the AR produces it, but it is not in the activation here | 4 | 2 |
| **OMITTED** — in the activation, but the AR does not recover it | 3 | 1 |

*These are set operations on SAE feature sets — the explanation text is never read. It enters only through the AR's reconstruction of it.*

*6 of 15 features (40%) have a validated label and can be named. The rest are counted only.*

### Confirmed

- `f4628` Fires on tokens following a period, signaling the start of a new clause or sentence.
- `f297` Period followed by a space introducing a new section or important note.
- `f4612` Triggered by "I've" followed by a verb indicating inclusion/explanation.
- *(plus 5 further features that could not be named)*

### Unverified

- `f13567` Period after a stylistic declaration.
- `f1953` Starts a new paragraph/section after a preceding text block.
- *(plus 2 further features that could not be named)*

### Omitted

- `f1498` Period following a clause introducing further detail or explanation.
- *(plus 2 further features that could not be named)*

## Assessment

*Written by a language model from the CONFIRMED and UNVERIFIED lists only — omitted features are excluded, since they concern what the explanation left out rather than whether what it said holds up. The counts and lists above are computed; only this paragraph is generated.*

The model's explanation demonstrates a degree of reliability regarding its identification of specific activation patterns. Our analysis confirms that the explanation accurately reflects the presence of features such as tokens following periods, periods introducing new sections, and triggers associated with phrases like "I've" followed by a verb. However, the evidence supporting other claims is thin; a reconstructor identified additional features—specifically, periods after stylistic declarations and paragraph starts following preceding text blocks—that were not found within the activation at the point of analysis. Therefore, while the explanation provides some useful insights, readers should approach the unverified aspects with caution, recognizing that these features may be present elsewhere in the broader document.

## Source text

```
user Two robots who have fallen in love with another. Soon, there is valentines day and one robots to write a humorous love letter and send it to the other. Can you help it write such a letter? model Okay, here's a humorous love letter, written from the perspective of a robot to another, with a few options for different tones (slightly more silly, slightly more sarcastic, a bit more earnest underneath the humor). I'll include explanations of the choices after each option to help you tailor it.
```

---

**Unverified is not false.** On 50 Gemma rollout activations, 65-68% of unverified content features were genuinely present in the source document, just not at this token position (control 25-30%). Treat unverified as *not checked*, never as *refuted*.
