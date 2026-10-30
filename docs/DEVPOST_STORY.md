# Devpost text: Babel (story version)

A rewrite of [DEVPOST.md](DEVPOST.md) in a human, read-aloud voice. The facts are the same and every number follows
[DECISIONS.md](DECISIONS.md) sections 3 and 4. The other fields (built with, links, gallery, dates) stay as they are in
DEVPOST.md.

## How this is written (for you, not for Devpost)

Winning Devpost write-ups tend to share a few habits. This text follows them:

1. **The first two lines carry the whole idea.** Judges may score from the text and images alone, and many only skim.
2. **One problem, one number, one villain.** The villain here is the copy-pasted language list.
3. **The "aha" is told as a story:** what we believed, what we checked, what surprised us.
4. **The sponsor's tech does the key step, and the text proves it** with a "without Qloo" contrast the judge can check
   in the app.
5. **The limits are in our own words.** Saying where it's weak reads as confidence, and it keeps every claim true.
6. **Short paragraphs, one bold line per section** for skimmers.
7. **It ends with who it's for and what's next,** which matters for the investor bonus track.

Read it aloud once before you paste it in. If a sentence makes you stumble, shorten it.

If you built Babel alone, change "we" to "I" throughout. It sounds more personal, and it's true.

---

## Elevator pitch (200 characters max; pick one)

```
Indie devs can afford two or three translations. Babel reads Qloo fan maps of games like yours and turns them into a costed language plan that fits your budget.
```

```
Your game isn't out yet, but fans of games like it are. Babel finds them with Qloo and tells you which languages your translation budget should buy first.
```

```
Stop copying the same language list. Babel uses Qloo fan maps of look-alike games to tell indie devs what to translate first, at a price they can afford.
```

---

## About the project

(Paste everything between the two lines.)

---

## Inspiration

Ask anyone which languages to translate your indie game into, and you'll hear the same list. Simplified Chinese,
Japanese, Korean. Then Portuguese, Russian, Spanish.

It's in blog posts, Discord threads and publisher decks. And it's the same list whether you made a cozy farming game or
a war strategy game.

That bothered us, because this decision costs real money. Say you have $10,000 for localization. For a 30,000-word
game, one language costs roughly three to five thousand dollars. So you get two languages. Maybe three. Pick the wrong
ones, and that money doesn't come back.

So we looked at what players actually do. We scanned 4,000 Steam games to find 114 English-only indie games released
since 2023 with at least 500 reviews, and counted every review by language.

Even with no translation at all, about one review in five wasn't in English. And the biggest group wasn't Chinese or
Japanese. **It was Russian: 21.7% of the non-English reviews. Japanese, number two on the famous list, was 2.6%.**

(One honest caveat, and we'll come back to it: an English-only game loses the players who can't read English, and that
hits Chinese, Japanese and Korean hardest. But the gap was too big to ignore.)

That gave us the question behind Babel: **can taste data tell an indie developer where their players are likely to be,
before the game even launches?**

## What it does

You tell Babel about your game: a Steam link, a name, or just a paragraph if there's no store page yet. Add your word
count and your budget.

Babel comes back with a plan, in plain words:

- **Translate the whole game** into these languages.
- **Translate only the store page** for these. It's a cheap way to test a market.
- **Skip for now** for the rest.

Every language comes with an estimated share of your likely non-English players, an estimated cost, and a **Why?**
button that walks through every step behind it.

Try the WEBFISHING demo: 30,000 words, $10,000. Babel says translate the game into Russian and Spanish, put up store
pages in 11 more languages, and skip Thai for now. That's $7,996 of your $10,000. (Costs are estimates, not quotes.)

Around the plan you get:

- a **world map** of where fans of games like yours are, compared with usual
- a **budget slider** that re-fits the plan instantly
- **who those fans are** (age and gender skew), and what films and music are popular with them in each top market
- a side-by-side with the copy-pasted list, with the reason for every difference
- a one-page report you can print or save as a PDF
- an assistant that answers questions about your plan and can drive the app for you

And because this is an agent hackathon: Babel is also an **MCP tool**. Another AI agent can ask it for a language plan
and get the same answer the web app shows.

![How Babel works](https://raw.githubusercontent.com/Maheswar-Sah00/babel/main/docs/diagrams/overview.png)

## Why it needs Qloo

Here's the problem we hit on day one. **A game that isn't out yet has no fans, so Qloo has no data on it.** We looked up
75 new indie games that Qloo knows about. All 75 came back with Qloo's default "no data" map.

But fans of games *like* yours already exist. And Qloo knows where they are, country by country, across the whole
world.

So Babel picks three well-known games that share your Steam tags and reads their Qloo fan maps. For each language it
asks one question: are fans of games like this more or less common where this language is spoken than usual? The answer
becomes a **Qloo adjustment** on top of the typical language mix of English-only indie games.

That adjustment is the only part of the score that's about *your* game. Take it out, and look what happens to our four
demo games at $10,000:

| Demo game | Without Qloo | With Qloo |
|---|---|---|
| WEBFISHING (cozy multiplayer fishing) | Russian + Spanish | Russian + Spanish |
| Dawnsbury Days (tactical RPG) | Russian + Spanish | **Russian + German** |
| Never Second in Rome (historical turn-based RPG) | Russian + Spanish | **Russian + German** |
| A cozy farming idea (just a description) | Russian + Spanish | **Russian + Simplified Chinese** |

**Without Qloo, every game gets the same answer again.** It's a better-researched version of the list we set out to
replace, but it's still one list. With Qloo, the plan follows the fans.

Even when the top two stay the same, Qloo moves the rest. For WEBFISHING, it lifts Japanese from 2.7% to 4.7% and
Korean from 3.4% to 5.4%, and cuts Turkish from 3.4% to 1.8%. Open "Why?" on any language and you'll see exactly how
much of that came from Qloo.

Qloo gives us two more things nothing else in Babel can: **who the fans are** (Qloo's demographics for the look-alike
games) and **what's popular with them in each market** (Qloo insights for films and music, re-ranked by these fans).
Without Qloo there's no map, no audience and no "why".

## How we built it

**Look-alikes first.** Babel keeps a pool of 844 well-known Steam games released before 2023. It ranks them by shared
Steam tags, with rare tags counting more, and tries the top six until three have real Qloo data.

**Then the fake-data trap.** When Qloo has no data on a game, it doesn't return an error. It returns the same generic map
every time. We fingerprint that map and never use it. You can watch the agent do this in the WEBFISHING demo: Poly
Bridge comes back with the default map and gets skipped, and two other candidates aren't in Qloo at all.

From there, it's all deterministic code:

1. **Qloo world heatmaps** for each look-alike, in cells about 156 km wide, summed per country and weighted by
   popularity. (Plain averages put tiny islands on top, so a country needs at least 5 cells.)
2. **Countries become languages,** weighted by population.
3. **A lift per language:** how much more or less common these fans are there than for a yardstick of other games.
4. **The lift adjusts the typical mix:**

$$\text{share}(L) \propto \text{typical mix}(L) \times \text{lift}(L)$$

5. **An exact budget optimizer** checks every combination of full translations and keeps the one that covers the most
   estimated demand. Whatever's left buys store pages.

![The planning engine](https://raw.githubusercontent.com/Maheswar-Sah00/babel/main/docs/diagrams/pipeline.png)

**The agent** runs these steps as a live trace you can watch: plan, act, reflect, verify, explain. When something comes
back wrong, like a look-alike with no real data, it notices and recovers. Then it re-checks the finished plan before it
shows it to you.

**Where the LLM fits, and where it doesn't.** The LLM reads a description and suggests tags (only tags from our pool)
and similar games, and it writes the plain-English explanation. That's it. It never produces a score, a country or a
cost. Code checks every game it names against Steam and Qloo. Every number in its text has to appear in the evidence it
cites, or code writes that sentence instead.

![LLM vs code](https://raw.githubusercontent.com/Maheswar-Sah00/babel/main/docs/diagrams/guardrails.png)

**Stack:** Python 3.12 and FastAPI, with Server-Sent Events for the live trace. The frontend is plain HTML, CSS and
JavaScript with D3 for the map: no build step, and no API keys in the browser. Every outside call goes through one
throttled, cached HTTP layer, so the demo buttons run from cache. 473 automated tests, including real-browser tests.
Deployed on Railway.

## Did it work? We tested it before we trusted it.

Our first try, on 43 games, was a wash. Qloo changed the top pick on 8 games: 3 got better, 5 got worse. The signal was
there (Qloo tracked which games lean toward which language, p = 0.002), but the plan wasn't better.

So we stopped tuning. **We wrote the test down first:** the method, the measure and the pass mark, on 9 October, before
any fresh results existed ([pre-registration](https://github.com/Maheswar-Sah00/babel/blob/main/backtest/PREREGISTRATION.md)).
Then we ran it once, on 257 real games, with two independent measures of where a game's non-English audience really is.

![The backtest](https://raw.githubusercontent.com/Maheswar-Sah00/babel/main/docs/diagrams/evidence.png)

- **186 notable games released since 2023, measured by Wikipedia pageviews in 13 languages:** Qloo fan maps of
  look-alike games improved Babel's top 3 languages. The pick was **better for 87 games and worse for 33**
  (p < 0.001), +2.7 points of coverage.
- **71 small English-only indie games, measured by Steam reviews:** the gain was small and **not significant**
  (+1.2 points, p = 0.50). Qloo's signal still tracked which games lean toward which language (p = 0.001).
- **In context:** Babel's top 3 captured 60% of these games' non-English Wikipedia attention, against 22% for the
  copy-pasted list. Most of that gap comes from using real language data at all, not from Qloo, and this measure
  under-counts Chinese, Japanese and Korean readers.
- **Qloo on its own** scored about 26%. Taste data works best as an adjustment, not as an oracle.
- **A frontier LLM on its own was about as accurate.** So we let the LLM read and explain, and use Qloo for evidence you
  can inspect on a map.

All of this lives in the app's Track record screen, recomputed from the frozen data files every time.

## Challenges we ran into

- **The idea almost died on day one.** New games are invisible to Qloo. Before writing any product code we ran a kill
  check: 15 games across 5 genres. Fans of same-genre games lined up by country at 0.50, against 0.08 across genres.
  That was enough to build the look-alike idea on.
- **Qloo's silent default map.** Three of the 15 recent hits in that kill check (Lethal Company, Content Warning, Manor
  Lords) shared one identical map. Averaging those in would have quietly corrupted every plan, so we fingerprint and
  drop them.
- **A bug that returned nothing, quietly.** Qloo caps results at 50 per call and our batches were 100, so one signal
  came back empty without an error. We fixed it before the final run and logged it as a dated amendment.
- **Our own data had a flaw.** Halfway through, we found that 68 of the 186 Wikipedia test games had no Steam tags, so
  they'd all been given the same three look-alikes. We left the pre-registered result exactly as it was, reported the
  flaw, and fixed the planner: look-alikes now have to share at least one tag with your game.
- **Keeping the LLM honest.** Getting an LLM to explain a plan is easy. Making sure it never invents a number took a
  checker that matches every figure in its text against the evidence.

## Accomplishments that we're proud of

- A test we wrote down before seeing the results, and published as it came out, including the part where Qloo added
  little.
- Every number on screen comes from code, and "Why?" traces it back step by step.
- It works for a game that doesn't exist yet. Describe it in a paragraph and you get a plan.
- Another agent can call it over MCP and get the same plan the web app shows.

## What we learned

- **Taste data is strongest as an adjustment on top of a solid baseline,** not as an oracle. Ranking by Qloo alone did
  poorly; multiplying it into the typical mix is what worked.
- **The honest version of a result is more useful than the impressive one.** Writing down what we'd claim before seeing
  the numbers changed how we built the whole product.
- **When money is involved, people want the reason more than the answer.** The "Why?" button ended up at the centre of
  the app.

## Who it's for, and what's next

Babel is for solo developers and small studios on Steam, deciding where their first few thousand dollars of
localization should go. Two other groups could use it too: small publishers planning translations for a whole slate of
games each year, and translation agencies, who could hand a Babel report to a studio as the start of a quote.

Next:

- **Regional variants:** Latin American vs European Spanish, Brazilian vs European Portuguese
- **Real translator quotes** instead of example per-word rates
- **Testing an LLM + Qloo combination,** which we haven't evaluated yet
- **Re-running the backtest** as new games launch and Qloo's data grows

## Thank you

A big thank-you to Qloo, for the API and for running this hackathon. Babel only knows where the fans are because of
your data.

---
