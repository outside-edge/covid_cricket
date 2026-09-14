"""Match roster names to Cricsheet registry identifiers.

A candidate is any Cricsheet player who appeared within MATCH_WINDOW_DAYS of the
infection date and whose recorded name agrees with the roster name: exact match,
or same surname with a compatible first initial. Unique candidates are accepted;
ties and misses are written out for manual resolution in data/manual_matches.csv,
which overrides the automatic match.
"""

import argparse
import re
import unicodedata
from pathlib import Path

import pandas as pd

MATCH_WINDOW_DAYS = 400


def fold(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", "", s.lower()).split()


def score(roster, cs_name):
    """3 = full name agrees; 2 = surname plus compatible given name/initial; 1 = surname
    only (roster gives one name); 0 = no match."""
    r = fold(roster)
    raw = cs_name.split()
    lead = []
    while raw and raw[0].isalpha() and raw[0].isupper() and len(raw) > 1:
        lead.append(raw.pop(0))
    rest = fold(" ".join(raw))
    if not r or not rest:
        return 0
    if r == fold(cs_name) or r == rest:
        return 3
    if r[-1] != rest[-1]:
        return 0
    if len(r) == 1:
        return 1
    if lead:
        # Initials follow no fixed order across countries (e.g. "CBRLS Kumara",
        # "HDRL Thirimanne"), so any initial may carry the roster's first name.
        return 2 if r[0][0] in "".join(lead).lower() else 0
    return 2 if len(rest) > 1 and rest[0] == r[0] else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", type=Path, default=Path("raw"))
    ap.add_argument("--data", type=Path, default=Path("data"))
    args = ap.parse_args()

    inf = pd.read_csv(args.data / "infections.csv", parse_dates=["date"])
    apps = pd.read_parquet(args.raw / "appearances.parquet")
    apps["start_date"] = pd.to_datetime(apps["start_date"])
    names = (
        apps.groupby(["player_id", "player"])
        .agg(
            first=("start_date", "min"),
            last=("start_date", "max"),
            n=("match_id", "size"),
            teams=("team", lambda t: "; ".join(t.value_counts().index[:4])),
        )
        .reset_index()
    )

    rows = []
    for _, r in inf.iterrows():
        lo = r["date"] - pd.Timedelta(days=MATCH_WINDOW_DAYS)
        hi = r["date"] + pd.Timedelta(days=MATCH_WINDOW_DAYS)
        pool = names[(names["last"] >= lo) & (names["first"] <= hi)].copy()
        pool["score"] = pool["player"].map(lambda n: score(r["player"], n))
        best = pool[pool["score"] > 0].sort_values(["score", "n"], ascending=False)
        top = best[best["score"] == best["score"].max()] if len(best) else best
        status = (
            "unmatched"
            if top.empty
            else ("unique" if top["player_id"].nunique() == 1 else "ambiguous")
        )
        rows.append(
            dict(
                player=r["player"],
                episode=r["episode"],
                date=r["date"].date(),
                team_reported=r["country_or_team"],
                status=status,
                player_id=top["player_id"].iloc[0] if status == "unique" else "",
                cricsheet_name=top["player"].iloc[0] if status == "unique" else "",
                candidates=" | ".join(
                    f"{x.player} [{x.player_id}] {x.teams} n={x.n}"
                    for x in top.head(5).itertuples()
                ),
            )
        )
    out = pd.DataFrame(rows)
    manual = args.data / "manual_matches.csv"
    if manual.exists():
        # Keyed on player, so a decision applies to every episode; NONE marks a player
        # with no Cricsheet record.
        m = pd.read_csv(manual, dtype=str).set_index("player")
        for player, mr in m.iterrows():
            sel = out["player"] == player
            pid = "" if mr["player_id"] == "NONE" else mr["player_id"]
            out.loc[sel, ["player_id", "status"]] = [pid, f"manual: {mr['reason']}"]
    out.to_csv(args.data / "player_matches.csv", index=False)
    print(out["status"].str.split(":").str[0].value_counts().to_string())
    print(
        out[out["status"] != "unique"][
            ["player", "date", "team_reported", "status", "candidates"]
        ].to_string()
    )


if __name__ == "__main__":
    main()
