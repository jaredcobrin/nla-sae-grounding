# Trust report — activation 5 (parquet row 421)

Reconstruction FVE `+0.680` · cosine `0.9955`

## The explanation under review

> Structured definition format: factual biome description, following a classic ecological classification pattern with "Tundra" as the subject. The phrase "Desert biome, characterized by..." signals a specific key characteristic of the steppe biome — cold temperatures and precipitation, contrasting with dry summers. Final token "experience" opens a predicate clause ("which experience..."), requiring a characteristic trait of the tundra climate — most likely "cold winters" or "low temperatures" to specify the defining condition, likely "cold winters and freezing temperatures" or "significant seasonal variation" or "both cold winters and warm summers" — a specific temperature or seasonal category typical for Mediterranean/boreal vegetation.

## Verdict

| | features | named |
|---|---:|---:|
| **CONFIRMED** — in the activation *and* recoverable from the explanation | 13 | 8 |
| **UNVERIFIED** — implied by the explanation, not found in the activation here | 10 | 8 |
| **OMITTED** — in the activation, not carried by the explanation | 12 | 7 |

*23 of 35 features (65%) have a validated label and can be named. The rest are counted only.*

### Confirmed

- `f13508` A word describing climate conditions, frequently following an article or preposition.
- `f11` Fires on tokens indicating enablement or possibility.
- `f284` Describes meteorological conditions after a colon or descriptor.
- `f3113` Adjective describing coldness or related discomfort in a warning/descriptive context.
- `f11960` The feature fires on tokens indicating someone or something is confronted with a problem.
- `f1207` Fires on articles following a "What is" question.
- `f4639` The token "winter" appears within a list or description of seasons.
- `f6272` Highlights phrases indicating the best time to visit or seasonal information.
- *(plus 5 further features that could not be named)*

### Unverified

- `f152` Following a description of a natural system or process.
- `f8567` Proper noun denoting a polar region or associated location.
- `f3753` experience" appearing in discussions of subjective understanding or qualifications.
- `f11318` Introduces a new topic or explanation within a historical overview.
- `f14116` Fires on tokens following a bolded label designating a geographic weather forecast.
- `f3559` Adjectives/phrases describing wetness, dryness, or moisture levels.
- `f4076` Indicates susceptibility or reactivity to alterations or conditions.
- `f4277` The feature fires on tokens representing the concept of "summer," especially when explicitly named.
- *(plus 2 further features that could not be named)*

### Omitted

- `f12551` Triggers on tokens indicating arid, sandy environments.
- `f16341` Describes a temperature or feeling of coolness or coldness.
- `f6253` A token representing frozen water immediately following a description or definition.
- `f11098` Temperature values, frequently with a degree symbol, trigger the feature.
- `f4711` Measures of time or responsiveness are being explicitly quantified.
- `f8727` National" appearing as part of a named entity referring to a park.
- `f6132` focus" appears after a topic is introduced or defined.
- *(plus 5 further features that could not be named)*

## Assessment

*Written by a language model from the CONFIRMED and UNVERIFIED lists only — omitted features are excluded, since they concern what the explanation left out rather than whether what it said holds up. The counts and lists above are computed; only this paragraph is generated.*

The model's explanation demonstrates a degree of reliability centered on specific, observable patterns within the neural activation. A substantial number of features – including climate descriptors, references to fire and meteorological conditions, and seasonal markers like "winter" – were consistently confirmed through reconstruction with the sparse autoencoder. However, the evidence supporting the explanation is thinner when it comes to broader contextual elements; the model’s implication of polar regions, discussions of subjective experience, or connections to summer conditions were not found at this activation position, though they likely appear elsewhere in the document. Therefore, while the explanation can be trusted for its identification of concrete linguistic features, caution is advised when interpreting its broader inferences about the tundra biome.

## Source text

```
ns, climates, vegetation, and wildlife: **1. Defining a Desert: It's About Precipitation, Not Just Temperature** The defining characteristic of a desert is *low precipitation*. While many people associate deserts with scorching heat, that's not always the case. The technical definition isn't just about temperature; it's about receiving **less than 250 mm (10 inches) of precipitation per year.** **2. Types of Deserts & Their Distribution:** We can broadly categorize deserts into several types: * **Hot and Dry Deserts:** These are the quintessential deserts most people envision – fiery temperatures, sparse vegetation, and often sandy or rocky landscapes. * **Distribution:** Sahara (North Africa - the largest hot desert), Arabian Desert (Middle East), Australian Outback, Sonoran Desert (Southwestern US/Mexico), Mojave Desert (California), Negev Desert (Israel/Jordan/Egypt) * **Semiarid Deserts:** Slightly more rainfall than hot deserts, supporting a bit more vegetation. They transition into grasslands or shrublands. * **Distribution:** Patagonian Desert (Argentina/Chile), Great Basin Desert (US - Nevada, Utah), Chihuahuan Desert (US/Mexico) * **Cold Deserts:** These deserts experience
```

---

**Unverified is not false.** On 50 Gemma rollout activations, 65-68% of unverified content features were genuinely present in the source document, just not at this token position (control 25-30%). Treat unverified as *not checked*, never as *refuted*.
