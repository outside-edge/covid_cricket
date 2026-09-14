# Analysis plan: COVID-19 infection and cricket performance

**Status at commit (2026-09-14):** written before any infection roster beyond the 2021 seed list
(`data/cricketers_with_covid_positive_test.csv`, 43 rows) and before any performance data were
downloaded or examined. No outcome for any treated player has been seen. Deviations from this plan
will be logged in `DEVIATIONS.md` with dates and reasons; analyses not listed here are exploratory.

**Question.** Do cricketers who test positive for COVID-19 perform worse after they return?

**Decisions.** Treated window 2020-03 to 2022-12 (including Omicron); all Cricsheet competitions,
men and women; the infection roster is collected first, and the power check runs after collection but
before any treated-player effect is estimated.

**Closest prior study.** Fischer, Reade & Schmal (2022), *Labour Economics* 79:102281: professional
footballers in Germany and Italy, staggered difference-in-differences, performance about 6% lower after
return and about 5% lower eight months later; no effect for other respiratory infections.

## Estimand
For professional cricketers with a publicly reported positive COVID-19 test between 2020-03 and
2022-12, the average effect of infection on per-ball performance in matches played in the first
N innings (primary: days 0–90) after return, relative to the performance they would have had
uninfected — estimated against teammates who played the same matches and had no reported
infection. Unit: player × innings. Aggregation: equal weight per treated player (not per ball),
separately for batting and bowling. Secondary: event-time path to 365 days.

## Identification
Assumption: absent infection, treated players' performance *relative to teammates in the same
matches* would have evolved like that of non-reported teammates (parallel trends within team-period),
and infection timing is not driven by form. Plausible because infections arrived through squad
outbreaks and bubble testing, not through player choices tied to form.

Threats and how the design answers each:
1. **Conditions, opposition, schedule shocks** → match (innings) fixed effects: compare treated players
   to teammates in the same match.
2. **Layoff/rust, not infection** → placebo group: close contacts who isolated without testing positive,
   and returns from non-COVID absences of similar length (injury, rest). Effect should appear for
   infected, not for these.
3. **Selection into playing after return** (dropped players go unobserved) → report appearance/selection
   as its own outcome; performance conditional on playing gets Lee-style bounds.
4. **Contaminated controls** (esp. 2022 Omicron: unreported infections among "never reported") → biases
   toward zero. Pre-specified split 2020–21 (bubble testing) vs 2022; report attenuation bound using
   the share of controls plausibly infected.
5. **Reporting depends on prominence/bubble status** → the estimand is for *reported* infections; record
   reporting context (national squad, franchise league, domestic) and estimate within context.
6. **Staggered timing + heterogeneous effects** → no TWFE; use imputation estimator
   (Borusyak–Jaravel–Spiess / `did2s`) fit on untreated player-innings with player FE + match FE,
   and Sun–Abraham event study as a cross-check.

## Data build
1. **Infection roster** (`data/infections.csv`): player, cricinfo id, positive-test date, report date,
   source URLs (≥1, second source where possible), context (national/league/domestic, team, series),
   symptomatic mentioned, reinfection flag, first match after return. Sources: ESPNcricinfo COVID
   stories, board press releases, league statements; seed with the existing 43 rows after correcting
   dates. Also **close contacts** (`data/close_contacts.csv`) isolated without a positive test.
   Every row carries its URL; unverifiable rows are kept but flagged, not silently dropped.
2. **Outcomes**: Cricsheet JSON for 2017–2023, all competitions; parse to ball level; map players via
   Cricsheet registry → cricinfo ids. Keep format, competition, venue, innings phase, date.
3. **Expected-value adjustment**: per-ball expected runs and dismissal probability by format × phase
   (over) × competition-season, estimated on pre-2020 balls; outcomes are observed minus expected
   (reuse `outside-edge/war` replacement-level logic where it fits).
4. **Panel**: player × innings with event time (days and innings since return), team-period, age
   (from cricinfo), role (batter, pace bowler, spinner, keeper).
5. Show the user samples beside sources before analysis: 20 roster rows beside their articles; match
   rate of roster names to registry ids; innings counts per treated player pre/post.

## Pre-specified analysis
- **Primary outcomes**: batting runs above expected per 100 balls; bowling runs conceded below expected
  per 6 balls. **Secondary**: dismissal rate per ball (batting), wicket rate per ball (bowling),
  overs bowled per match (workload), appearance probability.
- **Heterogeneity (pre-specified)**: pace vs spin bowlers; age (above/below 30); format (Test/first-class
  vs limited overs); period (2020–21 vs 2022); symptomatic reported.
- **Expected sign**: negative, largest for pace bowlers and long formats; plausible magnitude a few
  percent (Fischer: ~6%).
- **Inference**: cluster by outbreak (squad-event), since infections co-occur within squads; report
  number of treated clusters; wild cluster bootstrap if clusters are few. Multiplicity: primary family =
  2 outcomes; Holm within family; heterogeneity labeled exploratory unless listed above.
- **Power/MDE (before estimating treated effects)**: assign placebo infections to random untreated
  players on random dates with the real roster's structure; the distribution of placebo estimates gives
  the MDE. Report it against the ~6% benchmark before looking at real estimates.
- **Falsification**: flat event-study leads; placebo groups (close contacts; non-COVID layoffs) show no
  post-return decline; placebo dates one year earlier; `HonestDiD` breakdown value for pre-trend violations.

## Interpretation plan
Report effects in runs per 100 balls and percent of the player's pre-infection baseline; state what the
interval rules out relative to ~6%. A null with wide intervals is "not detectable at this power", not
"no effect". Keep infection effect separate from layoff and selection.
