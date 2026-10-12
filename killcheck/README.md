# Kill check

The day-1 test that decided whether Babel was worth building: does Qloo have usable, genre-specific world fan maps
for video games? **Result: pass.** Same-genre games correlate 0.50 by country, against 0.08 across genres. Three
recent hits return one identical "default" map, meaning no real data. See [report.md](report.md).

| File | What it is |
|---|---|
| `killcheck.py` | The test: 15 games in 5 genres, world heatmaps, country aggregation, verdict |
| [report.md](report.md) | Verdict, sanity checks and top countries per game |
| `games_x_countries.csv` | Country score per game (mean cell affinity) |

```bash
python killcheck/killcheck.py --inspect   # resolve the games and print one raw heatmap response
python killcheck/killcheck.py             # full run -> report.md, games_x_countries.csv
```
