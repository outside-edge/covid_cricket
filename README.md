# Does COVID-19 Hurt Cricketers' Performance?

> **Alpha (v0.1.0-alpha).** The infection roster is incomplete and skews toward international and franchise players; see [Limitations](#limitations). Estimates will change as the roster grows.

**Short answer: no detectable effect.** Cricketers with a publicly reported COVID-19 infection in 2020–2022 performed no worse after returning than matched never-infected players coming back from an absence of the same length. The intervals rule out large declines, not small ones.

## Results

Each infected player is compared with up to three never-infected players who returned from an absence of similar length at a similar time, in the same format, level, gender and role, with a similar career stage and pre-infection form. The effect is the infected player's change in performance (relative to teammates in the same matches) minus the matches' change.

| Outcome | Estimate | 95% CI | Pairs (clusters) |
|---|--:|---|--:|
| Batting, days 0–90 after return (runs above expected per 100 balls) | +2.1 | [−5.4, +9.7] | 110 (69) |
| Batting, days 91–365 | −2.1 | [−7.8, +3.3] | 106 (68) |
| Batting, in-season infections, days 0–90 | +5.8 | [−2.6, +17.1] | 64 (41) |
| Bowling, days 0–90 (runs saved per 6 balls) | +0.00 | [−0.35, +0.37] | 75 (51) |
| Bowling, days 91–365 | +0.05 | [−0.23, +0.36] | 71 (51) |
| Bowling, in-season infections, days 0–90 | +0.02 | [−0.65, +0.63] | 41 (29) |

Intervals come from a bootstrap over outbreak clusters (players reported by the same team within 14 days). Wilcoxon signed-rank p = 0.38 (batting), 0.82 (bowling). Source: [`results/matched_pairs_estimate.json`](results/matched_pairs_estimate.json); per-pair rows in `results/pairs_estimate_*.csv`.

**What the intervals rule out.** A batting decline of more than about 5 runs per 100 balls in the first 90 days (about 4% of a T20 scoring rate, about 7% of an ODI rate), and a bowling decline of more than about 0.35 runs per over (about 5% of a T20 economy rate). The closest prior study, Fischer, Reade & Schmal (2022, *Labour Economics*), found a ~6% drop among footballers.

## Checks that had to pass first

The placebo checks and the rule for reading them were fixed before the real estimate was run ([DEVIATIONS.md](DEVIATIONS.md), entry 8).

| Check | What it tests | Result |
|---|---|---|
| P1: fake infections among never-infected absence returners, matched the same way (100 replications) | the estimator is unbiased; its spread sets the minimum detectable effect | batting +0.28 (SE 0.31), MDE 8.7 per 100 balls; bowling +0.04 (SE 0.02), MDE 0.52 per 6 balls |
| P2: real infected players with dates moved back 365 days | infected players were not already on a different path | batting +3.8 [−0.5, +8.2]; bowling −0.23 [−0.58, +0.09] |
| P4: held-out pre-infection bin (91–14 days before), not used in matching | pre-trends | batting +1.0 [−6.5, +8.8]; bowling −0.33 [−0.72, +0.11] |

P2 for batting is borderline; read batting estimates as carrying a few runs per 100 balls of structural noise.

**Why the design is not a simple before/after with teammates.** Placebo runs on never-infected players showed that simpler comparisons produce a spurious decline of about 2 runs per 100 balls: any player returning from an absence underperforms teammates who kept playing, and most infected players' absences were long and mostly not caused by illness (median ~100 days, with the last innings a month or more before the positive test). The sequence of designs tried and the placebo evidence that retired each one are in [DEVIATIONS.md](DEVIATIONS.md).

## Data

- **Infection roster** — [`data/infections.csv`](data/infections.csv): 202 episodes, 191 players, March 2020–December 2022, men and women, international, franchise and domestic. Every row carries the source URL(s) of a news report that names the player as testing positive. Collected by period in [`data/collection/`](data/collection/); named close contacts in [`data/close_contacts.csv`](data/close_contacts.csv). Five cases with a negative confirmatory test or conflicting reports are excluded from estimation.
- **Performance** — [Cricsheet](https://cricsheet.org/) ball-by-ball data, 2017–2023: 10,426 matches, 5.0 million deliveries. Runs and dismissals are compared with expected rates for the format, gender and innings phase, estimated on 2017–2019 only.
- **Matching roster names to Cricsheet** — [`data/player_matches.csv`](data/player_matches.csv): 191 of 202 episodes matched; 33 matches were made by hand, each with a written reason in [`data/manual_matches.csv`](data/manual_matches.csv). The 11 unmatched are retired or low-level domestic players with no Cricsheet record.
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

- **Roster coverage.** Web search for the roster was capped, so India domestic cricket, West Indies and CPL, women's domestic leagues, Associate nations and late 2022 are under-collected, and prominent players are over-represented. Cricsheet's 17 recorded "COVID replacements" illustrate the gap: the international ones are on the roster, the domestic ones mostly are not.
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
