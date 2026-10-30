# Devpost submission: Babel

Copy each block into the matching Devpost field.

---

## Project name

```
Babel
```

## Elevator pitch

```
Indie devs can afford 2 or 3 translations. Babel reads Qloo fan maps of games like yours and turns them into a costed language plan that fits your budget.
```

---

## About the project

(Paste everything between the two lines into the "About the project" box.)

---

## Inspiration

If you make an indie game and ask which languages to translate it into, you get the same answer every time: Simplified Chinese, Japanese and Korean first, then Brazilian Portuguese, Russian, Spanish. It shows up in blog posts, Discord servers and publisher decks, and it is the same list whether you made a cozy farming sim or a WW2 grand strategy game.

That bothered us, because the decision is expensive. A small studio usually has a few thousand dollars for localization, and one language costs anywhere from about $500 to more than $20,000. That pays for two or three languages, and a wrong pick is money that never comes back.

Fans of a farming game and fans of a war game don't live in the same places. Qloo knows where the fans of a game are. So the question we started with was simple: **can taste data tell an indie developer where their players are likely to be, before the game even launches?**

## What it does

You give Babel your game (a Steam link, a name, or a short description if there is no store page yet), the word count and your budget. Babel gives you back a plan:

- **Translate the whole game** into these languages
- **Translate only the store page** for these (a cheap way to test a market)
- **Skip for now** for the rest

Each language comes with an estimated share of your likely non-English players, an estimated cost and a reason. On top of that you get:

- a **world map** of where fans of games like yours are, compared with the usual pattern
- a **budget slider** that re-fits the plan instantly
- a **"Why?"** for every recommendation, step by step
- a side-by-side with the copy-pasted list, showing where your game differs and why
- who the fans are (age and gender skew) and what they also like in each top market
- a printable report you can save as a PDF

![How Babel works](https://raw.githubusercontent.com/Maheswar-Sah00/babel/main/docs/diagrams/overview.png)

There's also an in-app assistant that can answer questions about your plan and drive the app for you, and Babel works as an **MCP tool**, so another AI agent can ask it for a language plan directly.

## How Babel works as an agent

Babel is an agent with one goal: the best language plan your budget can buy. You give it the goal; it works out the rest, and you watch it happen as a live trace on screen.

1. **It plans.** It lays out the steps for your game: find it, find look-alikes, read their Qloo fan maps, score the 14 languages, fit the budget, add market notes, explain, verify.
2. **It acts, with tools.** It calls Steam (your game and its tags), **Qloo** (finding each look-alike, its world fan map, its audience and what its fans love in each market), Claude (reading a description, writing the explanation), and its own planning engine.
3. **It reflects on what comes back, and recovers.** A look-alike that Qloo has no real data for is caught by its fingerprint and dropped; too few look-alikes and it widens the search; sparse Steam tags and it reads the store description instead; a failed request is reported, never papered over. You see each of these decisions in the trace.
4. **It verifies before it answers.** It re-checks the finished plan, and every number in Claude's explanation must appear in the evidence it cites, or that sentence is replaced.

It also works the other way round: other agents can use Babel as a tool. The **MCP tool** `babel_language_plan` runs the same agent and returns the same plan, and the in-app **assistant** answers questions about your plan and performs actions in the app (re-fit the budget, show a country, open a "Why?"), each one checked against Babel's own data.

## How we built it

**The core trick: look-alike games.** A game that hasn't launched has no fans, so Qloo has nothing on it. (We checked: 75 out of 75 new indie games we looked up returned Qloo's default "no data" map.) So Babel finds three well-known games that share your Steam tags, with rare tags weighted more, and reads their fan maps instead.

From there it's all deterministic code:

1. **Qloo world heatmaps** for each look-alike, summed per country
2. Countries turned into languages, weighted by population
3. A **lift** per language: how much more (or less) common these fans are where that language is spoken, compared with a yardstick of other games
4. That lift applied to the **typical language mix** of English-only indie games on Steam

$$\text{share}(L) \propto \text{typical mix}(L) \times \text{lift}(L)$$

5. An **exact budget optimizer** (a small knapsack that checks every combination) picks the full translations that cover the most estimated demand. Whatever's left buys store pages.

![The planning engine](https://raw.githubusercontent.com/Maheswar-Sah00/babel/main/docs/diagrams/pipeline.png)

**The agent** runs these steps as a live trace you can watch. It reflects on what comes back and recovers when something is off (for example, a look-alike that Qloo has no real data for gets detected by its fingerprint and swapped out). Then it re-checks the finished plan before showing it.

**Where the LLM fits, and where it doesn't.** An LLM reads a game description to suggest tags and similar games, and writes the plain-English explanation. That's it. It never produces a score, a country or a cost. Code verifies every game it names against Steam and Qloo, and every number in its explanation has to appear in the evidence it cites, or the sentence is dropped.

![LLM vs code](https://raw.githubusercontent.com/Maheswar-Sah00/babel/main/docs/diagrams/guardrails.png)

**Stack:** Python 3.12 and FastAPI on the backend, with Server-Sent Events for the live trace. The frontend is plain HTML, CSS and JavaScript, with no build step and no API keys in the browser, and D3 draws the map. Every outside call goes through one throttled, cached HTTP layer, so the four demo buttons run fully from cache. It's deployed on Railway.

## Did it actually work? We tested it.

We didn't want to ship a tool that just sounds smart, so before looking at any results we wrote down the method, the measure and the pass mark ([pre-registration](https://github.com/Maheswar-Sah00/babel/blob/main/backtest/PREREGISTRATION.md)). Then we ran it once on 257 real games, using two independent measures of where a game's non-English audience really is.

![The backtest](https://raw.githubusercontent.com/Maheswar-Sah00/babel/main/docs/diagrams/evidence.png)

- **186 notable games released since 2023**, measured by Wikipedia pageviews across 13 language editions: Qloo fan maps of look-alike games improved Babel's top 3 languages. The pick was better for **87 games** and worse for **33** (p < 0.001), **+2.7 points** of coverage.
- In context: Babel's top 3 captured **60%** of these games' non-English Wikipedia attention, against **22%** for the copy-pasted list. Most of that gap comes from using real language data at all, not from Qloo, and this measure under-counts Chinese, Japanese and Korean readers.
- **71 small English-only indie games**, measured by Steam reviews: the gain was small and **not significant** (+1.2 points, p = 0.50), although Qloo's signal still tracked which games lean toward which language (p = 0.001).
- A frontier LLM on its own was about as accurate. So we use the LLM to read and explain, and Qloo for evidence you can inspect on a map.

All of this is in the app's Track record screen, recomputed live from the frozen data files.

## Challenges we ran into

- **New games are invisible to Qloo.** This nearly killed the idea on day one. The look-alike approach came out of that, and we ran a kill check first: same-genre games turned out to correlate 0.50 by country against 0.08 across genres, so the signal was real.
- **Qloo's silent "default map".** When Qloo has no data on a game, it doesn't return an error. It returns the same generic map every time. Averaging those in would have quietly corrupted every plan, so we fingerprint them and drop them.
- **Our own data had a flaw.** Halfway through we found that 68 of the 186 Wikipedia test games had no Steam tags, so they had all been given the same three look-alikes. We left the pre-registered result untouched, reported the flaw openly, and fixed the planner so a game with no tags never gets arbitrary look-alikes.
- **Keeping the LLM honest.** Getting an LLM to explain a plan is easy. Making sure it never invents a number took a checker that matches every figure in its text against the evidence.

## Accomplishments that we're proud of

- A test we fixed in advance and then reported as it came out, including the part where Qloo added little.
- Every number on screen comes from code and can be traced back with "Why?".
- It works for a game that doesn't exist yet: describe it in a paragraph and you get a plan.
- Another agent can call it over MCP and get the same plan the web app shows.

## What we learned

- Taste data is strongest as an **adjustment on top of a solid baseline**, not as an oracle. Ranking by Qloo alone did poorly (about 26%); multiplying it into the typical mix is what worked.
- The honest version of a result is more useful than the impressive one. Writing down what we'd claim before seeing the numbers changed how we built the whole product.
- If a decision involves money, people want the reason more than the answer. The "Why?" button ended up being the centre of the app.

## What's next for Babel

- Planning for **regional variants** (Latin American vs European Spanish, Brazilian vs European Portuguese)
- Plugging in **real translator quotes** instead of example per-word rates
- Testing an **LLM + Qloo combination**, which we haven't evaluated yet
- Re-running the backtest as new games launch and Qloo's data grows

---

## Built with

Add these as tags, one at a time:

```
python
fastapi
qloo
javascript
html5
css3
d3.js
anthropic-api
mcp
server-sent-events
steam
steamspy
wikipedia
wikidata
openstreetmap
railway
docker
pytest
playwright
```

---

## "Try it out" links

```
https://babel-production-d47f.up.railway.app/
https://github.com/Maheswar-Sah00/babel
```

---

## Image gallery (3:2 works best, 5 MB max, up to 15)

Upload these, in this order. They are all in the repo:

1. `docs/screenshots/06-plan-map.png`: where the fans are (the hero image)
2. `docs/screenshots/09-plan-localization.png`: the plan and the budget slider
3. `docs/diagrams/overview.png`: how Babel works
4. `docs/screenshots/10-plan-why.png`: "Why?" for one language
5. `docs/screenshots/11-plan-vs-generic.png`: Babel vs the usual list
6. `docs/screenshots/05-working-live.png`: the agent's live trace
7. `docs/diagrams/evidence.png`: the backtest
8. `docs/screenshots/13-track-record.png`: Track record screen
9. `docs/screenshots/12-report.png`: the printable report
10. `docs/screenshots/18-assistant.png`: the assistant
11. `docs/diagrams/guardrails.png`: what the LLM does and what code checks
12. `docs/screenshots/01-start.png`: the Start screen

---

## Video demo link

Not required for this hackathon. If you record one, paste the YouTube or Vimeo link here.

---

## When did you begin your project?

```
October 8, 2026
```

## The public URL to your project

```
https://babel-production-d47f.up.railway.app/
```

## Link to your PUBLIC code repo

```
https://github.com/Maheswar-Sah00/babel
```

## If this was an existing project, in what ways did you significantly upgrade and improve it to work with Qloo?

```
This is not an existing project. We started it from scratch for this hackathon, beginning with a check on October 8 that Qloo has genre-specific world fan maps for video games. Qloo is the core of how Babel works: its fan maps of look-alike games are the only game-specific input to the language scores, and its demographics and "also loves" data make up the audience and market notes. Without Qloo, every game would get the same generic list.
```
