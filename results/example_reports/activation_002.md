# Trust report — activation 2 (parquet row 340)

Reconstruction FVE `+0.801` · cosine `0.9972`

## The explanation under review

> Structured advice framing: practical habit change guide establishing a practical, mindful pitch around vegetarian/sustainable lifestyle choices. The phrase "makes the lifestyle shift easier, framing it as a mindset change, which makes these changes easier" sets up a payoff statement about longterm commitment or sustainability. Final token "easier" ends a clause ("makes those changes easier...and that's key to making the tradeoff easier"), requiring a completion like "to maintain" or "long-term." — likely "to stick with." or "to adopt." or "over the long run. The emotional commitment..." or "or more permanent." referencing the behavioral habit or accepting the lifestyle.

## Verdict

| | features | named |
|---|---:|---:|
| **CONFIRMED** — in the activation, and the AR recovers it | 13 | 5 |
| **UNVERIFIED** — the AR produces it, but it is not in the activation here | 6 | 5 |
| **OMITTED** — in the activation, but the AR does not recover it | 9 | 4 |

*These are set operations on SAE feature sets — the explanation text is never read. It enters only through the AR's reconstruction of it.*

*14 of 28 features (50%) have a validated label and can be named. The rest are counted only.*

### Confirmed

- `f63` Adjectives and adverbs describing qualities following a qualifying phrase.
- `f3910` Adjective describing ease follows a description of a tool or process.
- `f3519` Difficult" follows a description of a barrier or obstacle.
- `f10602` An adjective appearing before a noun indicating an elevated state.
- `f1723` Preposition/conjunction within a discussion of food/nutrition.
- *(plus 8 further features that could not be named)*

### Unverified

- `f283` Second-person pronoun following a limitation or request.
- `f33` Declining a request using a negative modal verb.
- `f13029` Adjective describing a task as difficult/hard/impossible.
- `f2768` Fires on tokens following a comparative adverb or adjective.
- `f908` The feature fires on forms of "maintain/retain" indicating a need for ongoing preservation.
- *(plus 1 further features that could not be named)*

### Omitted

- `f123` Nouns following a description of an acceptable/unacceptable or defining characteristic.
- `f1443` Fires on a second-person pronoun/contraction appearing mid-list.
- `f2688` Words indicating nuance, variation, or emphasis following a preceding phrase.
- `f2216` Prepositions/conjunctions linking phrases discussing abstract topics.
- *(plus 5 further features that could not be named)*

## Assessment

*Written by a language model from the CONFIRMED and UNVERIFIED lists only — omitted features are excluded, since they concern what the explanation left out rather than whether what it said holds up. The counts and lists above are computed; only this paragraph is generated.*

Based on our analysis, the model's explanation demonstrates a degree of reliability regarding its description of qualities, ease, obstacles, elevated states, and discussions of food and nutrition within the activation—all of which were consistently recovered by a reconstructor. However, the explanation’s claims concerning second-person pronouns, declining requests, perceived task difficulty, and the need for ongoing preservation show considerably less consistency, as these features were not found in the activation at the described positions. Consequently, while the explanation provides some useful insights, reliance on its assertions about these unverified elements should be approached with caution, as the evidence supporting them is currently thin. Ultimately, the explanation’s value lies primarily in its identification of concrete linguistic patterns directly present in the activation.

## Source text

```
user What can we do as individuals to address climate change? Provide some examples and how we can adapt our lifestyle to include those changes model Okay, let's break down what individuals can do to address climate change, both in terms of actions and lifestyle adaptations. It's easy to feel overwhelmed, but *every* action, however small, contributes to a larger shift. I'll organize this into categories (big impact, medium impact, smaller but still worthwhile), and give actionable examples with how to integrate them. I'll also include some notes on mindset shifts that make these changes easier
```

---

**Unverified is not false.** On 50 Gemma rollout activations, 65-68% of unverified content features were genuinely present in the source document, just not at this token position (control 25-30%). Treat unverified as *not checked*, never as *refuted*.
