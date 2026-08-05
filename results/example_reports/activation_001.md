# Trust report — activation 1 (parquet row 134)

Reconstruction FVE `+0.804` · cosine `0.9973`

## The explanation under review

> Algorithm explanation structure: pedagogical pattern of "sliding window" logic requires a concrete example comparing substring search. The sentence "Given a string S, we compare the" sets up the core matching algorithm — finding the first occurrence of "pattern" from the substring. Final token "the" opens a noun phrase ("comparing the"), requiring a specific noun — most likely "pattern" or "first character of the pattern with the substring" or "pattern at the beginning of the string" or "first characters of 'apple'" — a direct comparison operation like "entire pattern with the string" or "substring starting at index 0" matching the needle/haystack.

## Verdict

| | features | named |
|---|---:|---:|
| **CONFIRMED** — in the activation *and* recoverable from the explanation | 19 | 7 |
| **UNVERIFIED** — implied by the explanation, not found in the activation here | 4 | 2 |
| **OMITTED** — in the activation, not carried by the explanation | 4 | 0 |

*9 of 27 features (33%) have a validated label and can be named. The rest are counted only.*

### Confirmed

- `f1205` Definite article at start of clause/phrase.
- `f635` Introduces a variable, type, or parameter within a code or data description.
- `f334` Fires on "the" at the beginning of a clause.
- `f121` Prepositions/conjunctions following a noun or noun phrase indicating enumeration or connection.
- `f4855` The feature fires on forms of "match" used to indicate a comparison or finding a suitable pair.
- `f2865` Signals a test or assertion statement, frequently initiating a validation sequence.
- `f3689` Triggers on mentions of regular expressions and related terms.
- *(plus 12 further features that could not be named)*

### Unverified

- `f393` Sentence-initial "The".
- `f667` Fires on "the" followed by a noun or noun phrase.
- *(plus 2 further features that could not be named)*

### Omitted

- *(none with a validated label)*
- *(plus 4 further features that could not be named)*

## Assessment

*Written by a language model from the CONFIRMED and UNVERIFIED lists only — omitted features are excluded, since they concern what the explanation left out rather than whether what it said holds up. The counts and lists above are computed; only this paragraph is generated.*

Overall, the model’s explanation demonstrates a degree of reliability, though with important limitations. The confirmed features—including indications of definite articles, variable introductions, comparison terminology, and regular expression mentions—appear consistently within the activation data and can be confidently reproduced. However, the evidence supporting the unverified features is thin; while these claims likely reflect broader patterns within the document, they were not present at the specific activation point examined. Therefore, users should treat the explanation’s assertions regarding sentence-initial "The" and "the" followed by a noun phrase with caution, recognizing that these may be valid observations elsewhere in the text. While the core analogy to substring search provides a useful framework, the explanation’s broader claims require further validation across a wider context.

## Source text

```
user Can you tell me the idea behind the Knuth-Morris-Pratt string matching algorithm? model Okay, let's break down the Knuth-Morris-Pratt (KMP) string matching algorithm. It's a clever and efficient way to find occurrences of a "pattern" string within a larger "text" string. Here's the core idea, explained in layers of detail, starting from the problem and building up to the solution. **1. The Problem: Naive String Matching is Inefficient** Imagine you want to find all occurrences of the word "needle" in a long text like this: `"haystackneedlehaystackneedlehaystack"` A naive approach would be: * Start at the beginning of the text. * Compare the
```

---

**Unverified is not false.** On 50 Gemma rollout activations, 65-68% of unverified content features were genuinely present in the source document, just not at this token position (control 25-30%). Treat unverified as *not checked*, never as *refuted*.
