"""Build player-innings batting and bowling tables with expected-value adjustment.

Expected runs and dismissal/wicket rates come from 2017-2019 balls only, by format
group x gender x innings phase, so the adjustment is fixed before any infection.
Match fixed effects in the estimator absorb conditions and opposition; this
adjustment removes differences in when in an innings a player bats or bowls.

Outputs (raw/, gitignored): bat_innings.parquet, bowl_innings.parquet.
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

FORMAT_GROUP = {
    "T20": "T20",
    "IT20": "T20",
    "ODI": "OD",
    "ODM": "OD",
    "Test": "MD",
    "MDM": "MD",
}
# Phase boundaries (0-indexed over numbers) where scoring conditions change:
# powerplay / middle / death for limited overs; new ball / old ball / second new ball
# for multi-day cricket.
PHASE_EDGES = {"T20": [6, 15], "OD": [10, 40], "MD": [20, 80]}
EXPECTED_BASE_END = "2019-12-31"


def phase(fmt, over):
    lo, hi = PHASE_EDGES[fmt]
    return np.where(over < lo, 0, np.where(over < hi, 1, 2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", type=Path, default=Path("raw"))
    args = ap.parse_args()

    b = pd.read_parquet(args.raw / "balls.parquet")
    b["fmt"] = b["match_type"].map(FORMAT_GROUP)
    b = b[b["fmt"].notna()].copy()
    b["phase"] = 0
    for fmt in PHASE_EDGES:
        m = b["fmt"] == fmt
        b.loc[m, "phase"] = phase(fmt, b.loc[m, "over"].to_numpy())
    b["cell"] = b["fmt"] + "|" + b["gender"] + "|" + b["phase"].astype(str)

    b["faced"] = (b["wides"] == 0).astype(int)
    b["legal"] = ((b["wides"] == 0) & (b["noballs"] == 0)).astype(int)
    b["conceded"] = b["runs_total"] - b["byes"] - b["legbyes"]

    base = b[b["start_date"] <= EXPECTED_BASE_END]
    bat_rates = base[base["faced"] == 1].groupby("cell")[["runs_batter", "batter_out"]]
    bat_rates = bat_rates.mean().rename(
        columns={"runs_batter": "exp_runs", "batter_out": "exp_out"}
    )
    bowl_rates = base.groupby("cell").agg(
        exp_conceded=("conceded", "mean"), exp_wicket=("bowler_wicket", "mean")
    )
    b = b.join(bat_rates, on="cell").join(bowl_rates, on="cell")

    keys = ["match_id", "start_date", "fmt", "gender", "match_type", "event"]
    faced = b[b["faced"] == 1]
    bat = (
        faced.groupby(keys + ["batting_team", "batter_id"])
        .agg(
            balls=("faced", "sum"),
            runs=("runs_batter", "sum"),
            exp_runs=("exp_runs", "sum"),
            outs=("batter_out", "sum"),
            exp_outs=("exp_out", "sum"),
        )
        .reset_index()
        .rename(columns={"batter_id": "player_id", "batting_team": "team"})
    )
    bat["runs_above_exp_per100"] = 100 * (bat["runs"] - bat["exp_runs"]) / bat["balls"]
    bat["outs_above_exp_per100"] = 100 * (bat["outs"] - bat["exp_outs"]) / bat["balls"]

    bowl = (
        b.groupby(keys + ["bowler_id"])
        .agg(
            deliveries=("faced", "size"),
            legal_balls=("legal", "sum"),
            conceded=("conceded", "sum"),
            exp_conceded=("exp_conceded", "sum"),
            wickets=("bowler_wicket", "sum"),
            exp_wickets=("exp_wicket", "sum"),
        )
        .reset_index()
        .rename(columns={"bowler_id": "player_id"})
    )
    bowl["runs_saved_per6"] = (
        6 * (bowl["exp_conceded"] - bowl["conceded"]) / bowl["deliveries"]
    )
    bowl["wickets_above_exp_per6"] = (
        6 * (bowl["wickets"] - bowl["exp_wickets"]) / bowl["deliveries"]
    )

    bat.to_parquet(args.raw / "bat_innings.parquet")
    bowl.to_parquet(args.raw / "bowl_innings.parquet")
    print(bat_rates.round(3).to_string())
    print(bowl_rates.round(3).to_string())
    print(f"batting rows={len(bat)} bowling rows={len(bowl)}")


if __name__ == "__main__":
    main()
