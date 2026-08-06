# Trust report — activation 4 (parquet row 446)

Reconstruction FVE `+0.834` · cosine `0.9977`

## The explanation under review

> Technical tutorial structure signals a structured data file description, establishing a practical CSV/spreadsheet output guide for a Wordnik entries data dump. The phrase "I've manually formatted the list. I" sets up a meta-note about the dataset, likely addressing the workaround used to generate the ordered, comma-separated list. Final token "I" opens a parenthetical clause ("I..."), requiring a verb phrase — likely "have included placeholder values" or "have prioritized ordering by name" or "have also noted the estimated counts". Or "have used a Markdown table after completing the entries." or "have included a disclaimer about the likely limitations/estimated values at end."

## Verdict

| | features | named |
|---|---:|---:|
| **CONFIRMED** — in the activation, and the AR recovers it | 13 | 10 |
| **UNVERIFIED** — the AR produces it, but it is not in the activation here | 4 | 2 |
| **OMITTED** — in the activation, but the AR does not recover it | 8 | 3 |

*These are set operations on SAE feature sets — the explanation text is never read. It enters only through the AR's reconstruction of it.*

*15 of 25 features (60%) have a validated label and can be named. The rest are counted only.*

### Confirmed

- `f398` First-person pronoun after a statement of inability or prohibition.
- `f376` Fires on the first-person singular pronoun "I" at the start of a sentence or clause.
- `f712` Fires on contractions of "I" or "will.
- `f174` We" initiating a declarative statement or concluding remark.
- `f24` Follows a transitional phrase indicating a structured explanation (e.g., "Here's a," "A breakdown").
- `f66` Fires on imperative verbs or phrases initiating a request.
- `f5914` First-person pronoun initiating a request or expression of hope.
- `f271` First-person pronoun introducing a statement of ability or intention.
- `f77` Fires on initial "I" at the start of a phrase.
- `f39` Pronoun following a colon or bullet point introduction.
- *(plus 3 further features that could not be named)*

### Unverified

- `f1470` A bolded phrase introducing a reason for modification.
- `f1980` Fires on words introducing limitations or restrictions.
- *(plus 2 further features that could not be named)*

### Omitted

- `f7002` Disclaimers immediately preceding "I" trigger the feature.
- `f5813` I" followed by "hope" signals a supportive or helpful response.
- `f8185` Fires on initial "I" or "I'm" within a declaration of principles or actions.
- *(plus 5 further features that could not be named)*

## Assessment

*Written by a language model from the CONFIRMED and UNVERIFIED lists only — omitted features are excluded, since they concern what the explanation left out rather than whether what it said holds up. The counts and lists above are computed; only this paragraph is generated.*

The model's explanation demonstrates a degree of reliability regarding its identification of specific linguistic patterns within the neural activation. A reconstructor successfully recovered several confirmed features, including the presence of first-person pronouns in various contexts, contractions, and transitional phrases—suggesting the model accurately captures certain aspects of the activation's response. However, the evidence supporting the unverified features is thin; while these patterns were not found at the specific position analyzed, the report notes they likely appear elsewhere in the document. Therefore, while the confirmed features can be reasonably relied upon, caution should be exercised when interpreting the unverified claims, recognizing they represent potential patterns not observed in this particular instance. Ultimately, the explanation provides a partial, but not comprehensive, window into the activation's behavior.

## Source text

```
user Please provide me with a list of the 100 most well known global (brand) names, trademarks, social media account names or other important terms such as blockchain, music, art, computer, games. And think of brands such as Google, Facebook, Walmart, Aliexpress, etc. Provide this in a machine readable CSV format. Use one row per brand and sort the list by importance. I need the following columns: Brand Name, Valuation (in million euros), Yearly revenue (in million euros), Number of employees and the Year the brand was established. model Okay, generating a perfectly accurate and definitively ranked list of 100 global brand names with precise valuation, revenue, employee numbers, and founding years is practically impossible. These figures fluctuate constantly, and reliable private company data is often unavailable. However, I've compiled a list based on a combination of brand recognition, market capitalization (where applicable), estimated revenue, general consensus on importance, and publicly available data. **Please read the important disclaimers at the very bottom of this response.** Here's the CSV data. I've structured it to be copy-pasteable into a spreadsheet program. I
```

---

**Unverified is not false.** On 50 Gemma rollout activations, 65-68% of unverified content features were genuinely present in the source document, just not at this token position (control 25-30%). Treat unverified as *not checked*, never as *refuted*.
