# Does COVID-19 Hurt Cricketers' Performance?

> **Alpha (v0.2.0-alpha).** The roster now adds named cases read from 1,009 archived ESPNcricinfo stories (of 1,506 found, 1,428 retrievable), but still under-covers domestic cricket; see [Limitations](#limitations). v0.1.0-alpha results are in [`results/v0.1.0-alpha/`](results/v0.1.0-alpha/).

**Short answer: no detectable effect.** Cricketers with a publicly reported COVID-19 infection in 2020–2022 performed no worse after returning than matched never-infected players coming back from an absence of the same length. The intervals rule out large declines, not small ones.

## Results

Each infected player is compared with up to three never-infected players who returned from an absence of similar length at a similar time, in the same format, level, gender and role, with a similar career stage and pre-infection form. The effect is the infected player's change in performance (relative to teammates in the same matches) minus the matches' change.

| Outcome | Estimate | 95% CI | Pairs (clusters) |
|---|--:|---|--:|
| Batting, days 0–90 after return (runs above expected per 100 balls) | +3.1 | [−3.6, +9.6] | 125 (82) |
| Batting, days 91–365 | −0.4 | [−5.6, +5.1] | 120 (80) |
| Batting, in-season infections, days 0–90 | +5.1 | [−2.6, +15.5] | 69 (46) |
| Bowling, days 0–90 (runs saved per 6 balls) | −0.10 | [−0.51, +0.30] | 83 (59) |
| Bowling, days 91–365 | −0.02 | [−0.28, +0.22] | 79 (59) |
| Bowling, in-season infections, days 0–90 | −0.14 | [−0.81, +0.47] | 44 (32) |

Intervals come from a bootstrap over outbreak clusters (players reported by the same team within 14 days). Wilcoxon signed-rank p = 0.26 (batting), 0.89 (bowling). Source: [`results/matched_pairs_estimate.json`](results/matched_pairs_estimate.json); per-pair rows in `results/pairs_estimate_*.csv`.

**What the intervals rule out.** A batting decline of more than about 3.6 runs per 100 balls in the first 90 days (about 3% of a T20 scoring rate, about 5% of an ODI rate), and a bowling decline of more than about 0.5 runs per over (about 7% of a T20 economy rate). The closest prior study, Fischer, Reade & Schmal (2022, *Labour Economics*), found a ~6% drop among footballers.

## Checks that had to pass first

The placebo checks and the rule for reading them were fixed before the real estimate was run ([DEVIATIONS.md](DEVIATIONS.md), entry 8).

| Check | What it tests | Result |
|---|---|---|
| P1: fake infections among never-infected absence returners, matched the same way (100 replications) | the estimator is unbiased; its spread sets the minimum detectable effect | batting −0.26 (SE 0.29), MDE 8.0 per 100 balls; bowling −0.01 (SE 0.02), MDE 0.48 per 6 balls |
| P2: real infected players with dates moved back 365 days | infected players were not already on a different path | batting +2.2 [−1.8, +5.9]; bowling −0.22 [−0.54, +0.12] |
| P4: held-out pre-infection bin (91–14 days before), not used in matching | pre-trends | batting −2.1 [−10.2, +5.8]; bowling −0.38 [−0.72, 0.00] |

All gates pass. The bowling pre-trend (P4) is borderline: infected bowlers may have been slightly worse in the three months before infection; if so, a post-return decline would look smaller than it is.

**Why the design is not a simple before/after with teammates.** Placebo runs on never-infected players showed that simpler comparisons produce a spurious decline of about 2 runs per 100 balls: any player returning from an absence underperforms teammates who kept playing, and most infected players' absences were long and mostly not caused by illness (median ~100 days, with the last innings a month or more before the positive test). The sequence of designs tried and the placebo evidence that retired each one are in [DEVIATIONS.md](DEVIATIONS.md).

## Data

- **Infection roster** — [`data/infections.csv`](data/infections.csv): 253 episodes, 240 players, March 2020–December 2022, men and women, international, franchise and domestic; one row per episode, so reinfections appear as further episodes. Every row carries the source URL(s) of a report that names the player as testing positive. Two sources: targeted news searches by period, and every archived ESPNcricinfo story found through the Wayback Machine URL index whose address mentions Covid, positive tests, isolation or quarantine (1,506 stories; [`data/collection/cricinfo_story_index.tsv`](data/collection/cricinfo_story_index.tsv)). Rows from the archive were kept only if the quoted sentence appears verbatim in the story. Retrospective mentions, inferred positives and non-players sharing a name are kept out ([DEVIATIONS.md](DEVIATIONS.md), entry 9). Named close contacts are in [`data/close_contacts.csv`](data/close_contacts.csv). Episodes explicitly reported as false positives or contradicted by a retest, and cases with conflicting reports, are excluded from estimation.
- **Performance** — [Cricsheet](https://cricsheet.org/) ball-by-ball data, 2017–2023: 10,426 matches, 5.0 million deliveries. Runs and dismissals are compared with expected rates for the format, gender and innings phase, estimated on 2017–2019 only.
- **Matching roster names to Cricsheet** — [`data/player_matches.csv`](data/player_matches.csv): 233 of 253 episodes matched; 50 episodes were resolved by hand, each with a written reason in [`data/manual_matches.csv`](data/manual_matches.csv). The 20 unmatched are retired, under-19 or low-level domestic players with no Cricsheet record. 209 players with a matched first infection enter the analysis.
- `data/collection/seed_2021.csv` is the original 2021 seed list, kept for provenance. Several of its dates are wrong and three rows are not COVID cases (van Niekerk and Tryon had back injuries; Kusal Mendis was sent home for a bubble breach); use `data/infections.csv`.

## Reproduce

```bash
make data        # download Cricsheet (checksummed) and parse to ball and innings tables
make roster      # merge roster collections and match names to Cricsheet
make gates       # P1 and P2 placebo checks
make estimate    # matched-pair estimates
```

Requires [uv](https://docs.astral.sh/uv/). The Cricsheet archive is about 150 MB and parsed tables are rebuilt locally under `raw/` (not committed).

## Limitations

- **Roster coverage.** ESPNcricinfo reports international and franchise cases far more than domestic ones, and the search-based collection was capped, so domestic cricket (India, West Indies, England counties, Australia and New Zealand) and women's domestic leagues remain under-collected. Cricsheet's 17 recorded "COVID replacements" illustrate the gap: the international ones are on the roster, the domestic ones mostly are not.
- **Unreported infections among controls.** Many "never-infected" players, especially in 2022, will have had unreported infections. This pulls estimates toward zero.
- **What "infection" means here.** Reported, mostly mild or asymptomatic cases, with about ten innings of follow-up per player. The data say nothing about severe illness or long COVID.

## Files

- [`ANALYSIS_PLAN.md`](ANALYSIS_PLAN.md) — plan committed and tagged `plan-v1` before any outcome data were examined.
- [`DEVIATIONS.md`](DEVIATIONS.md) — every change from the plan, dated, with the placebo evidence behind it.
- `scripts/matched_pairs.py` — primary estimator and placebo checks. `scripts/stacked_did.py` and `scripts/did_imputation.py` are the earlier designs, kept for comparison.

## Citation

See [CITATION.cff](CITATION.cff).

## License

Code is MIT. Cricsheet data are used under Cricsheet's terms; news sources belong to their publishers.
