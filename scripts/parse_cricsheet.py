"""Parse the Cricsheet JSON archive into ball- and appearance-level Parquet tables.

Outputs (under raw/, gitignored; rebuilt from the checksummed archive):
- balls.parquet: one row per delivery, with batter/bowler registry ids and
  runs/wicket fields.
- appearances.parquet: one row per player per match from the playing XI, including
  players who neither batted nor bowled, so selection can be studied as an outcome.
"""

import argparse
import json
import zipfile
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

# Dismissals that count against the batter but are not credited to the bowler.
NON_BOWLER_WICKETS = {
    "run out",
    "retired hurt",
    "retired out",
    "retired not out",
    "obstructing the field",
    "timed out",
    "handled the ball",
}


def parse_match(match_id, data, balls, apps):
    info = data["info"]
    dates = info.get("dates") or []
    start = min(dates) if dates else None
    reg = info.get("registry", {}).get("people", {})
    common = dict(
        match_id=match_id,
        start_date=start,
        match_type=info.get("match_type"),
        gender=info.get("gender"),
        team_type=info.get("team_type"),
        event=(info.get("event") or {}).get("name"),
        season=str(info.get("season")),
        venue=info.get("venue"),
    )
    for team, players in (info.get("players") or {}).items():
        for p in players:
            apps.append(dict(common, team=team, player=p, player_id=reg.get(p)))
    for inn_no, inn in enumerate(data.get("innings") or [], start=1):
        if inn.get("super_over"):
            continue
        bat_team = inn.get("team")
        for over in inn.get("overs") or []:
            for ball_no, d in enumerate(over.get("deliveries") or [], start=1):
                extras = d.get("extras") or {}
                wickets = d.get("wickets") or []
                out_kinds = [
                    w.get("kind") for w in wickets if w.get("player_out") == d["batter"]
                ]
                balls.append(
                    dict(
                        common,
                        innings=inn_no,
                        batting_team=bat_team,
                        over=over["over"],
                        ball=ball_no,
                        batter=d["batter"],
                        batter_id=reg.get(d["batter"]),
                        bowler=d["bowler"],
                        bowler_id=reg.get(d["bowler"]),
                        runs_batter=d["runs"]["batter"],
                        runs_extras=d["runs"]["extras"],
                        runs_total=d["runs"]["total"],
                        wides=extras.get("wides", 0),
                        noballs=extras.get("noballs", 0),
                        byes=extras.get("byes", 0),
                        legbyes=extras.get("legbyes", 0),
                        batter_out=bool(out_kinds),
                        bowler_wicket=any(
                            w.get("kind") not in NON_BOWLER_WICKETS for w in wickets
                        ),
                    )
                )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", type=Path, default=Path("raw/all_json.zip"))
    ap.add_argument("--start", default="2017-01-01")
    ap.add_argument("--end", default="2023-12-31")
    ap.add_argument("--out", type=Path, default=Path("raw"))
    args = ap.parse_args()

    balls, apps, n_matches, skipped = [], [], 0, 0
    with zipfile.ZipFile(args.archive) as z:
        for name in z.namelist():
            if not name.endswith(".json"):
                continue
            data = json.loads(z.read(name))
            dates = data["info"].get("dates") or []
            if not dates or not (args.start <= min(dates) <= args.end):
                skipped += 1
                continue
            parse_match(name.removesuffix(".json"), data, balls, apps)
            n_matches += 1

    pq.write_table(pa.Table.from_pylist(balls), args.out / "balls.parquet")
    pq.write_table(pa.Table.from_pylist(apps), args.out / "appearances.parquet")
    print(
        f"matches={n_matches} skipped_out_of_window={skipped} "
        f"balls={len(balls)} appearances={len(apps)}"
    )


if __name__ == "__main__":
    main()
