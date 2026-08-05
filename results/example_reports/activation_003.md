# Trust report — activation 3 (parquet row 254)

Reconstruction FVE `+0.803` · cosine `0.9973`

## The explanation under review

> Structured form template format establishes checklist instructions, requiring practical advice for contacting a specific lender/agency. The phrase "Address: [Company Name] - " signals a parenthetical clarification about the Contact form, setting up a specific location lookup or mailing address for the Canadian Bank. Final token " - " follows a parenthetical opener "Address - (Postal Address -") requiring immediate guidance on finding the specific branch address; likely "Find the correct branch by researching)" or "REQUIRED: Look up the specific IRS contact address" or "This is critical; find it online." or "Ideally, specify the exact branch if you know it" to match the letter.

## Verdict

| | features | named |
|---|---:|---:|
| **CONFIRMED** — in the activation *and* recoverable from the explanation | 19 | 5 |
| **UNVERIFIED** — implied by the explanation, not found in the activation here | 6 | 2 |
| **OMITTED** — in the activation, not carried by the explanation | 10 | 5 |

*12 of 35 features (34%) have a validated label and can be named. The rest are counted only.*

### Confirmed

- `f26` Fires on list markers followed by a colon.
- `f16` Starts sentences/clauses after punctuation, often introducing emphasis or explanation.
- `f9012` Introduces a descriptive point or list item following a colon/asterisk.
- `f2080` Relates to physical delivery of correspondence.
- `f5452` Fires on tokens immediately following a label indicating contact information.
- *(plus 14 further features that could not be named)*

### Unverified

- `f5852` ** The feature fires on phrases initiating a request for detail or clarification.
- `f648` Fires on a bolded title after a numbered section introduction.
- *(plus 4 further features that could not be named)*

### Omitted

- `f8310` Fires on a bracketed phrase denoting a specific detail or area.
- `f11281` Fires on phrases introducing focused advice regarding niche selection.
- `f13684` A clause ending with a parenthetical phrase or a clarifying statement.
- `f9133` Introduces a shift in thought or explanation within a sentence.
- `f10701` Comments suggesting modifications or optional steps trigger the feature.
- *(plus 5 further features that could not be named)*

## Assessment

*Written by a language model from the CONFIRMED and UNVERIFIED lists only — omitted features are excluded, since they concern what the explanation left out rather than whether what it said holds up. The counts and lists above are computed; only this paragraph is generated.*

The model’s explanation demonstrates a degree of reliability regarding the activation’s function, as a substantial number of observed features—specifically, its tendency to fire on list markers, sentence beginnings after punctuation, and tokens related to physical correspondence—were confirmed through reconstruction. However, the evidence supporting the explanation’s claims about the activation’s role in phrases requesting detail or bolded titles is thin, as these features were not directly observed at the analyzed position. Consequently, while the confirmed aspects of the explanation can be reasonably relied upon for understanding this particular activation, the unverified claims should be treated with caution and potentially investigated further within the broader document context. Ultimately, the model provides a useful, though incomplete, insight into the activation’s behavior.

## Source text

```
user Can you write me a formal letter for the canada immigration services in order to get a visa to work abroad from france? model Okay, here's a draft of a formal letter you can adapt for Canada Immigration Services. **Please read the IMPORTANT DISCLAIMERS at the very end of this response *before* using this letter.** I've included explanations and bracketed areas ([...]) where you *must* customize the content. I've also provided notes on optional sections. [Your Full Name] [Your Full Address in France] [Your Phone Number] [Your Email Address] [Date] Canada Immigration Services [Specific Office Address -
```

---

**Unverified is not false.** On 50 Gemma rollout activations, 65-68% of unverified content features were genuinely present in the source document, just not at this token position (control 25-30%). Treat unverified as *not checked*, never as *refuted*.
