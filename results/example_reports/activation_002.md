# Activation 2

Reconstruction FVE **+0.721**, cosine `0.9959`. Jaccard against its own rebuild **0.400**, against an unrelated activation *0.0221*.

## What Gemma was asked

> Based on the previous purchases, generate a list of products that cater to the users interests, while also encouraging them to engage in new products related to their interests. Previous Purchases: Laptop Lenovo Y520, JBL Charge 4, PlayStation 4, Dungeons & Dragons Monster Manual.

## What Gemma wrote

<details><summary>full response</summary> The activation is token 375, 307 tokens into the response.

> Okay, based on the user's previous purchases (Lenovo Y520 Laptop, JBL Charge 4, PlayStation 4, Dungeons & Dragons Monster Manual), here's a categorized list of product recommendations, balancing catering to existing interests and introducing new related ones. I'll break it down into categories: **Gaming, Audio/Tech, D&D/Tabletop, and "Stretch" Recommendations (new areas to explore).** I'll also include *why* I'm recommending each item. **I. Gaming (Building on PS4 & Laptop - Performance & Immersion)** * **PlayStation Plus Subscription:** (Essential) - *Why:* Extends the PS4 experience with online multiplayer, free monthly games, and exclusive discounts. They already own the console, this is the logical next step. * **Gaming Headset (e.g., HyperX Cloud Alpha, SteelSeries Arctis 7):** *Why:* The Y520 is a gaming laptop, and the PS4 is a gaming console. A good headset dramatically improves immersion and communication in both environments. Look for comfort and good sound quality. * **External SSD (1TB or 2TB):** *Why:* The Y520 likely has a standard HDD or smaller SSD. An external SSD provides faster loading times for PS4 games and can also be used to expand storage on the laptop. * **PS4 Pro (if budget allows):** *Why:* A significant upgrade to their existing PS4, offering improved graphics and performance for many games. A natural progression for a gamer. * **Gaming Mouse & Keyboard (for Laptop):** *Why:* The Y520 is a gaming laptop. A dedicated gaming mouse and keyboard will enhance their PC gaming experience. Consider ergonomic options. * **Games (Tailored to their potential preferences):** * **RPG/Action-RPG:** *Horizon Zero Dawn, The Witcher 3, Elden Ring* (Based on the D&D interest, they might enjoy story-rich, character-

</details>

## What the AV said about the activation

**Segment 1** — `no_final`, everything before the final-token paragraph:

> Structured product listing format: bullet points with categorized console/gaming recommendation, establishing a recommendation timeline for PS5 upgrade.
>
> The phrase "PS5 (…" signals a parenthetical upgrade option suggestion for the Xbox Series S, implying a trade-in or conditional buy suggestion for the older PlayStation 4.
>

**Segment 2** — `final_only`, the final-token paragraph:

> Final token " ( " opens a parenthetical recommendation label "PS5 (", requiring a bracketed phrase like "if upgrading)" or "Optional: Consider Upgrade)" — likely "Trade-in Option or New Release)" or "If budget allows, upgrade to Newer Model)" or "depending on price) - Considered if transitioning from PS4" for the console option.
>

The judge sees these two separately; `full` is scored as whichever latents *either* segment conveys.

## What each cut reconstructs

| variant | FVE | Jaccard | shared | lost | made |
|---|---:|---:|---:|---:|---:|
| `full` | +0.721 | 0.400 | 14 | 13 | 8 |
| `final_only` | +0.698 | 0.412 | 14 | 13 | 7 |
| `no_final` | +0.632 | 0.300 | 9 | 18 | 3 |

## Every validated latent, and what the judge said

`shared` + `lost` is F_orig — the latents genuinely in this activation. `made` was never in it.

### SHARED — in the activation, and the rebuild recovered it

*4 of 14 carry a validated label and can be shown.*

| latent | what it responds to | full | final_only | no_final |
|---|---|---|---|---|
| `f9855` | Identifies brand names and gaming platforms within text. | **stated** | **stated** | **stated** |
| `f10155` | Verbs signifying a shift or change, often following a discussion of a problem or need. | not stated | not stated | not stated |
| `f11272` | Fires on bolded section headers introducing suggestions or categories. | not stated | not stated | not stated |
| `f15169` | Fires on mentions of PlayStation and Sony related to gaming. | **stated** | **stated** | **stated** |

### LOST — in the activation, and the rebuild lost it

*6 of 13 carry a validated label and can be shown.*

| latent | what it responds to | full | final_only | no_final |
|---|---|---|---|---|
| `f1295` | Fires on nouns describing physical objects used for a practical purpose. | **stated** | **stated** | not stated |
| `f1876` | A preposition or conjunction introducing a list or specification. | **stated** | **stated** | not stated |
| `f2989` | Mentions a time-bound promotion or exclusive opportunity. | not stated | not stated | not stated |
| `f9980` | Fires on a token immediately following a colon or em dash. | not stated | not stated | not stated |
| `f13287` | Fires on price mentions, specifically numeric values related to cost. | not stated | not stated | not stated |
| `f13752` | Code-related tokens indicating data manipulation or algorithmic steps. | not stated | not stated | not stated |

### MADE — NOT in the activation — the rebuild produced it

*3 of 8 carry a validated label and can be shown.*

| latent | what it responds to | full | final_only | no_final |
|---|---|---|---|---|
| `f1252` | The feature fires on GPU model numbers and related specifications. | **stated** | **stated** | not stated |
| `f2756` | Fires on capitalized proper nouns, frequently denoting places or brands. | **stated** | **stated** | not stated |
| `f2793` | Fires on punctuation following a numerical statistic or measurement. | not stated | not stated | not stated |

