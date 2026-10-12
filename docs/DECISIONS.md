# Babel: decisions (Task 0)

Written 10 Oct 2026, after the pre-registered backtest. **Status: proposed.** Items in section 8 need Maheswar-Sah00's
approval; everything else follows from the evidence and the rules in [BABEL_BRIEF.md](BABEL_BRIEF.md) section 7.

Sources (unchanged by this task):
[final_report.md](../backtest/final_report.md) (the pre-registered result),
[PREREGISTRATION.md](../backtest/PREREGISTRATION.md) (the fixed plan and decision rule),
[step3_report.md](../backtest/step3_report.md) (43-game development run),
[market_insights.md](../backtest/market_insights.md) (audience and market examples),
[step2_report.md](../backtest/step2_report.md) (Steam truth) and [killcheck/report.md](../killcheck/report.md) (kill check).

## 1. Product framing

**Babel is a localization planner for indie Steam developers.** It replaces the copy-pasted language tier list with a
game-specific, costed plan and shows the evidence behind every pick.

- **Claude** reads the game (Steam page or description) and writes the explanation from the evidence.
- **Qloo** supplies the measured taste evidence: world fan maps of look-alike games (the only game-specific input to
  the scores), the audience profile and market notes.
- **Code** produces every number. The track record is public, including where Qloo adds little.

Qloo's role, stated honestly: Qloo is an **evidence layer and a game-specific adjustment** on top of the typical
language mix, not an oracle. Without Qloo, every game gets the same list (the typical mix), with no map, no audience
and no "why". With Qloo, the ranking moves per game, and the move is measurably better on the larger truth.

Rules that follow from the evidence:

- Rank languages with **typical mix × (Qloo S1 lift)^1**, the signal and alpha the pre-registered dev step chose on
  *both* truths ([final_report.md](../backtest/final_report.md), lines 14 and 44).
  - Do not switch to S2 because it scored 61.4% on the Wikipedia test: that would be picking after seeing the
    results.
- Never rank by Qloo alone. Qloo alone covered 25.9% (Steam) and 26.1% (Wikipedia), far below the typical mix.
- Claude never produces scores ([BABEL_BRIEF.md](BABEL_BRIEF.md) section 6, Brain, item 3). This loses nothing that was measured:
  the code ranking (60.1%) and Claude alone (59.1%) were about equal.

## 2. What the evidence shows

**Top-3 coverage** is the share of a game's real non-English demand that falls in the 3 recommended languages.
Test games only, method frozen on dev games first ([PREREGISTRATION.md](../backtest/PREREGISTRATION.md)).

| Method | Steam reviews, 71 indie games | Wikipedia pageviews, 186 notable games |
|---|---|---|
| Generic tier list | 15.7% | 21.8% |
| Steam user share | 47.5% | 51.2% |
| Typical mix (no Qloo) | 47.7% | 57.4% |
| AI alone (Groq gpt-oss-120b) | 24.3% | 27.4% |
| Claude Opus 5.5 alone | 45.5% | 59.1% |
| Claude + typical mix | 48.8% | not run |
| Qloo alone | 25.9% | 26.1% |
| **Babel = typical mix × Qloo S1 (primary)** | **48.9%** | **60.1%** |

**Pre-registered test: Babel vs the typical mix, paired by game.**

| Truth | Better / tie / worse | Sign test p | Mean gain, 95% CI | Qloo S1 correlation | Verdict |
|---|---|---|---|---|---|
| Steam reviews | 23 / 26 / 22 | 0.50 | +1.2 pt (−2.5 to +5.0) | +0.113, p = 0.001 | **Weak signal only** |
| Wikipedia pageviews | 87 / 66 / 33 | < 0.001 | +2.7 pt (+0.1 to +5.4) | +0.185, p < 0.001 | **Qloo adds value** |

The correlation column is the within-language correlation with each game's real over-index on that language
(1,000-shuffle p-value). The overall pre-registered verdict is **"Qloo adds value"**: the rule needs a pass on at least
one truth, and the Wikipedia truth passes.

**Claude.** Opus 5.5 alone performed competitively:

- Coverage: 59.1% vs Babel's 60.1% on Wikipedia, and 45.5% vs 48.9% on Steam.
- Game-specific signal: stronger than Qloo's, at +0.186 (Steam) and +0.329 (Wikipedia), both p < 0.001.
- Adjusted top-3 hit (Wikipedia): 44%, vs Babel's 34%.

No paired test between Babel and Claude was pre-registered or run. **Combining Claude with Qloo has not been
evaluated and remains exploratory** until it is. The only combination tested was Claude + typical mix (Steam only,
48.8%).

**Supporting results:**

- **Kill check** ([killcheck/report.md](../killcheck/report.md)): Qloo has genre-specific world fan maps for games. Same-genre
  games correlate 0.50 by country vs 0.08 across genres.
- **Development run** ([step3_report.md](../backtest/step3_report.md), 43 games, seen before pre-registration):
  - Top-3 hit was the same with and without Qloo (60% both). Qloo changed the pick on 8 games: 3 better, 5 worse.
  - The Qloo signal correlated +0.126 (p = 0.002).
- **Own-map validity check** ([final_report.md](../backtest/final_report.md), lines 70–75): where a notable game has
  its own real Qloo map (16 of 69 found), the map tracks its real language over-index (+0.180, p = 0.002).
  - New indies: 75 of 75 found in Qloo have only the default no-data map.

## 3. Claims we can make

Use these wordings, or narrower ones.

1. **Primary (headline).** "In a test we fixed before seeing the results, on 186 games released since 2023, Qloo fan
   maps of look-alike games improved Babel's top 3 languages. The pick was better for 87 games and worse for 33
   (p < 0.001), +2.7 points of coverage."
2. **Context number.** "Babel's top 3 languages captured 60% of these games' non-English Wikipedia attention, against
   22% for the copy-pasted tier list."
   - This must always come with: most of that gap comes from data-driven language mixes, not Qloo; and the measure
     under-counts Chinese, Japanese and Korean audiences (section 5, items 2 and 6).
3. **The honest second truth.** "On 71 small English-only indie games, measured by Steam reviews, the gain was small
   and not significant (+1.2 points, p = 0.50). Qloo's signal still tracked which games over-index on which language
   (p = 0.001)."
4. "Qloo fan maps carry real, game-specific signal on both truths (correlation +0.113 and +0.185, p ≤ 0.001)."
5. "Claude Opus 5.5 alone was about as accurate, and its game-specific signal was stronger. Babel uses Claude to read
   and explain, and Qloo for the inspectable evidence. Whether combining them beats both has not been tested."
6. "New indie games have no Qloo taste data of their own (75 of 75 checked), so Babel reads well-known look-alike
   games."
7. "Fans of different games differ in age and gender." Example: Hearts of Iron IV fans skew 55+ (+0.93) and male
   (+0.44). This is descriptive Qloo data, not a tested prediction.
8. "Tested on 257 games across two independent truths." Only together with: significant on one, not on the other.

## 4. Claims we must not make

- That Qloo or Babel predicts **sales, revenue, wishlists, player counts or localization ROI**. Neither truth measures
  these, and we never observed a game before and after translation.
- That Babel or Qloo **beats Claude or "AI"**. Not tested; the numbers say "about equal".
- That **Qloo drives the jump from 22% to 60%**. The typical mix gets to 57.4% without Qloo.
- That Babel is **significantly better for small indies**. It is not significant on the Steam truth.
- "Captures X% of your foreign players / real demand" without naming the proxy (Wikipedia attention, or Steam reviews
  of English-only games).
  - This retracts the wording "Copy-paste lists capture 22% of your foreign players" from the 10 Oct chat.
- Any headline built on S2 (61.4%) or another variant that was not the pre-registered primary.
- That "also loves" lists are personal insight. They are mostly each country's local favourites
  ([market_insights.md](../backtest/market_insights.md)).

## 5. Limitations (disclose in the Track record and on Devpost)

1. **Proxies, not sales.**
   - Steam truth: who reviews an *English-only* game.
   - Wikipedia truth: attention. It includes non-players, and the wiki set is "notable" games (96 of 373 are indie).
2. **Asian languages are under-counted in both truths.**
   - Steam: English-only games lose players who cannot read English ([step2_report.md](../backtest/step2_report.md)).
   - Wikipedia (known about the sources, not measured here): it is blocked in mainland China, and most Korean readers
     use other wikis.
   - So the generic list's poor score (it puts Chinese, Japanese and Korean first) is partly built into the truths.
3. **The significant result is on notable games, not on Babel's main users** (small English-only indies). For them the
   coverage gain was +1.2 points, with a wide CI (−2.5 to +5.0) on 71 games.
4. **Modest effect.** +2.7 points on Wikipedia, and the top 3 is unchanged for many games (66 of 186 ties).
5. **Claude is as accurate.** Its game-specific signal may be partly recognition: notable games' tags and descriptions
   can identify them, and Claude's training data may cover their reception.
6. **Most of the gain over the generic list comes from the typical mix**, a data-driven baseline anyone could compute.
7. **Qloo depends on look-alikes.**
   - New indies have no own map.
   - Some well-known games also return the default map: 3 of 15 recent hits in the kill check.
   - "Top markets by fan mass" mostly follow population.
8. **Qloo data is one snapshot** (Oct 2026): the current fans of older games, not of the game being planned.
9. **What was seen when.**
   - The 43 dev games were analysed before pre-registration.
   - The Steam-truth Groq results were seen before the Claude amendment. The Wikipedia and all Claude results were not.

## 6. Fallback policy for default Qloo maps

Default maps are detected with `qloo.fingerprint(cells) == qloo.default_fingerprint()`. Look-alike status comes from
`CompPicker.resolve` ([babel/comps.py](../babel/comps.py)).

| Situation | What Babel does | What the user sees | Backtested? |
|---|---|---|---|
| A look-alike is *not in Qloo*, has *no heatmap* or has the *default map* | Skip it and take the next of the top 6 tag matches | Listed in the agent trace as "no Qloo data" | Yes (`pick`, top 6 → keep 3) |
| 3 valid look-alikes | Average their S1 lifts; plan = typical mix × lift | Normal plan, map shown | Yes |
| 1–2 valid look-alikes | Use them. Then widen once to the next 6 tag matches, or let the user swap look-alikes | "Based on N look-alikes": low-evidence badge | 1–2: yes; widening: **no** (product choice) |
| 0 valid look-alikes | Qloo lift = 1 for every language, so the plan is the typical mix | "No Qloo fan data for games like this; this is the typical mix for English-only indie games." No map. | Yes (`lifts` fills 1.0) |
| A language has no countries in the fan map | Lift 1 for that language | "No fan data for this market" | Yes |
| The game itself is in Qloo (already released) | Never used in scores. Its map may be shown only if it is real, labelled "since launch". | Optional "since launch" check | Validity check only (+0.180 on 16 games) |

A default map is never drawn and never averaged in. Babel never pretends to have Qloo evidence it does not have.

## 7. Measured vs estimated: labelling rules

| Kind | Examples | Comes from | Label |
|---|---|---|---|
| Measured (backtest) | Coverage %, better/tie/worse, p-values, correlations | `backtest/final_report.md` | "Measured on N games"; link to Track record |
| Qloo data | Fan-map scores, per-language lift, audience skew, "also loves" | Qloo API via `babel.qloo` | "Qloo data: aggregate taste, not individuals" |
| Babel score | Per-language demand score, ranking, the three groups | `babel/plan.py` (code) | "Relative score, not a player count" |
| Estimate | Translation cost per word and per language, total cost, budget fit | Editable defaults plus user input | "Estimate"; editable |
| AI text | Explanation; description → tags or look-alikes | Claude | "Written by Claude from the evidence above"; kept visually apart from Qloo data |

Babel never shows projected sales, revenue, ROI or "X% more players".

## 8. Decisions that need Maheswar-Sah00's approval

1. **Headline.**
   - Recommended: lead with claim 1 (Qloo vs no Qloo, p < 0.001) and give claim 2 (60% vs 22%) as context with its
     caveats.
   - Not recommended: the brief's version, which puts 60% vs 22% first next to "adding Qloo beats…", and reads as if
     Qloo made the whole gap.
2. **Pitch line.**
   - Recommended: replace "The AI knows who's famous; Qloo knows who this audience likes" with **"Claude reads your
     game; Qloo shows where its fans are."**
   - Reason: our own data shows Claude's game-specific signal is stronger, so the old line implies something we
     measured to be false.
3. **Exploratory task 0b** (Claude + typical mix × Qloo, cross-validated on the test games).
   - Cost: about $1 of Claude calls, mostly cached.
   - It can only be reported as exploratory; no fresh games remain for a confirmatory test.
   - Recommended: run it only if the extra claim would change the pitch.
4. **Product prior** (brief, section 10, item 6).
   - Recommended: the typical English-only mix as the default, because it is what was tested.
   - A blend with Steam user share is untested; offer it only as a labelled toggle, or not at all.

## 9. Repository and publication (Task 1)

**Published:**

- code: `babel/`, `backtest/` (scripts, reports, frozen datasets, charts), `killcheck/`, `tools/`;
- docs: `docs/`, `README.md`, `CLAUDE.md`;
- setup: `LICENSE` (MIT), `requirements.txt`, `.env.example`.

**Not published** (git-ignored, kept locally):

| Path | Why |
|---|---|
| `.env` | API keys |
| `cache/` | Raw API responses, about 1 GB. Raw Qloo data stays private, and the committed CSVs plus the scripts are enough to reproduce the results. |
| `data/runtime/` | Precomputed runtime data (`tools/build_runtime.py`, about 2 MB): per-country Qloo fan-map sums of the pool's games, so it is Qloo-derived and private like `cache/`. Rebuilt from the cache in about a minute with no network; a deployment needs it copied to the server (decision pending). |
| `spike/` | Moved out of the repo on 12 Oct 2026; see below |

**`spike/`: moved out of the repo** (Maheswar-Sah00's choice, 12 Oct 2026) to `../Oloo-archive/spike/`, next to the
project folder, all 96 files. It is not published. The reasons:

- It holds the abandoned *Crossover* concept (film-dubbing references): actors, brands, Spain/Japan/India swaps.
  None of it is used by Babel, and a judge browsing the repo would find an unrelated project.
- Its scripts call the APIs directly with `requests`, bypassing `babel.net`'s caching and throttling. That breaks the
  brief's section 7 rule if anyone re-runs them.
- The Qloo facts it found that matter for Babel are already recorded in the brief, section 4:
  - `filter.results.entities` + location drops entities;
  - interests + location swamps the location.
- Nothing is deleted, so it stays available. `.gitignore` still lists `/spike/` in case it is ever moved back.

**Secret scan:** `python tools/check_secrets.py` checks every publishable file and all git history for the `.env`
values and common key formats. It must print `OK` before any push.

**Decided (10 Oct 2026):**

- Public repository: `github.com/Maheswar-Sah00/babel` (empty so far).
- Commits are authored by Maheswar-Sah00 only, with no co-author or "generated with" lines.
- Nothing is committed or pushed yet, by choice.

**Decided (12 Oct 2026):** `spike/` stays out of the public repo (moved out of the project folder).

## 10. Data-quality finding in the Wikipedia set (found 10 Oct 2026, Task 6)

**The flaw:**

- 139 of the 372 Wikipedia-set games (68 of the 186 test games) have no SteamSpy tags.
- The look-alike picker therefore gave all of them the same three look-alikes: Counter-Strike 2, Terraria and
  Tom Clancy's Rainbow Six Siege (`backtest/data/wiki_comps.csv`, overlap 0).
- For those games the "Qloo signal" was not game-specific.
- The Steam set is not affected: every look-alike there shares tags with its game (lowest overlap 0.12).

The pre-registered result stands as reported. It is not re-run or changed.

**Exploratory re-reading** of `backtest/data/final_predictions_wiki.csv` (post hoc, so not confirmatory):

| Wikipedia test games | Babel vs typical mix | Better / tie / worse | Sign test |
|---|---|---|---|
| All 186 (pre-registered) | 60.1% vs 57.4% (+2.7 pts) | 87 / 66 / 33 | p < 0.001 |
| 118 with tags (real look-alikes) | 61.4% vs 56.7% (+4.7 pts) | 49 / 58 / 11 | p < 0.0001 |
| 68 without tags (same 3 look-alikes) | 57.8% vs 58.6% (−0.8 pts) | 38 / 8 / 22 | n/a |

**What it means:** the untagged games diluted the result. Where look-alikes are real, the Qloo gain is larger.

**Allowed wording:** "Exploratory: on the 118 test games whose look-alikes share tags with them, +4.7 points
(49 better, 11 worse)." It must always be labelled exploratory and shown next to the pre-registered numbers.

**Product fix:** the planner now requires look-alikes to share at least one tag (`min_overlap=0` in `CompPicker.pick`).
A game with no tags gets no look-alikes and an explicit fallback; it never gets arbitrary ones. The backtest builders
keep the old default, so they still reproduce their data.
