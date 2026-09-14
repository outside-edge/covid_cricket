# Deviations and decisions not in ANALYSIS_PLAN.md

Each entry is dated and says whether any treated-player outcome had been seen when it was made.

## 2026-09-14 — before any treated-player estimate

1. **Roster coverage is incomplete.** Web search for the roster was capped at 200 queries per
   session. Collections for March–December 2020, January–June 2021 and July–December 2022 are
   partial (India domestic, West Indies, women's teams, Associates and most of late 2022 were not
   searched); July 2021–June 2022 was still being collected. Estimates are for the players found,
   and the coverage gaps are reported with them.
2. **Sample rules fixed before estimation.**
   - Excluded as not infections: players whose source reports a negative confirmatory test, a
     ruled false positive, or conflicting reports of infection (Anrich Nortje, Isuru Udana,
     Mohammad Hafeez, Shakib Al Hasan, Jack Edwards).
   - Players identified only through social media (Pakistan in New Zealand, November 2020) are
     kept; a sensitivity check drops them.
   - One episode per player: the first reported positive. Innings after a second reported positive
     are dropped.
   - A treated player enters a discipline's estimate only with at least 10 innings in that
     discipline from 2017 up to the infection date and at least one innings within 90 days after
     returning. Without pre-infection innings the player fixed effect is not identified.
   - Players with no Cricsheet record (retired or low-level domestic) cannot enter.
3. **Fixed effects.** The plan says match fixed effects. Implemented as match × team (batting team
   for batting, bowling team for bowling), because innings conditions differ between the two sides
   of a match.
4. **Inference.** Imputation estimator (Borusyak, Jaravel and Spiess): the first stage is fit on
   untreated innings only, and treated players' post-return residuals are averaged within player,
   then across players. Confidence intervals come from a bootstrap over outbreak clusters (players
   reported by the same team within 14 days), holding the first stage fixed. The first stage uses
   hundreds of thousands of innings, so its sampling error is small next to the treated-sample
   error; the placebo distribution provides a design-based check on the interval.
