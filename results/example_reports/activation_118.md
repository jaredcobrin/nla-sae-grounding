# Activation 118

Reconstruction FVE **+0.580**, cosine `0.9938`. Jaccard against its own rebuild **0.429**, against an unrelated activation *0.0226*.

## What Gemma was asked

> an or a operating system

## What Gemma wrote

<details><summary>full response</summary> The activation is token 87, 73 tokens into the response.

> You're asking about whether to use "a" or "an" before "operating system." The correct choice is **"an operating system."** Here's why: * **The Rule:** We use "an" before words that *begin with a vowel sound* (a, e, i, o, u). * **"Operating" starts with a vowel sound:** Even though "operating" starts with the letter "o," it's pronounced with an "ah" sound (like "or"), which is a vowel sound. Therefore, it's grammatically correct to say "an operating system." Let me know if you'd like more examples!

</details>

## What the AV said about the activation

**Segment 1** — `no_final`, everything before the final-token paragraph:

> Structured phonetics lesson format: explanation of a word pronunciation guide, with a breakdown of the mnemonic "e" sound in "education."
>
> The phrase "The key is the vowel sound /e/. Remember that 'edu' starts with..." signals a phonetics rule clarification, requiring the key distinction.
>

**Segment 2** — `final_only`, the final-token paragraph:

> Final token " ** " ends a header label ("**Remember the vowel /e/.**"), immediately requiring the relevant phonetic rule or example — likely "The word 'education'" or "The pronunciation despite the 'edu' sound" or "The actual vowel sound in 'education' is..." or "Applying it: the word begins with..." targeting the trick of the sound.
>

The judge sees these two separately; `full` is scored as whichever latents *either* segment conveys.

## What each cut reconstructs

| variant | FVE | Jaccard | shared | lost | made |
|---|---:|---:|---:|---:|---:|
| `full` | +0.580 | 0.429 | 6 | 4 | 4 |
| `final_only` | +0.576 | 0.500 | 6 | 4 | 2 |
| `no_final` | +0.312 | 0.188 | 3 | 7 | 6 |

## Every validated latent, and what the judge said

`shared` + `lost` is F_orig — the latents genuinely in this activation. `made` was never in it.

### SHARED — in the activation, and the rebuild recovered it

*2 of 6 carry a validated label and can be shown.*

| latent | what it responds to | full | final_only | no_final |
|---|---|---|---|---|
| `f769` | Fires on the immediately following token after a question mark. | not stated | not stated | not stated |
| `f1267` | Fires on conjunctions and prepositions connecting clauses or phrases. | not stated | not stated | not stated |

### LOST — in the activation, and the rebuild lost it

*1 of 4 carry a validated label and can be shown.*

| latent | what it responds to | full | final_only | no_final |
|---|---|---|---|---|
| `f4793` | Fires on the start of a bulleted list item or section heading. | not stated | not stated | not stated |

### MADE — NOT in the activation — the rebuild produced it

*0 of 4 carry a validated label and can be shown.*

*(none labelled)*

