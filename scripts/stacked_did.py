"""Stacked event-study difference-in-differences with a break around infection.

One stack per infected player:
  pre window   [infection - PRE_DAYS, infection - BREAK_DAYS)
  post window  [return, return + POST_DAYS]; return = first innings on/after infection
  controls     players who shared a match (either side) with the infected player in
               the pre window, played in the post window, and were not on the
               infection roster within ROSTER_EXCLUSION_DAYS of the infection.
Within each stack: y ~ treated x post | player + match-team, weighted by balls
(batting) or deliveries (bowling). The stack coefficient compares the infected
player's change with the change of players in the same matches. Stack estimates are
averaged with equal weight; intervals come from a bootstrap over outbreak clusters.

Subcommands: estimate (real roster), placebo (fake infections on never-infected
players), event (binned event study for the real roster).
"""

import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pyfixest as pf
from did_imputation import DISCIPLINES, SECONDARY, load_panel, roster

warnings.filterwarnings("ignore")

PRE_DAYS = 365
BREAK_DAYS = 14
POST_DAYS = 90
LATE_POST = (91, 365)
ROSTER_EXCLUSION_DAYS = 365
MIN_TREATED_PRE = 5
MIN_CONTROL_PRE = 3
EVENT_BINS = [(-365, -274), (-273, -183), (-182, -92), (-91, -14)]
POST_BINS = [(0, 90), (91, 180), (181, 365)]


def build_stack(panel, pid, infection, roster_dates, post=(0, POST_DAYS), layoff=None):
    """Innings for one infected player and their controls, with treated/post flags."""
    lo = infection - pd.Timedelta(days=PRE_DAYS)
    brk = infection - pd.Timedelta(days=BREAK_DAYS)
    own = panel[panel["player_id"] == pid]
    after = own[own["start_date"] >= infection + pd.Timedelta(days=layoff or 0)]
    if after.empty:
        return None
    ret = after["start_date"].min()
    p_lo = ret + pd.Timedelta(days=post[0])
    p_hi = ret + pd.Timedelta(days=post[1])
    pre_mask = (panel["start_date"] >= lo) & (panel["start_date"] < brk)
    post_mask = (panel["start_date"] >= p_lo) & (panel["start_date"] <= p_hi)
    tr_pre = own[(own["start_date"] >= lo) & (own["start_date"] < brk)]
    if len(tr_pre) < MIN_TREATED_PRE:
        return None
    shared = panel.loc[
        pre_mask & panel["match_id"].isin(tr_pre["match_id"]), "player_id"
    ]
    near = roster_dates[
        (roster_dates["date"] - infection).abs().dt.days <= ROSTER_EXCLUSION_DAYS
    ]["player_id"]
    controls = set(shared) - set(near) - {pid}
    d = panel[(pre_mask | post_mask) & panel["player_id"].isin(controls | {pid})].copy()
    d["post"] = post_mask[d.index].astype(int)
    d["treated"] = (d["player_id"] == pid).astype(int)
    n_pre = d[d["post"] == 0].groupby("player_id").size()
    n_post = d[d["post"] == 1].groupby("player_id").size()
    keep = n_pre[n_pre >= MIN_CONTROL_PRE].index.intersection(n_post.index)
    d = d[d["player_id"].isin(keep) | (d["treated"] == 1)]
    if d[(d["treated"] == 1) & (d["post"] == 1)].empty:
        return None
    d["tp"] = d["treated"] * d["post"]
    return d


def stack_estimate(d, y, w):
    tp_rows = d[d["tp"] == 1]
    ctrl_mt = set(d.loc[d["treated"] == 0, "match_team"])
    identified = int(tp_rows["match_team"].isin(ctrl_mt).sum())
    if identified == 0:
        return None
    try:
        fit = pf.feols(f"{y} ~ tp | player_id + match_team", data=d, weights=w)
        coef = float(fit.coef()["tp"])
    except Exception:
        return None
    return dict(
        coef=coef,
        treated_post_innings=len(tp_rows),
        identified_post_innings=identified,
        controls=int(d.loc[d["treated"] == 0, "player_id"].nunique()),
        treated_pre_w=float(d.loc[(d["treated"] == 1) & (d["post"] == 0), w].sum()),
        treated_post_w=float(tp_rows[w].sum()),
    )


def cluster_bootstrap(df, col="coef", reps=2000, seed=0):
    rng = np.random.default_rng(seed)
    groups = [g[col].to_numpy() for _, g in df.groupby("cluster")]
    draws = [
        np.concatenate(
            [groups[i] for i in rng.integers(0, len(groups), len(groups))]
        ).mean()
        for _ in range(reps)
    ]
    return np.percentile(draws, [2.5, 97.5]).tolist(), float(np.std(draws))


def summarise(stacks, reps=2000):
    if stacks.empty:
        return dict(stacks=0)
    ci, se = cluster_bootstrap(stacks, reps=reps)
    return dict(
        att=float(stacks["coef"].mean()),
        ci95=ci,
        se=se,
        stacks=len(stacks),
        clusters=int(stacks["cluster"].nunique()),
        median_controls=float(stacks["controls"].median()),
        median_treated_post_innings=float(stacks["treated_post_innings"].median()),
    )


def run_roster(panel, treated, y, w, post):
    rows = []
    for r in treated.itertuples():
        d = build_stack(panel, r.player_id, r.date, treated, post=post)
        if d is None:
            continue
        est = stack_estimate(d, y, w)
        if est:
            rows.append(
                dict(
                    est,
                    player=r.player,
                    player_id=r.player_id,
                    date=r.date.date(),
                    cluster=r.cluster,
                )
            )
    return pd.DataFrame(rows)


def cmd_estimate(args):
    treated = roster(args.data)
    out = {}
    for disc, spec in DISCIPLINES.items():
        panel = load_panel(args.raw, disc)
        res = {}
        for label, y in [("primary", spec["y"]), ("secondary", SECONDARY[disc])]:
            for wl, post in [("0_90", (0, POST_DAYS)), ("91_365", LATE_POST)]:
                st = run_roster(panel, treated, y, spec["w"], post)
                res[f"{label}|{y}|{wl}"] = summarise(st)
                if label == "primary" and wl == "0_90":
                    st.to_csv(args.out / f"stacks_{disc}.csv", index=False)
        pre = panel.merge(treated[["player_id", "date"]], on="player_id")
        rel = (pre["start_date"] - pre["date"]).dt.days
        base = pre[(rel >= -PRE_DAYS) & (rel < -BREAK_DAYS)]
        res["treated_pre_mean"] = float(
            np.average(base[spec["y"]], weights=base[spec["w"]])
        )
        out[disc] = res
    (args.out / "stacked_estimates.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


def cmd_placebo(args):
    treated = roster(args.data)
    rng = np.random.default_rng(args.seed)
    out = {}
    for disc, spec in DISCIPLINES.items():
        panel = load_panel(args.raw, disc)
        real = run_roster(panel, treated, spec["y"], spec["w"], (0, POST_DAYS))
        n_real = len(real)
        # Layoffs of real infections: days from positive test to first innings back.
        lay = []
        for r in treated.itertuples():
            nxt = panel[
                (panel["player_id"] == r.player_id) & (panel["start_date"] >= r.date)
            ]
            if len(nxt):
                lay.append((nxt["start_date"].min() - r.date).days)
        lay = np.array(lay)
        clean = panel[~panel["player_id"].isin(treated["player_id"])]
        span = clean.groupby("player_id")["start_date"].agg(["min", "max", "size"])
        span = span[span["size"] >= 20]
        dates = treated["date"].to_numpy()
        ests = []
        for rep in range(args.reps):
            rows = []
            order = span.sample(frac=1, random_state=int(rng.integers(1e9)))
            for pid, s in order.iterrows():
                d0 = pd.Timestamp(rng.choice(dates))
                if not (
                    s["min"] < d0 - pd.Timedelta(days=PRE_DAYS / 2) and s["max"] > d0
                ):
                    continue
                d = build_stack(clean, pid, d0, treated, layoff=int(rng.choice(lay)))
                if d is None:
                    continue
                est = stack_estimate(d, spec["y"], spec["w"])
                if est:
                    rows.append(dict(est, cluster=f"r{rep}_{len(rows)}"))
                if len(rows) >= n_real:
                    break
            st = pd.DataFrame(rows)
            ests.append(float(st["coef"].mean()))
            print(disc, rep, len(st), round(ests[-1], 3), flush=True)
        e = np.array(ests)
        out[disc] = dict(
            real_stacks=n_real,
            reps=len(e),
            placebo_mean=float(e.mean()),
            placebo_sd=float(e.std()),
            mde_80power_5pct=float(2.8 * e.std()),
            placebo_q=np.percentile(e, [2.5, 97.5]).tolist(),
        )
    (args.out / "stacked_placebo.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


def cmd_event(args):
    treated = roster(args.data)
    out = {}
    for disc, spec in DISCIPLINES.items():
        panel = load_panel(args.raw, disc)
        coefs = []
        for r in treated.itertuples():
            d = build_stack(
                panel, r.player_id, r.date, treated, post=(0, POST_BINS[-1][1])
            )
            if d is None:
                continue
            ret = d.loc[(d["treated"] == 1) & (d["post"] == 1), "start_date"].min()
            rel_pre = (d["start_date"] - r.date).dt.days
            rel_post = (d["start_date"] - ret).dt.days
            d["bin"] = "none"
            for lo, hi in EVENT_BINS:
                d.loc[(d["post"] == 0) & rel_pre.between(lo, hi), "bin"] = (
                    f"pre[{lo},{hi}]"
                )
            for lo, hi in POST_BINS:
                d.loc[(d["post"] == 1) & rel_post.between(lo, hi), "bin"] = (
                    f"post[{lo},{hi}]"
                )
            ref = f"pre[{EVENT_BINS[-1][0]},{EVENT_BINS[-1][1]}]"
            for b in d["bin"].unique():
                if b in (ref, "none"):
                    continue
                d[f"t_{b}"] = ((d["bin"] == b) & (d["treated"] == 1)).astype(int)
            tcols = [c for c in d.columns if c.startswith("t_")]
            if not tcols:
                continue
            sub = d.rename(columns={c: f"b{i}" for i, c in enumerate(tcols)})
            try:
                fit = pf.feols(
                    f"{spec['y']} ~ {' + '.join(f'b{i}' for i in range(len(tcols)))}"
                    " | player_id + match_team",
                    data=sub,
                    weights=spec["w"],
                )
                cf = fit.coef()
            except Exception:
                continue
            for i, c in enumerate(tcols):
                if f"b{i}" in cf.index:
                    coefs.append(
                        dict(bin=c[2:], coef=float(cf[f"b{i}"]), cluster=r.cluster)
                    )
        cdf = pd.DataFrame(coefs)
        res = {}
        for b, g in cdf.groupby("bin"):
            ci, se = cluster_bootstrap(g, reps=1000)
            res[b] = dict(mean=float(g["coef"].mean()), ci95=ci, se=se, stacks=len(g))
        out[disc] = res
    (args.out / "stacked_event_study.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["estimate", "placebo", "event"])
    ap.add_argument("--raw", type=Path, default=Path("raw"))
    ap.add_argument("--data", type=Path, default=Path("data"))
    ap.add_argument("--out", type=Path, default=Path("results"))
    ap.add_argument("--reps", type=int, default=100)
    ap.add_argument("--seed", type=int, default=20260914)
    args = ap.parse_args()
    args.out.mkdir(exist_ok=True)
    {"estimate": cmd_estimate, "placebo": cmd_placebo, "event": cmd_event}[
        args.command
    ](args)


if __name__ == "__main__":
    main()
