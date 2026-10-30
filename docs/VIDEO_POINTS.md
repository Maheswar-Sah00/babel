# Babel demo video: every point to cover

This is the full list of points to pick from. The word-for-word 2:32 version is [VIDEO_SCRIPT.md](VIDEO_SCRIPT.md); use
this file to plan a longer cut, to swap shots, or to answer judges' questions.

Every number here was checked against the repo on 17 Oct 2026. Each comes with its source. If a number isn't in this
file, don't say it on camera.

---

## 0. Running order (about 3 minutes)

| # | Part | Time | The one thing the viewer must remember |
|---|---|---|---|
| 1 | Hook | 0:00 to 0:12 | "$10,000 buys about two languages. Which two?" |
| 2 | The numbers that started it | 0:12 to 0:40 | Everyone copies one list; players don't follow it |
| 3 | The idea, and the check that it could work | 0:40 to 1:00 | Fans of a genre cluster by country; new games have no data, their look-alikes do |
| 4 | Walkthrough | 1:00 to 2:05 | A plan, a map and a "Why?" for your game |
| 5 | Without Qloo | 2:05 to 2:20 | Take Qloo out and all four demos get the same answer |
| 6 | Proof | 2:20 to 2:45 | Written down first, tested on 257 games, honest about the weak part |
| 7 | Close | 2:45 to 3:00 | Thank you, Qloo; agents can call Babel; the link |

Too long? Cut in this order: W10 to W12 (charts, vs generic, report), then W15 (track record screen), then part 3's
second bullet. Keep parts 5 and 6 whole: they are what judges score.

---

## 1. The numbers that led to the idea

These are what you knew *before* Babel existed. Say them as a story: what you believed, what you checked, what surprised
you.

| # | Point | Exact figure | Say it like this | Source |
|---|---|---|---|---|
| N1 | Translation is expensive | Rough industry range $500 to $20,000+ per language. Babel's own estimate for a 30,000-word game: $3,157 (Ukrainian) to $4,910 (Japanese) per language, with 15% for review and testing | "For a 30,000-word game, one language costs about three to five thousand dollars." | `babel/plan.py` (`Rates`); the range is from the brief, so call it rough |
| N2 | So the budget buys two | $10,000 buys 2 full translations in the WEBFISHING demo ($7,366) | "Ten thousand dollars buys about two languages." | The demo plan |
| N3 | Everyone copies one list | Simplified Chinese, Japanese, Korean; then Portuguese-BR, Russian, Spanish, Turkish; then German, French, Traditional Chinese, Polish | "Chinese, Japanese, Korean first. Same list for a farming game and a war game." | `babel/languages.py` (`GENERIC`) |
| N4 | How hard real data is to get | 4,000 Steam indie games scanned; 833 English-only; 114 paid, released since 2023, with 500+ reviews | "We scanned four thousand Steam games to find 114 we could measure." | `backtest/step2_report.md` |
| N5 | Non-English players are real, even for English-only games | Median 19% of reviews not in English | "Even with no translation, about one review in five isn't in English." | `backtest/step2_report.md` |
| N6 | They don't follow the list | Russian 21.7%, German 11.0%, Portuguese-BR 10.3%, Spanish 9.9%, Simplified Chinese 9.8% ... Korean 3.2%, Japanese 2.6% | "The biggest group was Russian: one in five. Japanese, number two on the list? Under three percent." | `backtest/step2_report.md` |
| N7 | The list misses most of them | The list's top 3 covered 15.7% of non-English Steam reviews (71 test games); the typical mix covered 47.7% | "The copy-pasted top three covered about 16% of those players' reviews." | `backtest/final_report.md` |
| N8 | Genre decides where fans are (kill check, 8 Oct) | 15 games in 5 genres, 15 of 15 found in Qloo. Same-genre games correlate 0.50 by country, different genres 0.08 | "Fans of similar games live in similar places: 0.50 against 0.08." | `killcheck/report.md` |
| N9 | Every game's map is its own | Stardew Valley vs Slay the Spire: cell-level similarity only 0.23 over 847 shared cells | Optional, for the technical cut | `killcheck/report.md` |
| N10 | The wall: new games are invisible | 75 of 75 new indie games found in Qloo returned Qloo's default "no data" map | "A game that isn't out yet has no fans, so Qloo has no data on it." | `backtest/final_report.md`, validity check |
| N11 | The way around the wall | Fans of well-known look-alike games do exist in Qloo: 356 real fan maps in Babel's pool | "But fans of games *like* yours exist, and Qloo knows where they are." | `data/runtime/manifest.json` |

**Always add this caveat to N6 and N7** (small caption on screen is enough): English-only games under-count players who
can't read English, and that hits Chinese, Japanese and Korean hardest.

---

## 2. The numbers after Babel was built

Say these in the order they happened. The honest order is what makes them believable.

**Step 1. First try, 43 development games: not a win.**

- Top-3 hit rate was 60% with Qloo and 60% without.
- Qloo changed the pick on 8 games: 3 better, 5 worse.
- But the signal was real: Qloo tracked which games lean to which language (+0.126, p = 0.002).
- Say: "Our first test was a wash. So we stopped tuning, and wrote the real test down first."
- Source: `backtest/step3_report.md`.

**Step 2. Fixes found before the real test.**

- Raw cell averages put tiny islands at the top. Fix: popularity-weighted, at least 5 cells per country.
- Qloo returns the same generic map for games it has no data on. Fix: fingerprint it and drop it.
- One signal silently returned nothing: Qloo caps `take` at 50 and the batches were 100. Fixed and logged as a dated
  amendment.
- Source: `killcheck/report.md` (robust verdict), `backtest/PREREGISTRATION.md` (amendments).

**Step 3. The pre-registered test (written 9 Oct 2026, run once).**

| Point | Exact figure | Source |
|---|---|---|
| Games | 257 test games: 71 indie (Steam reviews) + 186 notable (Wikipedia pageviews, 13 language editions) | `backtest/PREREGISTRATION.md` |
| **Headline** | Wikipedia: Qloo made Babel's top 3 better for **87** games, the same for 66, worse for **33**; p < 0.001; +2.7 points of coverage (95% CI +0.1 to +5.4) | `backtest/final_report.md` |
| Honest second truth | Steam, small indies: 23 better, 26 same, 22 worse; +1.2 points; p = 0.50, not significant. Qloo's signal still tracked lean per language (+0.113, p = 0.001) | `backtest/final_report.md` |
| Context | Babel's top 3: 60.1% of non-English Wikipedia attention; copy-pasted list: 21.8%; typical mix without Qloo: 57.4% | `backtest/final_report.md` |
| Qloo alone | 25.9% (Steam), 26.1% (Wikipedia): Qloo works as an adjustment, not an oracle | `backtest/final_report.md` |
| A frontier LLM alone | 45.5% (Steam), 59.1% (Wikipedia): about as accurate as Babel | `docs/DECISIONS.md` section 2 |

Say: "We wrote the test down before seeing any results, then ran it on 257 real games. On 186 well-known games, adding
Qloo's fan maps made the top three better for 87 games and worse for 33. On small indie games the gain was small and
not significant, and we show that too, right in the app."

**Step 4. A flaw in our own data, reported openly.**

- 68 of the 186 Wikipedia test games had no Steam tags, so all of them got the same three look-alikes.
- The pre-registered result was left as it was.
- Exploratory re-reading, labelled as exploratory: on the 118 games with real look-alikes, +4.7 points (49 better,
  11 worse).
- Product fix: look-alikes must now share at least one tag with the game.
- Source: `docs/DECISIONS.md` section 10. If you show the +4.7, put the word "exploratory" on screen next to it.

**Step 5. The product today.**

| Point | Figure | Source |
|---|---|---|
| Languages planned | 14 | `babel/languages.py` |
| Look-alike pool | 844 well-known Steam games released before 2023 (5,000+ reviews) | `data/runtime/manifest.json` |
| Budget optimizer | Exact: checks every combination of full translations | `babel/plan.py` (`best_subset`) |
| Speed | Runtime data loads in about 0.2 s; each demo plan comes back in under a second | `babel/runtime.py`; `tools/precache_demos.py` |
| Tests | 473 automated tests, including real-browser Playwright tests | `python -m pytest --collect-only` |
| LLM guardrail | Every number in the LLM's text is checked against the evidence; if one doesn't match, code writes the text instead | `babel/explain.py` |

---

## 3. Qloo's numbers

| What | Figure | Source |
|---|---|---|
| Qloo look-ups in the kill check | 15 games, 5 genres, 15 of 15 found | `killcheck/report.md` |
| Map resolution | Cells about 156 km wide (geohash-3), 850 to 3,800 cells per world map | `killcheck/report.md`, brief section 4 |
| Reach | Median game has fans in 74 countries (robust count) | `killcheck/report.md` |
| Key markets | China, Japan, Korea, Brazil, Russia, Poland, Germany present for every game with data | `killcheck/report.md` |
| Genre signal | 0.50 same genre vs 0.08 across genres | `killcheck/report.md` |
| Default "no data" map | 3 of 15 recent hits in the kill check (Lethal Company, Content Warning, Manor Lords); 73 of the 554 pool games checked | `killcheck/report.md`; `data/runtime/manifest.json` |
| Pool checked in Qloo | 554 games: 356 real fan maps, 73 default map, 125 not in Qloo | `data/runtime/manifest.json` |
| New indie games | 75 of 75 found in Qloo have only the default map | `backtest/final_report.md` |
| Notable games' own maps | 16 of 69 have a real map, and it tracks their real language lean (+0.180, p = 0.002) | `backtest/final_report.md` |
| Signal strength | +0.113 (Steam, p = 0.001), +0.185 (Wikipedia, p < 0.001) | `backtest/final_report.md` |
| Audience example | Hearts of Iron IV fans skew 55+ (+0.93) and male (+0.44); Stardew Valley fans skew female (+0.18) | `backtest/market_insights.md` |
| WEBFISHING's look-alikes' fans | Age 25 to 29 +0.72, 30 to 34 +0.39, 35 to 44 −0.65, 55+ −0.50; female +0.16 | Demo, market notes |
| Qloo calls in the final backtest | 272 live, 780 from cache | `backtest/final_report.md` |
| Qloo responses cached in total | 2,057 | `cache/qloo/` |
| Qloo calls the demo buttons make | 0 (all from cache) | `tools/precache_demos.py --offline` |

---

## 4. Where and how Qloo is used

**In the app (what to point at on screen):**

| Where you see it | What Qloo gives | Qloo API | Code |
|---|---|---|---|
| Start: the three "games like yours" cards | Is this game in Qloo, and does it have a real fan map? | `/search` (`types=urn:entity:videogame`); `/v2/insights` heatmap + fingerprint | `qloo.find_game`, `qloo.fingerprint`, `comps.qloo_status`, `suggest.py` |
| Working: the live trace | "Poly Bridge: default map, skipped"; "not in Qloo" | same | `agent.py` |
| Plan: the three groups | The Qloo adjustment per language, the only game-specific input to the scores | `/v2/insights`, `filter.type=urn:heatmap`, world polygon | `qloo.world_cells`, `qloo.country_profile`, `plan.qloo_lift`, `plan.demand_shares` |
| The world map + country panel | Fans compared with usual, per country, game by game | same | `explore.py`, `web/static/map.js` |
| Why? | The "Qloo adjustment" step, for example +16% for Spanish | same | `explore.py` |
| Chart: "What Qloo changed" | Typical mix vs after Qloo, per language | same | `web/static/charts.js` |
| Who the fans are | Age and gender skew vs Qloo's average audience | `/v2/insights`, `filter.type=urn:demographics` | `markets.audience` |
| What these fans also like, by market | Films and music popular in each top market, re-ranked by these fans (two steps: local pool by location, then re-rank) | `/v2/insights`, `urn:entity:movie` / `urn:entity:artist`, `signal.location.query` | `markets.also_loved` |
| Track record | What Qloo measurably adds | The same heatmaps, frozen | `track_record.py`, `backtest/` |
| Report, MCP tool | The same Qloo evidence, with Qloo request IDs | | `report.js`, `mcp_server.py` |

**How, in one breath (for the voice-over):** "Babel finds three well-known games that share your Steam tags, reads
Qloo's world fan map for each, sums it per country, turns countries into languages, and asks: are fans of games like
this more or less common here than usual? That answer adjusts the typical language mix, and the budget does the rest."

**Formula (on screen only, for the technical cut):** share(L) ∝ typical mix(L) × Qloo lift(L).

---

## 5. Why Babel can't work without Qloo

Say it this way. It is true, and it holds up to a judge's follow-up question.

1. **Without Qloo, every game gets the same plan again.** Qloo's adjustment is the only game-specific input to the
   scores. Proof from the four demo buttons, at 30,000 words and $10,000:

   | Demo | Without Qloo | With Qloo |
   |---|---|---|
   | WEBFISHING | Russian + Spanish | Russian + Spanish |
   | Dawnsbury Days (tactical RPG) | Russian + Spanish | **Russian + German** |
   | Never Second in Rome (historical turn-based RPG) | Russian + Spanish | **Russian + German** |
   | A cozy farming idea (description only) | Russian + Spanish | **Russian + Simplified Chinese** |

   "Take Qloo out, and all four games get Russian and Spanish. That's the copy-paste problem again, just with better
   data." (Check: re-fit each demo's plan with the Qloo lift set to 1, using `plan.fit_budget` on the plan's
   `baseline_share` values.)

2. **The game itself has no data, and Steam can't help before launch.** 75 of 75 new indies have only Qloo's default map.
   Steam reviews by language only exist after launch, and the Steam survey is one language mix for all of Steam (as a
   ranking it covered 47.5% / 51.2%, below Babel). Qloo is where the fans of the *look-alikes* are, country by country.
3. **It measurably helps.** Adding Qloo made the top 3 better for 87 games and worse for 33 (p < 0.001).
4. **It's evidence you can check.** An LLM alone was about as accurate, but its answer is a guess you can't inspect.
   Qloo gives a map, per-country numbers, game-by-game evidence and request IDs behind every "Why?".
5. **The audience and market notes come only from Qloo.** Without it: no map, no audience, no "why".

Even when Qloo keeps the same top two (WEBFISHING), it still moves the rest of the plan. Japanese goes from 2.7% to
4.7% (Qloo adjustment +95%), Korean from 3.4% to 5.4% (+83%), Turkish from 3.4% down to 1.8% (−37%), and Simplified
Chinese overtakes Portuguese-BR for fourth place. For the cozy farming idea, Simplified Chinese goes from 10.3% to
13.3% (+24%) and overtakes Spanish, so it gets the second full translation. (The shares move less than the adjustment
because all shares are re-scaled to add up to 100%.)

**Don't say** that Babel can't make *any* plan without Qloo: it falls back to the typical mix, the same for every game.

---

## 6. Walkthrough: shot by shot

Record at 1920×1080, browser zoom 100%, light theme. Move the mouse slowly; pause on each thing before clicking.

| # | Show | Say (or point at) | 🟣 Qloo |
|---|---|---|---|
| W1 | Start screen: the dot-matrix world map with language pins | Three ways in: a Steam link, a game name, or a paragraph if there's no store page yet. Four demo buttons | |
| W2 | Click **WEBFISHING**. Three cards: Temtem, A Hat in Time, Unpacking | "Babel picks three well-known games like it and checks each one in Qloo." You can swap a card, search the pool or check any game | 🟣 |
| W3 | 30,000 words, $10,000 → **Run the plan** | "Thirty thousand words, ten thousand dollars." | |
| W4 | Working screen: the live checklist | Point at the reflect step: Super Animal Royale and Fishing Planet aren't in Qloo; Poly Bridge returned Qloo's default no-data map, so it was skipped. "It never averages in data that isn't there." | 🟣 |
| W5 | Plan headline + three groups | "Translate the whole game into Russian and Spanish. Store pages in 11 more languages: a cheap way to test those markets. Thai can wait. $7,996 of $10,000." Costs are estimates | |
| W6 | The world map (default: fans compared with usual). Hover, then click Japan | "This is Qloo's fan data for games like this, compared with usual. Click a country for the evidence, game by game." | 🟣 |
| W7 | Click a language (e.g. Spanish) | Its countries light up on the map | 🟣 |
| W8 | Zoom onto a country until the street map opens | Optional. Context only; Babel's numbers are for the whole country | |
| W9 | The **Japanese** card (it shows "Qloo adjustment: +95%"), then **+** → **Why?** | "Typical mix 2.7%, Qloo adjustment +95%, so 4.7%. Enough for a $70 store page test, not yet a $4,910 translation." (Spanish shows +16% if you'd rather open a full translation) | 🟣 |
| W10 | The four charts | Who your likely players are · What Qloo changed · Babel vs the usual list · Where the budget goes | 🟣 |
| W11 | Babel vs the usual list | The list says Chinese, Japanese, Korean first; Babel says Russian and Spanish, with the reason for each difference | |
| W12 | **Who the fans are** | Fans of the look-alikes skew 25 to 29 (+0.72) and slightly female (+0.16). Aggregate taste, never individuals | 🟣 |
| W13 | **What these fans also like, by market** | Russia, Mexico, Germany: films and music popular there, re-ranked by these fans. Say "a starting point for marketing"; they're mostly local favourites | 🟣 |
| W14 | Budget slider | Drag to $4,000: Russian only, plus 8 store pages. Drag to $15,000: four full translations (Russian, Spanish, Portuguese-BR, Polish). "The same exact optimizer re-fits it instantly." | |
| W15 | Second demo: **A cozy farming idea** | No store page, just a paragraph. The LLM suggests tags (only tags from the pool); code checks every game it names. Look-alikes: Stardew Valley, My Time at Portia, Unpacking. Plan: **Russian + Simplified Chinese**. "Different game, different plan." | 🟣 |
| W16 | **Export report** | One A4 page, print or PDF | |
| W17 | **Track record** | The backtest, recomputed live from the frozen data files; every method, per game | 🟣 |
| W18 | **Assistant** | Ask it to set the budget or show a country; it acts. Code checks every number it writes and every action it takes | |
| W19 | Optional: Take the tour, dark theme | Both run on the real interface | |
| W20 | MCP | "Other AI agents can call Babel too": `babel_language_plan`, same plan as the web app | |

---

## 7. Never say on camera

From `docs/DECISIONS.md` section 4:

- That Babel or Qloo predicts **sales, revenue, wishlists, player counts or ROI**.
- That Babel **beats AI or LLMs**. A frontier LLM alone was about as accurate.
- That **Qloo took the result from 22% to 60%**. The typical mix alone gets to 57.4%.
- That Babel is **significantly better for small indies**. It isn't, on the Steam test.
- "Captures X% of your players" without naming the measure (Wikipedia attention, or Steam reviews of English-only
  games).
- 61.4% (the S2 variant) as a headline. It wasn't the pre-registered choice.
- That "also likes" lists are personal insight. They're mostly each country's local favourites.
- +4.7 points without the word "exploratory".

---

## 8. Judge questions: short answers

| Question | Answer |
|---|---|
| "Couldn't an LLM just do this?" | "It was about as accurate in our test, and we say so. But an LLM's answer is a guess you can't inspect. Qloo gives a map, per-country numbers and the evidence behind every 'Why?'. So we let the LLM read and explain, and Qloo supply the evidence." |
| "Isn't most of the gain from the typical mix?" | "Yes, most of the gap over the copy-pasted list comes from using real language data. Qloo is what makes it game-specific: 87 better, 33 worse on 186 games." |
| "Why not use the game's own Qloo data?" | "New games don't have any: 75 of 75 we checked return the default map. That's why Babel reads look-alikes." |
| "What if Qloo has no data for the look-alikes?" | "Babel skips them and tries the next of the top six. With none valid, it says so and shows the typical mix with no map." |
| "Does this predict sales?" | "No. It estimates where non-English demand is. We never saw a game before and after translation." |
| "How do you stop the LLM inventing numbers?" | "Every number in its text has to appear in the evidence it cites, or code writes the sentence instead." |
