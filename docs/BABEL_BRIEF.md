# Babel: end-to-end project brief (for the planner)

**Who this is for:** an AI planner (ChatGPT) that will turn this brief into **one prompt per task**. Each prompt will be
pasted into **Claude Code**, an AI coding agent that works directly inside this repository, runs commands, and already
has the context in this file (via `CLAUDE.md`). Your job is to plan and write those prompts. Section 9 shows the format.
Status is as of **10 Oct 2026**.

---

## 1. The hackathon

| Item | Detail |
|---|---|
| Event | Qloo Agentic Hackathon 2026 (Devpost: qloo.devpost.com). Theme: "Agents, but with taste." |
| Deadline | **30 Oct 2026, 11:45 pm ET** (31 Oct, 9:15 am IST). Target: submit 29 Oct. Feature freeze 25 Oct. |
| Must submit | Hosted, working demo usable end to end (no local-only); public repo with run instructions; MIT licence visible in the repo; text description of features and why it is Qloo-powered. Video not required. |
| Litmus test | "If your submission would work the same without Qloo, you're building the wrong thing." |
| Judging | Stage 1 pass/fail (fits theme, uses Qloo API). Stage 2, equal weight: Technological implementation, Design, Potential impact, Quality of the idea. Judges may score from text and images only. |
| Judges | Jason Calacanis (angel investor), Mike Diolosa (Qloo CTO), Nicole Seligman (OpenAI board), Todd Boehly (Eldridge), Cedric the Entertainer, Michael Abrams (Live Nation EVP). |
| Prizes | $15k / $6k / $4k. **Bonus track:** Calacanis personally invests $25k in his favourite entry (verify on Devpost). |
| Competition | 804 registered participants (Devpost, 8 Oct); ~100 public repos. Crowded: travel, group outings, relocation, tour routing. Only one game-related entry (FirstPlayable: which comparable games to lead a pitch with). **Nobody does translation/market decisions for games.** |

## 2. The problem and the product

**Problem.** An indie game developer has a few thousand dollars for translation; translating costs $500 to $20,000+ per
language, so they can afford 2 or 3 languages. Everyone copies the same generic tier list (Simplified Chinese, Japanese,
Korean first; then Brazilian Portuguese, Russian, Spanish, Turkish; then German, French, Traditional Chinese, Polish),
whatever kind of game they made. A cozy farming game and a war strategy game get the same advice.

**Babel** tells an indie developer which languages to translate their Steam game into, as a costed plan:

- **Input:** a Steam store link, or a game name, or a free-text description (for games with no store page yet), plus word
  count and translation budget.
- **Output:** every language in one of three groups (*translate the whole game* / *translate the store page only* /
  *skip for now*), with cost, a world map of where fans of games like this are, the audience profile, "what these fans
  also love" per top market, a side-by-side against the generic list with reasons, and a "why" link behind every number.
- **How:** a new game has no fans yet, so Babel finds 3 well-known **look-alike games** (by Steam tag overlap), reads
  **Qloo's world fan maps** for them, turns countries into languages, and combines that with the **typical language mix**
  of games like it. Qloo also supplies the audience profile (age/gender skew) and the per-market "also loves" lists.
- **Proof:** a pre-registered backtest on real games (section 3) and a Track record screen.

**Users:** solo/small indie studios on Steam (main user); small publishers (5–20 games a year, the likeliest payer);
translation companies (a free report as a lead tool). Not for: big studios, mobile games.

**Pitch line (honest):** "The AI knows who's famous; Qloo knows who this audience likes." For Babel: the copy-pasted list
is folklore; Babel is a measured, game-specific plan, and we publish how well it does on real games.

## 3. What has been proven so far (evidence)

All scripts and reports are in the repo; numbers below are from them.

1. **Kill check** (`killcheck/report.md`): Qloo has global, genre-specific fan maps for video games. 15/15 test games found;
   3 recent hits (Lethal Company, Content Warning, Manor Lords) return an identical *default* map = no real data. Robust
   aggregation: same-genre games correlate 0.50 by country vs 0.08 across genres; median 74 countries per game.
2. **Ground truth** (`backtest/step2_report.md`): 114 paid, English-only indie games released 2023+, 500+ Steam reviews.
   Average share of non-English reviews: Russian 21.7%, German 11.0%, Portuguese-BR 10.3%, Spanish 9.9%, Simplified
   Chinese 9.8%, French 8.5%, Polish 5.5%, Korean 3.2%, Turkish 3.1%, Japanese 2.6%, Spanish-LatAm 2.4%, Italian 2.3%,
   Traditional Chinese 1.2%, Ukrainian 1.2%, Thai 0.4%. (English-only games under-count players who cannot read English,
   which hits Asian languages hardest; say so openly.)
3. **Development backtest, 43 games** (`backtest/step3_report.md`): top-3 hit rate: generic list 15%, Steam user share
   54%, typical mix (no Qloo) 60%, AI alone (Groq) 19%, Babel (typical × Qloo) 60%. Qloo's fan-map signal tracks which
   games over-index on which language: within-language correlation +0.126 (p = 0.002); AI alone +0.086.
4. **Pre-registered final backtest** (`backtest/PREREGISTRATION.md`, `backtest/evaluate.py` → `backtest/final_report.md`).
   **Overall verdict: "Qloo adds value"** (passes on the Wikipedia truth, weak on the Steam truth). Top-3 coverage = share
   of a game's real non-English demand that falls in the 3 recommended languages:

   | Method | Steam reviews (71 indie test games) | Wikipedia pageviews (186 notable test games) |
   |---|---|---|
   | Generic tier list | 15.7% | 21.8% |
   | Steam user share | 47.5% | 51.2% |
   | Typical mix (no Qloo) | 47.7% | 57.4% |
   | AI alone (Groq gpt-oss-120b) | 24.3% | 27.4% |
   | Claude Opus 5.5 alone | 45.5% | 59.1% |
   | Claude + typical mix | 48.8% | (not run) |
   | **Babel = typical mix × Qloo fan maps** | **48.9%** | **60.1%** (fan-mass variant 61.4%) |

   - Wikipedia: Babel beats the typical mix on 87 games, ties 66, loses 33 (p < 0.001; +2.7 points, 95% CI +0.1 to +5.4).
     Steam: +1.2 points, not significant (p = 0.50).
   - Game-specific signal (within-language correlation with real over-index): Qloo fan maps +0.113 (Steam) / +0.185
     (Wikipedia), both p ≤ 0.001; Groq AI +0.027 / +0.112; **Claude Opus 5.5 +0.186 / +0.329, stronger than Qloo.**
     Caveat: the Wikipedia games are famous, so Claude may partly recognise them from tags and descriptions.
   - Data-quality note (found later): 68 of the 186 Wikipedia test games had no SteamSpy tags and got the same three
     arbitrary look-alikes. Exploratory re-reading without them: +4.7 points (49 better, 11 worse). See
     `docs/DECISIONS.md` section 10; the pre-registered numbers above stand.
   - Qloo has no taste data for new indie games themselves: 75 of 100 sampled Steam-set games are in Qloo, **all 75 with
     the default map**. For notable games 16 of 69 have a real map. This is why Babel uses older look-alike games.
   - **Honest reading:** Qloo measurably improves the plan over the best non-AI baseline, and its improvement is
     significant on the bigger truth. Claude alone is about as accurate on coverage and has a stronger game-specific
     signal. So the strongest product is **Claude + Qloo together** (Claude proposes and explains; Qloo supplies measured,
     inspectable evidence: fan maps, audience profiles). Whether combining them beats both is untested (exploratory).
5. **Market insights** (`backtest/market_insights.md`): Qloo audience profiles are strongly game-specific (Hearts of
   Iron IV fans: 55+ +0.93, male +0.44; Stardew Valley: female +0.18). "Top markets by fan mass" mostly follow population.
   "What these fans also love" per country is mostly the country's local favourites (useful flavour, weakly personal).

## 4. Verified facts about the data sources (do not re-derive)

**Qloo (hackathon API).** Base URL `https://hackathon.api.qloo.com`, header `X-Api-Key`.
- `/search?query=&types=urn:entity:videogame` works. Exact-name matching needs cleaning (®, ™, "Definitive/GOTY Edition",
  "(2016)", 2 vs II); `babel.qloo.search_game` handles it.
- **Heatmaps** (`/v2/insights?filter.type=urn:heatmap&signal.interests.entities=<id>`) **require a location**. A world
  WKT polygon (`babel.qloo.WORLD`) in `filter.location` gives a global map (850–3,800 geohash-3 cells). Each cell has
  `affinity`, `affinity_rank`, `popularity`.
- Averaging raw cell affinity by country ranks tiny islands first: always use `babel.qloo.country_scores` /
  `country_profile` (popularity-weighted, ≥5 cells per country).
- Games without real data return one identical **default map**; detect with `babel.qloo.fingerprint` vs
  `default_fingerprint()`. About 17% of popular pre-2023 games do.
- **Tag-signal heatmaps return empty** on this key (tried genre/keyword/audience tags, world and country). So a
  description must be turned into look-alike games, not tags.
- `take` is capped at **50**. `filter.results.entities` + a location signal silently drops many entities.
- Combining `signal.interests.entities` with a location in one query swamps the location (results stop being local):
  use two steps (local pool by location only, then re-rank with `filter.results.entities` + the interest signal).
- `urn:demographics` insight works (age bands and gender skew vs average). Several entity IDs can be combined in
  `signal.interests.entities` (some single games, e.g. Temtem, have no demographics on their own).
- Location-only pools of films and music are "popular in" a country, not always local (Mexico's films are mostly
  Hollywood); the re-rank step without a location keeps results inside the pool (`babel/markets.py`).
- Results are deterministic and comparable across calls.

**Steam / SteamSpy.** Public, no key. `store.steampowered.com/api/appdetails?appids=` (type, supported_languages HTML,
release_date, genres, is_free, short_description); `store.steampowered.com/appreviews/<id>?json=1&language=<code>&
purchase_type=all&filter=all&num_per_page=0` gives exact per-language review totals. SteamSpy `request=tag|appdetails|all`
(tags with vote counts; `all` once per minute). SteamSpy review counts lag Steam's (~0.77×). Steam occasionally answers
`null` or drops DNS: retries are built into `babel.net`.

**Wikipedia.** Wikidata P1733 (Steam application ID) → article titles per language; Wikimedia pageviews API
(needs a User-Agent; ~1 request/second or it returns 429). Small indies rarely have non-English articles.

**LLMs.** Groq (`openai/gpt-oss-120b`, free, slow, frequent 429s) and **Claude** (Anthropic API, key in `.env`; models
available include `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`). `babel.llm.ask_claude_json` uses Opus 5.5,
medium effort, JSON-schema output, server-side fallbacks; ~$0.003 per ranking call; budget ~$25 (set a spend cap in the
Anthropic Console). **Google Trends is unusable** from this machine (429 + broken `pytrends`).

## 5. The repository today

```
babel/            shared library (reuse it; do not re-implement)
  net.py          throttled HTTP, retries (429/5xx/network), per-host call counters
  qloo.py         cached Qloo client, WORLD polygon, search_game, world_cells, fingerprint, country_scores/profile
  steam.py        cached Steam store + SteamSpy helpers (appdetails, review_total, languages, release_date)
  wiki.py         Wikidata + Wikipedia pageviews
  llm.py          cached Groq JSON calls; cached Claude JSON-schema calls (+ parallel helper)
  comps.py        CompPicker: look-alike pool (844 well-known pre-2023 games), IDF-weighted tag overlap, Qloo validity
killcheck/killcheck.py, killcheck/report.md    the kill check
backtest/
  build_dataset.py   Steam set (test_games.csv, truth_reviews.csv, comps.csv, step2_report.md)
  build_wiki_set.py  Wiki set (wiki_games.csv, wiki_comps.csv, truth_wiki.csv)
  evaluate.py        final pre-registered evaluation -> final_report.md, data/final_*.csv, data/final_coverage.png
  compare.py         the earlier 43-game development comparison (step3_report.md)
  market_insights.py demographics + "also loves" examples -> market_insights.md
  PREREGISTRATION.md the fixed plan and decision rule (with dated amendments)
  data/              datasets, predictions, charts
spike/            earlier, abandoned "Crossover" concept experiments (decide whether to keep or delete before publishing)
cache/            every API response, git-ignored (never re-requested; deleting it costs API calls and time)
.env              QLOO_API_KEY, GROQ_API_KEY, ANTHROPIC_API_KEY (git-ignored; never print or commit)
LICENSE (MIT), .gitignore, README.md, requirements.txt, .env.example
tools/check_secrets.py   pre-publication secret scan (must print OK before any push)
```

Environment: Windows 11, Git Bash and PowerShell, Python 3.12 (pandas, scipy, matplotlib, requests, python-dotenv,
reverse_geocoder, anthropic 1.13.0 installed), Node 22.17. **Nothing is committed to git yet**, and no GitHub repo exists.

## 6. What to build: the brain and the body

### Brain (Python, in `babel/`)

1. **Runtime data, precomputed once** (so the live demo needs almost no live API calls):
   - look-alike pool: names, tag weights, Qloo id, validity (valid / default map / not found), and per-language fan-map
     scores for the 14 targets (`pool.json` or Parquet). The backtest checked 285 of 844 pool games in Qloo; the rest
     need ~2 calls each (check the Qloo quota with the organisers first).
   - typical language mix (from `truth_reviews.csv`), Steam user share by language (Sep 2026 survey, in `evaluate.py`),
     per-word translation rates (editable defaults, labelled as estimates).
2. **Planning engine** `babel/plan.py`, deterministic and testable: input (Steam appid, name or description; word count;
   budget) → look-alikes → per-language demand score (prior × Qloo lift, alpha as chosen by the backtest) → cost per
   language → budget optimiser → three groups + evidence object. Numbers come only from code, never from an LLM.
3. **Agent layer** `babel/agent.py`: runs the steps and emits a live trace (plan → act → reflect → verify → explain):
   read Steam page or description → pick look-alikes (if fewer than 2 valid, widen the search or ask the user to pick)
   → fan maps → combine → cost → market notes (demographics + local favourites, two-step) → explanation. Claude is used
   only to (a) turn a description into Steam-style tags or candidate look-alikes, and (b) write the plain-English
   explanation **from the evidence object**. Claude never produces scores.
4. **MCP tool** `babel_language_plan(steam_url | description, word_count, budget)` returning the plan as JSON, so other
   agents can call Babel (official Python MCP SDK).

### Body

5. **API** (FastAPI): `POST /plan` (streams agent steps with Server-Sent Events, then the plan), `GET /track-record`,
   `GET /health`; MCP mounted on the same app. Keys stay server-side. Rate limit per visitor; cache plans.
6. **Frontend**, four screens (Design is a judging criterion):
   - **Start:** one input (Steam link, name or description), three look-alike cards the user can swap, word count, budget.
   - **Working:** live checklist of agent steps, each ticking as it finishes.
   - **Your plan:** headline card ("Translate X, Y, Z; store page only for A, B"), world map coloured by fan demand,
     three language groups with cost, budget slider that recomputes instantly on the client, Babel-vs-generic list with
     reasons, market notes, "why" links to the Qloo evidence, a fixed note that Qloo data describes aggregate taste, not
     individuals.
   - **Track record:** the backtest results (honest, including where Qloo only adds a little), per-game predicted vs real.
   - Shareable one-page report (print or PDF).
7. **Hosting:** always-on (judges must not hit a 50-second cold start). Demo games load from cache. Public repo, README
   with run instructions, `.env.example`.

## 7. Rules every prompt must keep

- Reuse `babel/` modules and the cache; never call an API without caching through `babel.net`/the existing clients.
- Never print, log, commit or ship keys; nothing secret in the frontend bundle.
- Qloo calls are limited: batch where possible (`take` ≤ 50), never re-request cached data.
- Do not change `backtest/PREREGISTRATION.md` decisions or re-run the full backtest unless the task says so.
- Safety: no personal data to Qloo; segments are described by taste, never by ethnicity or other protected traits;
  every estimate is labelled as an estimate; the UI separates Qloo data from LLM text.
- Every task ends with a verifiable check (a command that runs, a test that passes, a screenshot of a page).
- Keep the code style already in the repo (short docstrings, small functions, no heavy frameworks unless the task needs
  them).

## 8. Task list (in order; each becomes one prompt)

| # | Task | Done when |
|---|---|---|
| 0 | Read `backtest/final_report.md`; summarise the verdict and decide the framing with the user (see "decision" below). | A short decision note in `docs/DECISIONS.md` |
| 1 | Tidy and publish: decide on `spike/`, add `README.md` stub, `.env.example`, `requirements.txt`, `CLAUDE.md`; first commit; create the public GitHub repo (confirm the account first). | Repo public, licence visible, no secrets in history |
| 2 | Precompute runtime data (pool + Qloo validity + per-language scores, typical mix, rates). | Data files exist; a script rebuilds them from cache |
| 3 | `babel/plan.py` planning engine + unit tests (incl. budget optimiser and three groups). | `pytest` passes; CLI prints a plan for 3 example games |
| 4 | Description input: Claude turns a description into Steam-style tags / candidate look-alikes (JSON schema). | Same plan pipeline works from text only |
| 5 | Market notes (demographics + two-step local favourites) with caching. | Notes for the 3 example games |
| 6 | `babel/agent.py`: step trace, reflection (too few look-alikes, sparse tags), evidence object, Claude explanation from evidence. | CLI shows the trace and the explanation |
| 7 | FastAPI app: `/plan` (SSE), `/track-record`, `/health`, rate limit, plan cache. | `curl` streams steps and returns a plan |
| 8 | MCP tool mounted on the app. | An MCP client lists and calls the tool |
| 9 | Frontend: Start and Working screens wired to the API. | Live run from the browser |
| 10 | Frontend: Plan screen (map, groups, slider, vs-generic, market notes, why links). | All parts render for 3 demo games |
| 11 | Frontend: Track record screen + one-page report. | Matches `final_report.md` numbers |
| 12 | Deploy (always-on) + demo games pre-cached + error states. | A stranger completes the flow on the live URL |
| 13 | Usability test with 3 people + fixes. | 3 of 3 get a plan without help |
| 14 | README, Devpost text (problem → what the agent does → why Qloo → backtest table → honest limits → business model for the bonus track), 3–5 screenshots. | Submitted by 29 Oct |

**Decision for task 0.** The pre-registered verdict is "Qloo adds value" (section 3, item 4). Decide with the user:
- Headline claim (supported): "On 186 games, Babel's top 3 languages capture 60% of real foreign demand vs 22% for the
  copy-pasted list; adding Qloo beats the same method without it (p < 0.001)."
- Must also be said: Claude Opus 5.5 alone is about as accurate (59%), and its game-specific signal is stronger. So
  Babel should use Claude **and** Qloo, with Qloo as the measured evidence layer (fan map, audience, why links).
- Optional exploratory task 0b (cheap, mostly cached): test "Claude + typical mix × Qloo" on the test games with
  cross-validation, clearly labelled exploratory (no fresh games remain for a confirmatory test).

## 9. Prompt format for Claude Code

Write each prompt like this (short; Claude Code reads the repo and `CLAUDE.md` itself):

```
TASK <n>: <title>
Context: Babel (see docs/BABEL_BRIEF.md). Relevant files: <paths>.
Goal: <one or two sentences>.
Inputs / outputs: <files, endpoints, data shapes>.
Constraints: <task-specific rules, plus "follow section 7 of the brief">.
Done when: <commands to run and what they must show>.
Report back: <what to summarise; any decision you need from me>.
```

One task per prompt. If a task needs a decision only the user can make (hosting provider, model for the live app,
GitHub account, keeping `spike/`), the prompt should tell Claude Code to ask instead of guessing.

## 10. Open decisions for the user

1. Framing after the final verdict (task 0).
2. Hosting: an always-on service (e.g. Railway, Fly.io or a paid Render instance) vs free tiers with cold starts.
3. Claude model for the live app: Opus 5.5 (best) vs Sonnet 5.5 (about half the price); spend cap amount.
4. Decided: the public repo is `github.com/Maheswar-Sah00/babel`; commits are authored by Maheswar-Sah00 only (no
   co-author or "generated with" lines). Commit and push only when the user says so.
5. Keep or delete `spike/` (abandoned Crossover experiments) before the repo goes public.
6. Product prior: the typical English-only mix (best predictor in the backtest) vs a blend with Steam user share (to
   reflect players who only buy translated games). The backtest cannot measure that second group.
7. Rotate the Qloo, Groq and Anthropic keys after the hackathon (they appeared in chat).
