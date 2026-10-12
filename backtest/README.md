# Backtest

Does Qloo improve which translation languages we recommend for a game? The plan and decision rule were fixed before
the test results were seen. **Read [PREREGISTRATION.md](PREREGISTRATION.md) first, then
[final_report.md](final_report.md).**

## Reports

| File | What it is |
|---|---|
| [PREREGISTRATION.md](PREREGISTRATION.md) | The fixed plan, competitors, measures and decision rule (with dated amendments) |
| [final_report.md](final_report.md) | The pre-registered result on both truths (Steam reviews, Wikipedia pageviews) |
| [step2_report.md](step2_report.md) | How the Steam test set and its ground truth were built |
| [step3_report.md](step3_report.md) | The earlier 43-game development comparison |
| [market_insights.md](market_insights.md) | Qloo audience profiles and market notes for three example games |

## Scripts, in run order

| Script | Writes |
|---|---|
| `build_dataset.py` | `data/test_games.csv`, `data/truth_reviews.csv`, `data/comps.csv`, `data/lang_share.png`, `step2_report.md` |
| `build_wiki_set.py` | `data/wiki_games.csv`, `data/wiki_comps.csv`, `data/truth_wiki.csv` |
| `compare.py` | `data/predictions.csv`, `step3_report.md` |
| `evaluate.py` | `data/final_predictions_steam.csv`, `data/final_predictions_wiki.csv`, `data/final_coverage.png`, `final_report.md` |
| `market_insights.py` | `market_insights.md` |

`data/dev_test_games_43.csv` is the frozen list of the 43 development games that `evaluate.py` keeps out of the test.

Run from the repository root, for example `python backtest/evaluate.py`. Every API response is cached in `cache/`, so
re-runs are offline. The datasets in `data/` are frozen: do not edit them.
