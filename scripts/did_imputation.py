"""Imputation difference-in-differences for COVID-19 infection and cricket performance.

Subcommands:
  placebo  Assign fake infections to never-infected players and re-run the estimator
           many times; the spread of placebo estimates is the minimum detectable effect.
  estimate Estimate post-return effects for the infection roster, with pre-trend leads.

The estimator follows Borusyak, Jaravel and Spiess: fit y ~ player FE + match-team FE
on untreated innings (never-infected players, and infected players before infection),
predict treated players' post-return innings, and average residuals within player and
then across players.
"""

import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pyfixest as pf
from pyfixest.estimation.internals.demean_ import LsmrDemeaner

warnings.filterwarnings("ignore", message=".*singleton.*")

DISCIPLINES = {
    "batting": dict(file="bat_innings.parquet", y="runs_above_exp_per100", w="balls"),
    "bowling": dict(file="bowl_innings.parquet", y="runs_saved_per6", w="deliveries"),
}
SECONDARY = {"batting": "outs_above_exp_per100", "bowling": "wickets_above_exp_per6"}
EXCLUDE = {
    "Anrich Nortje",
    "Isuru Udana",
    "Mohammad Hafeez",
    "Shakib Al Hasan",
    "Jack Edwards",
}
MIN_PRE_INNINGS = 10
POST_DAYS = 90
LEADS = [(-180, -91), (-90, -1)]
CLUSTER_GAP_DAYS = 14
FALSE_POSITIVE_DAYS = 30
RECENT_DAYS = 365
# Minimum balls faced (batting) or deliveries (bowling) per treated player in the post
# window and in the recent pre window; set by placebo noise, not by treated outcomes.
MIN_POST_W = 0
MIN_PRE_W = 0


def load_panel(raw, discipline):
    spec = DISCIPLINES[discipline]
    d = pd.read_parquet(raw / spec["file"])
    d["start_date"] = pd.to_datetime(d["start_date"])
    if discipline == "bowling":
        apps = pd.read_parquet(
            raw / "appearances.parquet", columns=["match_id", "player_id", "team"]
        )
        d = d.merge(
            apps.drop_duplicates(["match_id", "player_id"]),
            on=["match_id", "player_id"],
        )
    d = d[d["player_id"].notna() & (d[spec["w"]] > 0)].copy()
    d["match_team"] = d["match_id"] + "|" + d["team"]
    return d


def roster(data):
    inf = pd.read_csv(data / "infections.csv", parse_dates=["date"])
    m = pd.read_csv(data / "player_matches.csv", dtype={"player_id": str})
    inf = inf.merge(m[["player", "episode", "player_id"]], on=["player", "episode"])
    inf = inf[inf["player_id"].notna() & ~inf["player"].isin(EXCLUDE)]
    # Drop episodes contradicted by a negative retest or ruled false positive within
    # FALSE_POSITIVE_DAYS for the same player.
    fp_path = data / "collection" / "cricinfo_archive_false_positives.csv"
    if fp_path.exists():
        fp = pd.read_csv(fp_path, parse_dates=["date"])
        # A later negative test usually means recovery; count explicit contradictions.
        said = (fp["quote"].fillna("") + " " + fp["notes"].fillna("")).str.lower()
        fp = fp[said.str.contains(r"false|re-?test|private test|second test|disput")]
        bad = inf.merge(fp[["player", "date"]], on="player", suffixes=("", "_fp"))
        bad = bad[(bad["date"] - bad["date_fp"]).abs().dt.days <= FALSE_POSITIVE_DAYS]
        inf = inf[
            ~inf.set_index(["player", "episode"]).index.isin(
                bad.set_index(["player", "episode"]).index
            )
        ]
    # Different spellings of one player can produce two episodes on the same dates.
    inf = inf.sort_values("date")
    keep, last = [], {}
    for idx, r in inf.iterrows():
        prev = last.get(r["player_id"])
        if prev is None or (r["date"] - prev).days > 60:
            keep.append(idx)
            last[r["player_id"]] = r["date"]
    inf = inf.loc[keep]
    inf["episode"] = inf.groupby("player_id").cumcount() + 1
    second = inf[inf["episode"] == 2].set_index("player_id")["date"]
    first = inf[inf["episode"] == 1].copy()
    first["next_infection"] = first["player_id"].map(second)
    first = first.sort_values("date")
    # Outbreak clusters: same reported team within CLUSTER_GAP_DAYS of the last case.
    cluster, last = {}, {}
    for idx, r in first.iterrows():
        team = str(r["country_or_team"]).split("/")[0].strip().lower()
        prev = last.get(team)
        if prev is None or (r["date"] - prev[0]).days > CLUSTER_GAP_DAYS:
            cluster[idx] = f"{team}|{r['date'].date()}"
        else:
            cluster[idx] = prev[1]
        last[team] = (r["date"], cluster[idx])
    first["cluster"] = pd.Series(cluster)
    return first[
        [
            "player",
            "player_id",
            "date",
            "next_infection",
            "cluster",
            "collection",
            "notes",
        ]
    ]


def assign(panel, treated):
    """Label innings: untreated, treated-post (with event day), lead bin, or dropped."""
    p = panel.merge(
        treated[["player_id", "date", "next_infection", "cluster"]],
        on="player_id",
        how="left",
    )
    p["ever"] = p["date"].notna()
    rel = (p["start_date"] - p["date"]).dt.days
    ret = p[p["ever"] & (rel >= 0)].groupby("player_id")["start_date"].min()
    p["return_date"] = p["player_id"].map(ret)
    p["event_day"] = (p["start_date"] - p["return_date"]).dt.days
    p["pre"] = p["ever"] & (rel < 0)
    p["post"] = p["ever"] & (rel >= 0) & (p["event_day"] <= 365)
    p.loc[
        p["next_infection"].notna() & (p["start_date"] >= p["next_infection"]), "post"
    ] = False
    drop = p["ever"] & (rel >= 0) & ~p["post"]
    p = p[~drop].copy()
    for lo, hi in LEADS:
        p[f"lead_{-lo}_{-hi}"] = (p["pre"] & (rel >= lo) & (rel <= hi)).astype(int)
    return p


def eligible(p):
    pre_n = p[p["pre"]].groupby("player_id").size()
    post_n = p[p["post"] & (p["event_day"] <= POST_DAYS)].groupby("player_id").size()
    ok = pre_n[pre_n >= MIN_PRE_INNINGS].index.intersection(post_n.index)
    return set(ok)


def fit_first_stage(p, y, w, leads=False):
    untreated = p[~p["post"]]
    rhs = " + ".join(c for c in p.columns if c.startswith("lead_")) if leads else "0"
    # Player and match-team effects form a sparse, weakly connected graph (associate and
    # domestic matches); alternating projections stall on it, LSMR converges.
    return pf.feols(
        f"{y} ~ {rhs} | player_id + match_team",
        data=untreated,
        weights=w,
        demeaner=LsmrDemeaner(fixef_maxiter=20000),
    )


def player_effects(p, fit, y, w, window, baseline="career"):
    """Per-player weighted mean residual in the post window.

    baseline="career": residual against player FE + match-team FE (FE from all
    untreated innings). baseline="recent": also subtract the player's weighted mean
    residual over the RECENT_DAYS before infection, so slow career trends cancel.
    """
    keep = p["post"] & p["event_day"].between(*window)
    if baseline == "recent":
        rel = (p["start_date"] - p["date"]).dt.days
        keep = keep | (p["pre"] & (rel >= -RECENT_DAYS))
    d = p[keep].copy()
    d["yhat"] = fit.predict(newdata=d)
    d = d[d["yhat"].notna()]
    d["resid"] = d[y] - d["yhat"]
    wavg = lambda x: np.average(x["resid"], weights=x[w])  # noqa: E731
    key = ["player_id", "cluster"]
    post = d[d["post"]].groupby(key)
    eff = post.apply(wavg, include_groups=False).rename("effect")
    eff = eff[post[w].sum() >= MIN_POST_W]
    if baseline == "recent":
        pre = d[d["pre"]].groupby(key)
        pre_eff = pre.apply(wavg, include_groups=False)
        pre_eff = pre_eff[pre[w].sum() >= MIN_PRE_W]
        eff = (eff - pre_eff).dropna().rename("effect")
    n = post.size().rename("post_innings")
    return eff.reset_index().merge(n.reset_index(), on=key)


def cluster_bootstrap(eff, reps=2000, seed=0):
    rng = np.random.default_rng(seed)
    by = {c: g["effect"].to_numpy() for c, g in eff.groupby("cluster")}
    keys = list(by)
    draws = []
    for _ in range(reps):
        pick = rng.choice(len(keys), size=len(keys), replace=True)
        draws.append(np.concatenate([by[keys[i]] for i in pick]).mean())
    return np.percentile(draws, [2.5, 97.5]).tolist(), float(np.std(draws))


def cmd_estimate(args):
    treated = roster(args.data)
    if args.drop_social_media:
        treated = treated[~treated["notes"].fillna("").str.contains("ocial.media")]
    out = {}
    for disc, spec in DISCIPLINES.items():
        panel = load_panel(args.raw, disc)
        p = assign(panel, treated)
        keep = eligible(p)
        p = p[~p["ever"] | p["player_id"].isin(keep)]
        treated_rows = p[p["player_id"].isin(keep)]
        res = dict(
            treated_players=len(keep), clusters=int(treated_rows["cluster"].nunique())
        )
        for label, y in [("primary", spec["y"]), ("secondary", SECONDARY[disc])]:
            fit = fit_first_stage(p, y, spec["w"])
            for baseline in ["career", "recent"]:
                for wlabel, window in [("0_90", (0, POST_DAYS)), ("91_365", (91, 365))]:
                    eff = player_effects(p, fit, y, spec["w"], window, baseline)
                    ci, se = cluster_bootstrap(eff)
                    res[f"{label}|{y}|{baseline}|{wlabel}"] = dict(
                        att=float(eff["effect"].mean()),
                        ci95=ci,
                        se=se,
                        players=len(eff),
                    )
                    if label == "primary" and wlabel == "0_90":
                        eff.merge(treated, on=["player_id", "cluster"]).to_csv(
                            args.out / f"player_effects_{disc}_{baseline}.csv",
                            index=False,
                        )
        lead_fit = fit_first_stage(p, spec["y"], spec["w"], leads=True)
        res["leads"] = lead_fit.tidy().reset_index().to_dict("records")
        pre = treated_rows[treated_rows["pre"]]
        res["treated_pre_raw_mean"] = float(
            np.average(pre[spec["y"]], weights=pre[spec["w"]])
        )
        out[disc] = res
    name = (
        "estimates_no_social_media.json" if args.drop_social_media else "estimates.json"
    )
    (args.out / name).write_text(json.dumps(out, indent=2, default=str))
    print(json.dumps(out, indent=2, default=str))


def cmd_placebo(args):
    treated = roster(args.data)
    rng = np.random.default_rng(args.seed)
    out = {}
    for disc, spec in DISCIPLINES.items():
        panel = load_panel(args.raw, disc)
        real = assign(panel, treated)
        n_real = len(eligible(real))
        clean = panel[~panel["player_id"].isin(treated["player_id"])]
        dates = treated["date"].to_numpy()
        players = clean.groupby("player_id")["start_date"].agg(["min", "max", "size"])
        players = players[players["size"] >= MIN_PRE_INNINGS + 5]
        ests = []
        for rep in range(args.reps):
            pool = players.sample(frac=1, random_state=int(rng.integers(1e9)))
            fake = []
            for pid, r in pool.iterrows():
                d = pd.Timestamp(rng.choice(dates))
                if r["min"] < d - pd.Timedelta(days=365) and r[
                    "max"
                ] > d + pd.Timedelta(days=POST_DAYS):
                    fake.append(
                        dict(
                            player=pid,
                            player_id=pid,
                            date=d,
                            next_infection=pd.NaT,
                            cluster=f"c{len(fake) // 3}",
                            collection="placebo",
                            notes="",
                        )
                    )
                if len(fake) >= n_real * 2:
                    break
            p = assign(clean, pd.DataFrame(fake))
            keep = list(eligible(p))[:n_real]
            p = p[~p["ever"] | p["player_id"].isin(keep)]
            fit = fit_first_stage(p, spec["y"], spec["w"])
            e1 = player_effects(p, fit, spec["y"], spec["w"], (0, POST_DAYS), "career")
            e2 = player_effects(p, fit, spec["y"], spec["w"], (0, POST_DAYS), "recent")
            ests.append((float(e1["effect"].mean()), float(e2["effect"].mean())))
            print(
                disc, rep, len(e1), len(e2), [round(x, 3) for x in ests[-1]], flush=True
            )
        ests = np.array(ests)
        out[disc] = dict(n_treated_real=n_real, reps=len(ests))
        for j, b in enumerate(["career", "recent"]):
            e = ests[:, j]
            out[disc][b] = dict(
                placebo_mean=float(e.mean()),
                placebo_sd=float(e.std()),
                mde_80power_5pct=float(2.8 * e.std()),
                placebo_q=np.percentile(e, [2.5, 97.5]).tolist(),
            )
    (args.out / "placebo_mde.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["placebo", "estimate"])
    ap.add_argument("--raw", type=Path, default=Path("raw"))
    ap.add_argument("--data", type=Path, default=Path("data"))
    ap.add_argument("--out", type=Path, default=Path("results"))
    ap.add_argument("--reps", type=int, default=200)
    ap.add_argument("--seed", type=int, default=20260914)
    ap.add_argument("--drop-social-media", action="store_true")
    ap.add_argument("--min-post-w", type=int, default=None)
    ap.add_argument("--min-pre-w", type=int, default=None)
    args = ap.parse_args()
    args.out.mkdir(exist_ok=True)
    global MIN_POST_W, MIN_PRE_W
    MIN_POST_W = args.min_post_w if args.min_post_w is not None else MIN_POST_W
    MIN_PRE_W = args.min_pre_w if args.min_pre_w is not None else MIN_PRE_W
    {"placebo": cmd_placebo, "estimate": cmd_estimate}[args.command](args)


if __name__ == "__main__":
    main()
