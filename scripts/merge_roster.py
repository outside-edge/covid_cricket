"""Merge per-period roster collections into data/infections.csv and close_contacts.csv.

Inputs are text files holding fenced CSV blocks named ``infections`` and
``close_contacts``. A player reported positive twice within 60 days is one
episode (the earlier date is kept and the sources are pooled); a later positive
is recorded as a reinfection of the same player.
"""

import argparse
import csv
import io
import re
from pathlib import Path

import pandas as pd

REINFECTION_GAP_DAYS = 60


def blocks(text, name):
    """Read a fenced CSV block; surplus fields from unquoted commas go to notes."""
    m = re.search(rf"```{name}\n(.*?)```", text, re.S)
    if not m:
        return pd.DataFrame()
    rows = list(csv.reader(io.StringIO(m.group(1))))
    header, body = rows[0], [r for r in rows[1:] if any(r)]
    fixed = []
    for r in body:
        if len(r) > len(header):
            r = r[: len(header) - 1] + [",".join(r[len(header) - 1 :])]
        fixed.append(r + [""] * (len(header) - len(r)))
    return pd.DataFrame(fixed, columns=header)


def normalise(name):
    return re.sub(r"\s+", " ", re.sub(r"\(.*?\)", "", name)).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, default=Path("data"))
    args = ap.parse_args()

    inf, cc = [], []
    for p in args.inputs:
        text = p.read_text()
        i, c = blocks(text, "infections"), blocks(text, "close_contacts")
        i["collection"], c["collection"] = p.stem, p.stem
        inf.append(i)
        cc.append(c)
    inf = pd.concat(inf, ignore_index=True)
    cc = pd.concat(cc, ignore_index=True)

    inf["player"] = inf["player"].map(normalise)
    inf["date"] = pd.to_datetime(inf["date"], errors="coerce")
    inf = inf.sort_values(["player", "date"])

    episodes = []
    for _, g in inf.groupby("player", sort=False):
        current = None
        for _, row in g.iterrows():
            gap = (row["date"] - current["date"]).days if current is not None else None
            if current is not None and gap is not None and gap <= REINFECTION_GAP_DAYS:
                current["sources"] |= {row["source_url"], row["second_source_url"]} - {
                    ""
                }
                current["notes"] = "; ".join(
                    x for x in [current["notes"], row["notes"]] if x
                )
                continue
            if current is not None:
                episodes.append(current)
            current = row.to_dict()
            current["sources"] = {row["source_url"], row["second_source_url"]} - {""}
        episodes.append(current)

    out = pd.DataFrame(episodes)
    out["episode"] = out.groupby("player").cumcount() + 1
    out["sources"] = out["sources"].map(lambda s: " ".join(sorted(s)))
    cols = [
        "player",
        "episode",
        "country_or_team",
        "level",
        "competition_or_series",
        "date",
        "date_type",
        "symptomatic_reported",
        "sources",
        "notes",
        "collection",
    ]
    out["date"] = out["date"].dt.date
    args.out.mkdir(exist_ok=True)
    out[cols].to_csv(
        args.out / "infections.csv", index=False, quoting=csv.QUOTE_MINIMAL
    )
    cc.to_csv(args.out / "close_contacts.csv", index=False)
    print(
        f"input rows={len(inf)} episodes={len(out)} players={out['player'].nunique()} "
        f"reinfections={int((out['episode'] > 1).sum())} close_contacts={len(cc)} "
        f"missing_date={int(out['date'].isna().sum())}"
    )


if __name__ == "__main__":
    main()
