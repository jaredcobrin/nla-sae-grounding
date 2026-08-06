# Trust report — activation 5 (parquet row 467)

Reconstruction FVE `+0.715` · cosine `0.9960`

## The explanation under review

> Structured workout routine format signals a workout plan outline, requiring specific exercise programming details for the dumbbell bench press. The phrase "Start with: Dumbbell Chest Press:" establishes a weight instruction header, priming a standard set/rep/rest breakdown for the barbell exercise. Final token " :": follows a structured exercise description ("Dumbbell Bench Press:"), immediately requiring the workout parameters — likely "3 sets of 8-12" or "3 sets, 3 reps" or "3 sets (3-4)" or "4 sets to target muscle growth." or "2 sets (full body)." referencing sets, reps, or weight.

## Verdict

| | features | named |
|---|---:|---:|
| **CONFIRMED** — in the activation, and the AR recovers it | 14 | 9 |
| **UNVERIFIED** — the AR produces it, but it is not in the activation here | 4 | 3 |
| **OMITTED** — in the activation, but the AR does not recover it | 10 | 3 |

*These are set operations on SAE feature sets — the explanation text is never read. It enters only through the AR's reconstruction of it.*

*15 of 28 features (53%) have a validated label and can be named. The rest are counted only.*

### Confirmed

- `f12154` Numbers immediately preceding "reps" or "repetitions.
- `f4703` Noun/adjective immediately following "and" in a fitness-related sentence.
- `f12767` Starts a list item describing a fitness exercise.
- `f16` Starts sentences/clauses after punctuation, often introducing emphasis or explanation.
- `f594` Preposition introducing a duration or timeframe.
- `f3943` Fires on number words, specifically those indicating a numerical value.
- `f4565` A word describing a body part immediately following a colon or bullet point.
- `f4750` Triggered by words related to carrying or moving things.
- `f6806` Fires on numeric literals, frequently within a calculation or assertion.
- *(plus 5 further features that could not be named)*

### Unverified

- `f1555` Equals sign preceding a numerical result or measurement.
- `f9564` A term describing a specific element of a game or sport.
- `f3595` A word indicating mass or weight, frequently appearing in specifications or descriptions.
- *(plus 1 further features that could not be named)*

### Omitted

- `f967` Fires on a label followed by a colon and a numeric strength rating.
- `f1663` Fires on digits or symbols following an equals sign or within a mathematical expression.
- `f322` Describes a positional or directional element.
- *(plus 7 further features that could not be named)*

## Assessment

*Written by a language model from the CONFIRMED and UNVERIFIED lists only — omitted features are excluded, since they concern what the explanation left out rather than whether what it said holds up. The counts and lists above are computed; only this paragraph is generated.*

Based on this analysis, the model's explanation demonstrates a degree of reliability regarding specific linguistic patterns within the activation. The confirmed features—such as numbers preceding "reps," fitness-related terms following "and," and phrases initiating exercise lists—appear consistently within the activation data and are successfully reconstructed when guided by the explanation. However, the evidence supporting the unverified features is thin; while these patterns likely exist elsewhere in the broader document, their presence at the specific locations indicated by the model cannot be confirmed. Therefore, while the explanation provides valuable insight into certain aspects of the activation, users should exercise caution and independent verification when interpreting claims related to the unverified features.

## Source text

```
 should focus on different muscle groups each day with a three day cycle and a rest day on Sundays. model Okay, here's a 3-day dumbbell-only workout plan designed to be done at home, targeting different muscle groups each day, with roughly an hour commitment per workout (including warm-up and rest), and a rest day on Sundays. **Please read the IMPORTANT DISCLAIMERS at the very end of this plan before starting.** **Key Assumptions:** * **Dumbbell Weight:** This plan is adaptable, but you'll need a range of weights. If you only have one dumbbell, adjust reps/sets accordingly (see Adaptations below). Ideally, you'll have weights that challenge you but allow you to maintain good form. * **Experience Level:** I've aimed this towards a beginner to intermediate level. It can be scaled up or down. * **Space:** You need enough space to safely perform each exercise. * **Warm-up/Cool-down:** These are *essential* and included in the time estimates. **Workout Schedule & Details** **Monday: Chest & Triceps** * **Warm-up (5-10 minutes):** Dynamic stretching (arm circles, torso twists, leg swings), light cardio (jumping jacks, high knees) * **Workout (40-45 minutes):** * **Dumbbell Bench Press:**
```

---

**Unverified is not false.** On 50 Gemma rollout activations, 65-68% of unverified content features were genuinely present in the source document, just not at this token position (control 25-30%). Treat unverified as *not checked*, never as *refuted*.
