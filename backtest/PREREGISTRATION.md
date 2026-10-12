# Babel backtest: pre-registered plan

Written 9 Oct 2026, before the fresh test results existed. The development results (43 games, `step3_report.md`) were
already seen; everything tuned is tuned on development data only.

## Question

Does Qloo data improve which translation languages we recommend for a game, compared with the best method that does not
use Qloo?

## Data

| Set | Games | Truth | Split |
|---|---|---|---|
| Steam set | Paid, English-only indie games released 2023+, 500+ Steam reviews | Share of non-English Steam reviews per language (14 targets) | **Dev** = the 43 games already analysed; **Test** = every other game |
| Wiki set | Notable games released 2023+ with a Steam ID and Wikipedia articles in 3+ of 13 target languages | Share of non-English Wikipedia pageviews per language edition (13 wikis) | Random 50/50 split by appid (seed 7): dev / test |

Every competitor sees only pre-launch information: Steam tags, store description, look-alike games. Never the game's
name, reviews or pageviews.

## Competitors

- **Without Qloo:** generic tier list; Steam user share by language; typical mix (average truth of the *other* games in
  the same split); AI alone (Groq gpt-oss-120b, tags + description + look-alikes); AI + typical mix (Steam truth only).
- **With Qloo:** Qloo alone; Babel = typical mix × (Qloo lift)^alpha, for each Qloo signal:
  - S1 look-alike fan maps, affinity (popularity-weighted, ≥5 cells per country);
  - S2 look-alike fan maps, fan mass (affinity × popularity share per language);
  - S5 per-country affinity of the look-alikes (entity insights with a location signal).
- **Validity check, not a competitor:** S4, the game's own Qloo fan map (only exists after launch).

## Choices fixed on dev, then frozen for test

1. Primary Qloo signal: the S1, S2 or S5 signal with the highest mean within-language correlation on the dev games.
2. alpha: the value in {0, 1, 2, 4, 8, 16, 32} with the best mean top-3 coverage on dev (ties → smaller alpha).
3. The typical mix used for a test game is the average over the dev games (no test truth is used).

## Measures (on test games)

- **Primary:** top-3 coverage, the share of the game's real non-English demand that falls in the 3 recommended
  languages (Babel vs typical mix, paired by game).
- Secondary: top-3 hit rate; within-language correlation between the Qloo signal and the real over-index (permutation
  p-value, 1,000 shuffles); the same for AI alone.

## Decision rule

- **Qloo adds value** if, on the test games of at least one truth, Babel's mean top-3 coverage beats the typical mix
  (one-sided paired sign test p < 0.05) **and** the primary signal's within-language correlation is positive (p < 0.05).
- **Qloo adds a weak signal only** if the correlation test passes but coverage does not.
- **No measurable value** if neither passes. Babel's language engine would then be presented as data-driven but not
  Qloo-driven, and the project re-scoped.

All results are reported, including the ones that go against Babel.

## Amendments

- **10 Oct 2026, before any Claude result existed:** added **Claude alone** and, on the Steam truth, **Claude + typical
  mix** (Claude Opus 5.5, medium effort, JSON-schema output, the exact prompt the Groq AI gets) as extra competitors
  without Qloo, so that Qloo is also compared with the strongest available AI. They are evaluated on test games only and
  do not change the decision rule above, which compares Babel with the typical mix.
- **10 Oct 2026, bug fix:** the S5 signal (per-country entity insights) had silently returned nothing because Qloo caps
  `take` at 50 and the batches were 100. Batches are now 50. S5's dev selection is unchanged in method.
- The Steam-truth results with the Groq AI were already seen when these amendments were written. The Wikipedia-truth
  results and every Claude result were not.
