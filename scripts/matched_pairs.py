"""Matched-pair estimates of COVID-19 infection on cricket performance.

Design (DEVIATIONS.md entry 8). Each infected player is matched 1:3 to never-infected
players returning from an absence of similar length, with exact gender, level, return
format and role, and nearest career stage and pre-infection form trajectory. The pair
effect is the infected player's change in teammate-relative performance minus the mean
change of the matches.

Commands:
  estimate   the real roster
  p1         fake infections among never-infected absence returners (bias, MDE)
  p2         real infected players with dates moved back 365 days
Each run also reports P4: the held-out pre bin [-91, -14] difference.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from did_imputation import DISCIPLINES, load_panel, roster

PRE = (-365, -14)
BIN1, BIN2, HELD_OUT = (-365, -183), (-182, -92), (-91, -14)
POST, LATE_POST = (0, 90), (91, 365)
GAP_TOL = 0.25
START_WINDOW = 365
N_MATCH = 3
SHRINK_BALLS = 150.0
MIN_PRE_INNINGS = 5
IN_SEASON_DAYS = 30
ROLE_EDGES = (0.2, 0.8)


def day(ts):
    return ts.to_numpy().astype("datetime64[D]").astype(np.int64)


class Series:
    """Per-player prefix sums of weight and weight x teammate-relative residual."""

    def __init__(self, df, y, w):
        df = df.dropna(subset=["resid"]).sort_values(["player_id", "start_date"])
        self.data = {}
        for pid, g in df.groupby("player_id", sort=False):
            d = day(g["start_date"])
            ww = g[w].to_numpy(float)
            self.data[pid] = (
                d,
                np.concatenate([[0], np.cumsum(ww)]),
                np.concatenate([[0], np.cumsum(ww * g["resid"].to_numpy(float))]),
                g["fmt"].to_numpy(),
            )

    def window(self, pid, lo, hi):
        """Weight sum, weighted mean residual and innings count for days [lo, hi]."""
        if pid not in self.data:
            return 0.0, np.nan, 0
        d, cw, cwr, _ = self.data[pid]
        i, j = np.searchsorted(d, lo, "left"), np.searchsorted(d, hi, "right")
        sw = cw[j] - cw[i]
        return sw, ((cwr[j] - cwr[i]) / sw if sw > 0 else np.nan), j - i

    def first_fmt(self, pid, lo):
        if pid not in self.data:
            return None
        d, _, _, f = self.data[pid]
        i = np.searchsorted(d, lo, "left")
        return f[i] if i < len(d) else None

    def count_before(self, pid, t):
        return (
            int(np.searchsorted(self.data[pid][0], t, "left"))
            if pid in self.data
            else 0
        )


def teammate_relative(panel, y, w):
    """Outcome minus the weighted mean of the other players in the same match-team."""
    panel["_wy"] = panel[y] * panel[w]
    g = panel.groupby("match_team")
    loo_w = g[w].transform("sum") - panel[w]
    loo_wy = g["_wy"].transform("sum") - panel["_wy"]
    panel["resid"] = np.where(
        loo_w > 0, panel[y] - loo_wy / loo_w.where(loo_w > 0), np.nan
    )
    return panel.drop(columns="_wy")


def load(raw, disc, y):
    spec = DISCIPLINES[disc]
    p = load_panel(raw, disc)
    return teammate_relative(p, y, spec["w"])


def appearance_days(raw):
    a = pd.read_parquet(raw / "appearances.parquet")
    a["d"] = day(pd.to_datetime(a["start_date"]))
    a = a.dropna(subset=["player_id"])
    days = {pid: np.unique(g["d"].to_numpy()) for pid, g in a.groupby("player_id")}
    level = a.groupby(["player_id", "d"])["team_type"].first()
    gender = a.groupby("player_id")["gender"].agg(lambda s: s.mode()[0])
    return days, level, gender


def absence_around(days, pid, t):
    d = days.get(pid)
    if d is None:
        return None
    i = np.searchsorted(d, t, "left")
    if i == 0 or i == len(d):
        return None
    return int(d[i - 1]), int(d[i])


def features(pid, t, ret, ctx, primary, bat, bowl):
    """Match features and outcomes for a real or pseudo infection at day t."""
    sw_pre, pre_m, n_pre = primary.window(pid, t + PRE[0], t + PRE[1])
    if n_pre < MIN_PRE_INNINGS:
        return None
    sw_post, post_m, n_post = primary.window(pid, ret + POST[0], ret + POST[1])
    sw_late, late_m, _ = primary.window(pid, ret + LATE_POST[0], ret + LATE_POST[1])
    f = []
    for lo, hi in (BIN1, BIN2):
        sw, m, _ = primary.window(pid, t + lo, t + hi)
        f.append(0.0 if sw == 0 else m * sw / (sw + SHRINK_BALLS))
    _, held, n_held = primary.window(pid, t + HELD_OUT[0], t + HELD_OUT[1])
    bat_w = bat.window(pid, t + PRE[0], t + PRE[1])[0]
    bowl_w = bowl.window(pid, t + PRE[0], t + PRE[1])[0]
    share = bowl_w / (bat_w + bowl_w) if bat_w + bowl_w > 0 else np.nan
    role = (
        "bat" if share < ROLE_EDGES[0] else "bowl" if share > ROLE_EDGES[1] else "all"
    )
    return dict(
        gender=ctx["gender"].get(pid),
        level=ctx["level"].get((pid, ret)),
        fmt=primary.first_fmt(pid, ret),
        role=role,
        exp=np.log1p(primary.count_before(pid, t + PRE[0])),
        form1=f[0],
        form2=f[1],
        delta=post_m - pre_m if n_post > 0 else np.nan,
        delta_late=late_m - pre_m if sw_late > 0 else np.nan,
        held_out=held if n_held > 0 else np.nan,
        pre_level=pre_m,
        post_innings=n_post,
    )


def donor_gaps(days, exclude):
    rows = []
    for pid, d in days.items():
        if pid in exclude or len(d) < 2:
            continue
        rows.append(pd.DataFrame({"player_id": pid, "b": d[:-1], "r": d[1:]}))
    g = pd.concat(rows, ignore_index=True)
    g["gap"] = g["r"] - g["b"]
    return g


def match_event(ev, gaps, ctx, primary, bat, bowl, scale, rng, exclude_pid=None):
    """Return the event's pair effect and its matches' summaries, or None."""
    gap = ev["r"] - ev["b"]
    offset = ev["t"] - ev["b"]
    tol = max(3, GAP_TOL * gap)
    cand = gaps[
        gaps["gap"].between(max(gap - tol, offset), gap + tol)
        & ((gaps["b"] - ev["b"]).abs() <= START_WINDOW)
        & (gaps["player_id"] != exclude_pid)
    ]
    if cand.empty:
        return None
    rows = []
    for c in cand.sample(
        n=min(len(cand), 4000), random_state=int(rng.integers(1e9))
    ).itertuples():
        fc = features(c.player_id, c.b + offset, c.r, ctx, primary, bat, bowl)
        if fc is None or np.isnan(fc["delta"]):
            continue
        if (fc["gender"], fc["level"], fc["fmt"], fc["role"]) != (
            ev["gender"],
            ev["level"],
            ev["fmt"],
            ev["role"],
        ):
            continue
        dist = (
            ((np.log(max(c.gap, 1)) - np.log(max(gap, 1))) / scale["gap"]) ** 2
            + ((fc["exp"] - ev["exp"]) / scale["exp"]) ** 2
            + ((fc["form1"] - ev["form1"]) / scale["form"]) ** 2
            + ((fc["form2"] - ev["form2"]) / scale["form"]) ** 2
        )
        rows.append(dict(fc, dist=dist, donor=c.player_id))
    if not rows:
        return None
    m = pd.DataFrame(rows).sort_values("dist").drop_duplicates("donor").head(N_MATCH)
    return dict(
        effect=ev["delta"] - m["delta"].mean(),
        effect_late=ev["delta_late"] - m["delta_late"].mean(),
        held_out_diff=ev["held_out"] - m["held_out"].mean(),
        n_matches=len(m),
        mean_dist=float(m["dist"].mean()),
        infected_delta=ev["delta"],
        matches_delta=float(m["delta"].mean()),
        form2_gap=ev["form2"] - m["form2"].mean(),
    )


def context(raw, disc):
    spec = DISCIPLINES[disc]
    primary = Series(load(raw, disc, spec["y"]), spec["y"], spec["w"])
    bat = Series(load(raw, "batting", DISCIPLINES["batting"]["y"]), "resid", "balls")
    bowl = Series(
        load(raw, "bowling", DISCIPLINES["bowling"]["y"]), "resid", "deliveries"
    )
    days, level, gender = appearance_days(raw)
    ctx = dict(level=level.to_dict(), gender=gender.to_dict())
    return primary, bat, bowl, days, ctx


def events_from_roster(treated, days, ctx, primary, bat, bowl, shift_days=0):
    out = []
    for r in treated.itertuples():
        t = int(np.datetime64(r.date, "D").astype(np.int64)) - shift_days
        ab = absence_around(days, r.player_id, t)
        if ab is None:
            continue
        b, ret = ab
        f = features(r.player_id, t, ret, ctx, primary, bat, bowl)
        if f is None or np.isnan(f["delta"]):
            continue
        out.append(
            dict(
                f,
                player=r.player,
                player_id=r.player_id,
                t=t,
                b=b,
                r=ret,
                cluster=r.cluster,
                in_season=(t - b) <= IN_SEASON_DAYS,
            )
        )
    return out


def scales(gaps, ctx, primary, bat, bowl, rng, n=3000):
    s = gaps.sample(n=n, random_state=int(rng.integers(1e9)))
    feats = [
        features(c.player_id, c.b + max(1, c.gap // 2), c.r, ctx, primary, bat, bowl)
        for c in s.itertuples()
    ]
    f = pd.DataFrame([x for x in feats if x])
    return dict(
        gap=float(np.log(s["gap"].clip(lower=1)).std()),
        exp=float(f["exp"].std()),
        form=float(pd.concat([f["form1"], f["form2"]]).std()),
    )


def bootstrap(df, col, reps=2000, seed=0):
    rng = np.random.default_rng(seed)
    df = df.dropna(subset=[col])
    groups = [g[col].to_numpy() for _, g in df.groupby("cluster")]
    draws = [
        np.concatenate(
            [groups[i] for i in rng.integers(0, len(groups), len(groups))]
        ).mean()
        for _ in range(reps)
    ]
    return dict(
        mean=float(df[col].mean()),
        ci95=np.percentile(draws, [2.5, 97.5]).tolist(),
        se=float(np.std(draws)),
        n=len(df),
        clusters=len(groups),
    )


def run_events(events, gaps, ctx, primary, bat, bowl, scale, rng):
    rows = []
    for ev in events:
        res = match_event(
            ev, gaps, ctx, primary, bat, bowl, scale, rng, ev["player_id"]
        )
        if res:
            rows.append(
                dict(
                    res,
                    player=ev["player"],
                    player_id=ev["player_id"],
                    cluster=ev["cluster"],
                    in_season=ev["in_season"],
                    role=ev["role"],
                    fmt=ev["fmt"],
                    level=ev["level"],
                )
            )
    return pd.DataFrame(rows)


def summary(pairs, n_events):
    from scipy.stats import wilcoxon

    out = dict(
        events_with_data=n_events, matched=len(pairs), unmatched=n_events - len(pairs)
    )
    if pairs.empty:
        return out
    out["effect_0_90"] = bootstrap(pairs, "effect")
    out["effect_91_365"] = bootstrap(pairs, "effect_late")
    out["P4_held_out_pre_bin"] = bootstrap(pairs, "held_out_diff")
    out["wilcoxon_p"] = float(wilcoxon(pairs["effect"].dropna()).pvalue)
    ins = pairs[pairs["in_season"]]
    out["in_season_effect_0_90"] = bootstrap(ins, "effect") if len(ins) > 2 else None
    out["mean_match_distance"] = float(pairs["mean_dist"].mean())
    out["mean_form2_gap_after_matching"] = float(pairs["form2_gap"].mean())
    return out


def cmd(args):
    treated = roster(args.data)
    rng = np.random.default_rng(args.seed)
    out = {}
    for disc in DISCIPLINES:
        primary, bat, bowl, days, ctx = context(args.raw, disc)
        gaps = donor_gaps(days, set(treated["player_id"]))
        scale = scales(gaps, ctx, primary, bat, bowl, rng)
        if args.command in ("estimate", "p2"):
            shift = 365 if args.command == "p2" else 0
            evs = events_from_roster(treated, days, ctx, primary, bat, bowl, shift)
            pairs = run_events(evs, gaps, ctx, primary, bat, bowl, scale, rng)
            out[disc] = summary(pairs, len(evs))
            pairs.to_csv(args.out / f"pairs_{args.command}_{disc}.csv", index=False)
        else:
            n_real = len(events_from_roster(treated, days, ctx, primary, bat, bowl))
            real = events_from_roster(treated, days, ctx, primary, bat, bowl)
            offsets = [(e["t"] - e["b"], e["r"] - e["b"], e["b"]) for e in real]
            means, held = [], []
            for rep in range(args.reps):
                evs = []
                while len(evs) < n_real:
                    off, g, b0 = offsets[int(rng.integers(len(offsets)))]
                    tol = max(3, GAP_TOL * g)
                    pool = gaps[
                        gaps["gap"].between(max(g - tol, off), g + tol)
                        & ((gaps["b"] - b0).abs() <= START_WINDOW)
                    ]
                    if pool.empty:
                        continue
                    c = pool.iloc[int(rng.integers(len(pool)))]
                    f = features(
                        c["player_id"], c["b"] + off, c["r"], ctx, primary, bat, bowl
                    )
                    if f is None or np.isnan(f["delta"]):
                        continue
                    evs.append(
                        dict(
                            f,
                            player=c["player_id"],
                            player_id=c["player_id"],
                            t=c["b"] + off,
                            b=c["b"],
                            r=c["r"],
                            cluster=f"p{len(evs)}",
                            in_season=off <= IN_SEASON_DAYS,
                        )
                    )
                pairs = run_events(evs, gaps, ctx, primary, bat, bowl, scale, rng)
                means.append(float(pairs["effect"].mean()))
                held.append(float(pairs["held_out_diff"].mean()))
                print(disc, rep, len(pairs), round(means[-1], 3), flush=True)
            e = np.array(means)
            out[disc] = dict(
                real_events=n_real,
                reps=len(e),
                mean=float(e.mean()),
                se_of_mean=float(e.std() / np.sqrt(len(e))),
                sd=float(e.std()),
                mde_80power_5pct=float(2.8 * e.std()),
                held_out_mean=float(np.mean(held)),
            )
    (args.out / f"matched_pairs_{args.command}.json").write_text(
        json.dumps(out, indent=2)
    )
    print(json.dumps(out, indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["estimate", "p1", "p2"])
    ap.add_argument("--raw", type=Path, default=Path("raw"))
    ap.add_argument("--data", type=Path, default=Path("data"))
    ap.add_argument("--out", type=Path, default=Path("results"))
    ap.add_argument("--reps", type=int, default=100)
    ap.add_argument("--seed", type=int, default=20260914)
    args = ap.parse_args()
    args.out.mkdir(exist_ok=True)
    cmd(args)


if __name__ == "__main__":
    main()
