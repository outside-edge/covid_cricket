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
5. **Primary baseline chosen from placebo runs.** 130 placebo replications (fake infection dates
   assigned to never-infected players, 55 players per replication) gave a mean batting estimate
   of −1.95 runs per 100 balls (SD 3.70) against each player's 2017–2023 fixed effect, and −0.05
   (SD 5.19) against each player's own residual in the 365 days before the fake date. The career
   baseline builds in a decline that is not caused by infection (plausibly career-stage trends),
   so the recent baseline is primary and the career baseline is reported only as a comparison.
6. **Primary estimator replaced by a stacked event-study DiD with a break (still before any
   treated-player estimate).** The placebo runs showed the imputation estimator against a
   2017–2023 player effect drifts negative with no treatment. The primary design is now one stack
   per infected player: pre window 365 to 14 days before the positive test (the 14-day break drops
   the pre-symptomatic period and any form dip that prompted testing), the layoff excluded, post
   window from the first innings back to 90 days later (91–365 secondary). Controls are players who
   shared a match with the infected player in the pre window, also played in the post window, and
   were not on the roster within 365 days. Within a stack: y ~ treated x post | player +
   match-team, weighted by balls or deliveries; stack coefficients are averaged with equal weight;
   bootstrap over outbreak clusters. Placebo stacks (never-infected players, roster infection
   dates, layoffs drawn from real layoffs) give the bias check and minimum detectable effect.
   Minimum samples: 5 pre-window innings for the infected player, 3 pre and 1 post for controls.
   The imputation estimator is kept only as a comparison.
7. **Absence-matched counterfactual (still before any treated-player estimate).** Placebo stacks
   on never-infected players drifted about −2 runs per 100 balls (45 replications × 103 stacks:
   mean −1.97, SD 2.63). Diagnostics on placebo stacks only: adjusting for pre-window form did not
   remove it (600 stacks: −2.5 unadjusted, −3.0 continuous form, −2.4 form terciles); with the
   imposed layoff the drift was −2.9 runs per 100 balls and +1.1 dismissals per 100 balls
   (t ≈ 2.2), and with no layoff it vanished. Players returning from any absence underperform
   teammates who kept playing. Infected players' absences are long and mostly not caused by
   illness (median last innings 35–42 days before the positive test; median total absence 98 days
   batting, 127 bowling), so the teammate comparison alone mixes infection with ordinary
   comeback effects. Primary estimate is now the infected player's stack coefficient minus the
   mean coefficient of up to 5 never-infected players who returned from an absence within ±25%
   of the same length, starting within 365 days, with the pseudo-infection placed at the same
   offset inside the gap. Pre-specified subgroup: in-season infections (last innings ≤ 30 days
   before the positive test). The teammate-only estimate is reported as a comparison.
8. **Agreed primary design: matched pairs with trajectory matching (2026-09-14, before any
   treated-player estimate).** Replaces entries 6–7 as primary; they remain comparisons.
   - Performance per innings: runs above expected per ball (batting) or runs saved per ball
     (bowling), minus the ball-weighted mean of the player's teammates in the same match-team.
   - Change: Δ = post mean − pre mean, pre = [infection − 365, infection − 14) days, post =
     [first innings back, +90] days, ball-weighted.
   - Matching, 1:3 with replacement, never-infected donors only. Exact: gender, level
     (international vs club), format of the first innings back, role (batter / bowler /
     all-rounder from the share of balls faced vs bowled in the pre window). Nearest
     (standardised distance): absence length (log, within ±25%), absence start within ±365
     days, career stage (log innings before the pre window), and shrunk teammate-relative form in
     two trajectory bins, [−365, −183] and [−182, −92] days before the pseudo or real infection.
     The pseudo infection for a donor sits at the same offset inside its absence.
   - Effect per infected player: Δ(infected) − mean Δ(matches); average across infected players;
     bootstrap over outbreak clusters; Wilcoxon signed-rank as a check. Infected players with no
     eligible match are dropped and counted.
   - Secondary: post window [91, 365]; in-season infections (last innings ≤ 30 days before test).
   - Gates, all must hold before the main estimate is interpreted: P1 fake infections among
     never-infected absence returners matched identically (mean ≈ 0; spread gives the minimum
     detectable effect); P2 real infected players with dates moved back 365 days (≈ 0); P4 the
     held-out pre bin [−91, −14] shows no difference between infected players and matches.
     If P1 or P2 fails the main estimate is reported as uninterpretable.
