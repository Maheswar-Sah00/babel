# Step 3 (mini): who picks the right languages?

43 English-only indie games released 2024+ (development set). Truth = each game's share of non-English reviews over 14 translation targets (Spanish = Spain + Latin America). **Raw** = which languages wrote the most reviews. **Adjusted** = which languages this game over-indexes on versus a typical English-only game (smoothed with 50 typical reviews), i.e. the game-specific part only. Top-3 hit = how many of the real top 3 a competitor's top 3 contains.

| Competitor | Top-3 hit (raw) | Spearman (raw) | Top-3 hit (adjusted) | Spearman (adjusted) |
|---|---|---|---|---|
| Generic tier list | 15% | 0.39 | 22% | 0.01 |
| Steam size | 54% | 0.68 | 19% | 0.06 |
| Typical mix (no Qloo) | 60% | 0.77 | 20% | 0.10 |
| AI alone | 19% | 0.48 | 23% | 0.09 |
| AI + typical mix | 59% | 0.74 | 22% | 0.12 |
| Qloo alone | 31% | 0.21 | 25% | 0.15 |
| Babel: typical mix x Qloo | 60% | 0.77 | 22% | 0.12 |
| Babel: Steam size x Qloo | 47% | 0.63 | 17% | 0.08 |

## Head to head (per game)

| A | B | Measure | A better | Tie | B better | Sign test p |
|---|---|---|---|---|---|---|
| Babel: typical mix x Qloo | Typical mix (no Qloo) | top-3 raw | 3 | 35 | 5 | 0.73 |
| Babel: typical mix x Qloo | Typical mix (no Qloo) | top-3 adj | 5 | 35 | 3 | 0.73 |
| Babel: typical mix x Qloo | AI + typical mix | top-3 raw | 12 | 20 | 11 | 1.00 |
| Qloo alone | AI alone | top-3 adj | 11 | 21 | 11 | 1.00 |
| Babel: typical mix x Qloo | Generic tier list | top-3 raw | 34 | 7 | 2 | 0.00 |

## Sensitive test: does the signal track which games over-index on which language?

Within each language, Spearman across the 42 games with look-alikes between the signal and the real over-index, averaged over languages. p = share of 500 within-language shuffles that score as high.

| Signal | Mean within-language correlation | p |
|---|---|---|
| Qloo lift (look-alike fan maps) | +0.126 | 0.002 |
| AI alone (its ranking) | +0.086 | 0.020 |
| AI + typical mix (its ranking) | +0.008 | 0.448 |

Qloo lift per language: Simplified Chinese +0.20, Japanese +0.13, Korean +0.26, Portuguese-BR +0.07, Russian +0.22, Spanish -0.09, Turkish -0.09, German +0.33, French +0.32, Traditional Chinese -0.17, Polish +0.16, Italian +0.23, Ukrainian +0.21, Thai -0.02

## Settings and data

- Alpha chosen by leave-one-out (typical-mix Babel): {1: 25, 0: 18}; (Steam-size Babel): {2: 33, 0: 9, 1: 1}. Alpha 0 = Qloo ignored.
- Look-alikes per game: {0: 1, 1: 3, 2: 11, 3: 28} (games without any fall back to the prior).
- AI answers that ranked all 14 languages: 86 of 86 (gaps filled in generic order).
- API calls this run: Groq 0 (cached 86), Qloo 0 (cached 85).

## Per game (top 3)

| Game | Real | Typical mix | Babel (typical x Qloo) | AI + typical | AI alone | Qloo alone |
|---|---|---|---|---|---|---|
| Jacksmith: Weapons and Warriors | Russian, Polish, Spanish | Russian, Spanish, Portuguese-BR | Russian, Spanish, Portuguese-BR | Russian, German, Simplified Chinese | Simplified Chinese, Spanish, German | Polish, Ukrainian, Russian |
| Desktop Survivors 98 | Russian, Spanish, Portuguese-BR | Russian, Spanish, Portuguese-BR | Russian, Spanish, Portuguese-BR | Russian, Simplified Chinese, Spanish | Simplified Chinese, Japanese, Korean | Korean, French, Simplified Chinese |
| Amenti | Russian, German, Spanish | Russian, Spanish, Portuguese-BR | Russian, German, Portuguese-BR | Russian, Simplified Chinese, Spanish | Simplified Chinese, Japanese, Korean | Italian, Russian, Ukrainian |
| Papa's Pizzeria Deluxe | Spanish, Portuguese-BR, Simplified Chinese | Russian, Spanish, Portuguese-BR | Russian, German, Portuguese-BR | Russian, Spanish, Portuguese-BR | Spanish, German, French | German, Polish, Portuguese-BR |
| Conquest Dark | German, Russian, Simplified Chinese | Russian, Spanish, Portuguese-BR | Russian, Simplified Chinese, German | Russian, Spanish, Portuguese-BR | Simplified Chinese, Japanese, Korean | Simplified Chinese, French, Polish |
| Deep Space Cache | German, Russian, Portuguese-BR | Russian, Spanish, Portuguese-BR | Russian, Portuguese-BR, Spanish | Russian, Spanish, Portuguese-BR | Simplified Chinese, Spanish, German | Russian, Ukrainian, Portuguese-BR |
| Bad Parenting 1: Mr. Red Face | Russian, Portuguese-BR, Spanish | Russian, Spanish, Portuguese-BR | Russian, Spanish, German | Russian, Spanish, Portuguese-BR | Simplified Chinese, Japanese, Korean | Russian, Ukrainian, Polish |
| Widget Inc. | German, Russian, Polish | Russian, Spanish, Portuguese-BR | Russian, Spanish, Portuguese-BR | Russian, German, Polish | Simplified Chinese, Japanese, Korean | Polish, Ukrainian, Russian |
| WEBFISHING | Russian, Portuguese-BR, Spanish | Russian, Spanish, Portuguese-BR | Russian, Spanish, Portuguese-BR | Russian, Spanish, Portuguese-BR | Simplified Chinese, Japanese, Korean | Korean, Traditional Chinese, Japanese |
| Nodebuster | Portuguese-BR, German, Spanish | Russian, Spanish, Portuguese-BR | Russian, Spanish, Portuguese-BR | Simplified Chinese, Russian, Spanish | Simplified Chinese, Japanese, Korean | Ukrainian, Polish, Portuguese-BR |
| Pantheon: Rise of the Fallen | German, French, Spanish | Russian, Spanish, Portuguese-BR | Spanish, Portuguese-BR, Russian | Simplified Chinese, Russian, Portuguese-BR | Simplified Chinese, Japanese, Korean | Polish, Turkish, Spanish |
| CLICKOLDING | Russian, Spanish, Simplified Chinese | Russian, Spanish, Portuguese-BR | Russian, Simplified Chinese, German | Russian, Spanish, Portuguese-BR | Spanish, German, French | Traditional Chinese, Korean, Japanese |
| Monster Prom 4: Monster Con | Spanish, Portuguese-BR, Russian | Russian, Spanish, Portuguese-BR | Russian, Spanish, German | Russian, Spanish, Portuguese-BR | Simplified Chinese, Japanese, Korean | Korean, Traditional Chinese, Russian |
| Class of '09: The Flip Side | German, Polish, Russian | Russian, Spanish, Portuguese-BR | Russian, Spanish, Portuguese-BR | Russian, Spanish, Portuguese-BR | Japanese, Simplified Chinese, Traditional Chinese | Russian, Korean, Ukrainian |
| Dawnsbury Days | Portuguese-BR, Russian, German | Russian, Spanish, Portuguese-BR | Russian, Spanish, Portuguese-BR | Russian, Simplified Chinese, Spanish | Simplified Chinese, Spanish, Portuguese-BR | Polish, Ukrainian, Russian |
| CRUEL | Spanish, Russian, Portuguese-BR | Russian, Spanish, Portuguese-BR | Russian, German, Spanish | Russian, Portuguese-BR, Spanish | Simplified Chinese, Japanese, Russian | Russian, Ukrainian, Polish |
| Mind Over Magnet | Portuguese-BR, Simplified Chinese, French | Russian, Spanish, Portuguese-BR | Russian, Spanish, Portuguese-BR | Russian, Portuguese-BR, Spanish | Spanish, German, French | Russian, Korean, Ukrainian |
| Beltmatic | Spanish, Portuguese-BR, German | Russian, Spanish, Portuguese-BR | Russian, Spanish, Portuguese-BR | Russian, Simplified Chinese, Portuguese-BR | Simplified Chinese, Japanese, Korean | Polish, Ukrainian, Russian |
| The Backrooms Deluxe | Russian, Simplified Chinese, Ukrainian | Russian, Spanish, Portuguese-BR | Russian, Spanish, Portuguese-BR | Russian, Portuguese-BR, Spanish | Simplified Chinese, Traditional Chinese, Japanese | Ukrainian, Turkish, Portuguese-BR |
| Starstruck Vagabond | Spanish, German, Portuguese-BR | Russian, Spanish, Portuguese-BR | Russian, Spanish, German | Russian, Spanish, Portuguese-BR | Simplified Chinese, Japanese, Traditional Chinese | Korean, Russian, Japanese |
| Sniper Killer | Russian, Spanish, Portuguese-BR | Russian, Spanish, Portuguese-BR | Russian, Spanish, Portuguese-BR | Russian, Spanish, Portuguese-BR | Simplified Chinese, Traditional Chinese, Japanese | Polish, Ukrainian, Spanish |
| Just Another Night Shift | Russian, Portuguese-BR, Ukrainian | Russian, Spanish, Portuguese-BR | Russian, Portuguese-BR, German | Russian, Spanish, Simplified Chinese | Simplified Chinese, Spanish, German | Ukrainian, Russian, Polish |
| Path of Achra | Simplified Chinese, Russian, French | Russian, Spanish, Portuguese-BR | Russian, Spanish, German | Russian, Simplified Chinese, Korean | Simplified Chinese, Japanese, Korean | Korean, French, Russian |
| KitHack Model Club | Simplified Chinese, German, Russian | Russian, Spanish, Portuguese-BR | Russian, Portuguese-BR, German | Russian, Simplified Chinese, Spanish | Simplified Chinese, Japanese, Spanish | Ukrainian, Polish, Portuguese-BR |
| Zoonomaly | Spanish, Russian, Simplified Chinese | Russian, Spanish, Portuguese-BR | Russian, Simplified Chinese, Portuguese-BR | Russian, Spanish, Portuguese-BR | Simplified Chinese, Spanish, German | Ukrainian, Russian, Simplified Chinese |
| 9 Days | German, French, Portuguese-BR | Russian, Spanish, Portuguese-BR | Russian, Simplified Chinese, Spanish | Russian, Spanish, Portuguese-BR | Simplified Chinese, Japanese, Korean | Russian, Ukrainian, Turkish |
| KinitoPET | Russian, Portuguese-BR, Spanish | Russian, Spanish, Portuguese-BR | Russian, Spanish, Portuguese-BR | Simplified Chinese, Russian, Portuguese-BR | Simplified Chinese, Japanese, Korean | Korean, Japanese, Traditional Chinese |
| Rift Wizard 2 | Japanese, Simplified Chinese, Russian | Russian, Spanish, Portuguese-BR | Russian, Spanish, Portuguese-BR | Russian, Simplified Chinese, Spanish | Simplified Chinese, Japanese, Korean | Simplified Chinese, French, Portuguese-BR |
| Jaded | Simplified Chinese, Russian, Portuguese-BR | Russian, Spanish, Portuguese-BR | Russian, Spanish, Portuguese-BR | Russian, Simplified Chinese, Portuguese-BR | Simplified Chinese, Japanese, Korean | Korean, Russian, Portuguese-BR |
| Orb of Creation | French, Simplified Chinese, Russian | Russian, Spanish, Portuguese-BR | Russian, Spanish, Portuguese-BR | Russian, Simplified Chinese, Spanish | Simplified Chinese, Japanese, Korean | Simplified Chinese, Japanese, Korean |
| I Am Your Beast | Russian, Spanish, Simplified Chinese | Russian, Spanish, Portuguese-BR | Russian, German, Spanish | Russian, Portuguese-BR, Spanish | Simplified Chinese, Japanese, Korean | Ukrainian, Russian, German |
| Microcivilization | German, Russian, Spanish | Russian, Spanish, Portuguese-BR | Russian, German, Portuguese-BR | Russian, Spanish, Portuguese-BR | Simplified Chinese, Japanese, Korean | Polish, Ukrainian, Russian |
| Smack Studio | Russian, Spanish, Simplified Chinese | Russian, Spanish, Portuguese-BR | Spanish, Portuguese-BR, Russian | Simplified Chinese, Russian, Japanese | Simplified Chinese, Japanese, Korean | Portuguese-BR, Spanish, Turkish |
| Into the Necrovale | Simplified Chinese, Portuguese-BR, Russian | Russian, Spanish, Portuguese-BR | Russian, Spanish, Portuguese-BR | Russian, Simplified Chinese, Spanish | Simplified Chinese, Japanese, Korean | French, Simplified Chinese, Portuguese-BR |
| Blue Prince | French, Portuguese-BR, Simplified Chinese | Russian, Spanish, Portuguese-BR | Russian, Simplified Chinese, Spanish | Simplified Chinese, Russian, Spanish | Simplified Chinese, Spanish, German | Russian, Ukrainian, Simplified Chinese |
| One Lonely Outpost | German, Portuguese-BR, French | Russian, Spanish, Portuguese-BR | Russian, Portuguese-BR, Simplified Chinese | Russian, Spanish, Portuguese-BR | Simplified Chinese, Japanese, Korean | Thai, Traditional Chinese, Korean |
| Neophyte | Russian, Spanish, Portuguese-BR | Russian, Spanish, Portuguese-BR | Russian, Spanish, Portuguese-BR | Russian, Simplified Chinese, Spanish | Simplified Chinese, Japanese, Korean | Korean, French, Thai |
| IRON REBELLION | Russian, German, Spanish | Russian, Spanish, Portuguese-BR | German, Spanish, Russian | Russian, Simplified Chinese, Spanish | Simplified Chinese, Japanese, Korean | German, Italian, Turkish |
| The Black Grimoire: Cursebreaker | German, Russian, Portuguese-BR | Russian, Spanish, Portuguese-BR | Russian, Spanish, Portuguese-BR | Simplified Chinese, Russian, Spanish | Simplified Chinese, Japanese, Korean | Traditional Chinese, Korean, German |
| Mahou Arms | Simplified Chinese, Traditional Chinese, Japanese | Russian, Spanish, Portuguese-BR | Russian, Spanish, Portuguese-BR | Russian, Portuguese-BR, Spanish | Simplified Chinese, Japanese, Korean | Traditional Chinese, Japanese, Korean |
| CUCKOLD SIMULATOR: Life as a Beta Male Cuck | Polish, Russian, Portuguese-BR | Russian, Spanish, Portuguese-BR | Russian, Portuguese-BR, Spanish | Russian, Spanish, Portuguese-BR | Portuguese-BR, Spanish, German | Portuguese-BR, Ukrainian, Spanish |
| Snacko | Simplified Chinese, Portuguese-BR, Spanish | Russian, Spanish, Portuguese-BR | Russian, Spanish, Portuguese-BR | Simplified Chinese, Spanish, Portuguese-BR | Japanese, Simplified Chinese, Traditional Chinese | Thai, Traditional Chinese, Korean |
| The Crimson Diamond | Portuguese-BR, German, French | Russian, Spanish, Portuguese-BR | Russian, Spanish, Portuguese-BR | Russian, Spanish, German | Simplified Chinese, Japanese, Korean | Simplified Chinese, Russian, French |
