"""Turn rows read from archived ESPNcricinfo stories into a roster collection file.

Each extracted row must quote a sentence that appears verbatim in the stored story text
and name the player in that quote or in the headline; failing rows are rejected and
written out for review. Accepted positives become an ``infections`` block and close
contacts a ``close_contacts`` block, in the same format as the other collections.
"""

import argparse
import csv
import io
import json
import re
import unicodedata
from pathlib import Path

import pandas as pd


def norm(s):
    s = unicodedata.normalize("NFKC", str(s))
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"')
    return re.sub(r"\s+", " ", s.replace("”", '"')).strip().lower()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stories", type=Path, required=True)
    ap.add_argument("--extracted", type=Path, nargs="+", required=True)
    ap.add_argument(
        "--out", type=Path, default=Path("data/collection/cricinfo_archive.txt")
    )
    ap.add_argument(
        "--rejects",
        type=Path,
        default=Path("data/collection/cricinfo_archive_rejects.csv"),
    )
    args = ap.parse_args()

    text, title = {}, {}
    for line in args.stories.open():
        r = json.loads(line)
        if r.get("status") == "ok":
            text[str(r["sid"])] = norm(r.get("title", "") + " " + r.get("text", ""))
            title[str(r["sid"])] = norm(r.get("title", ""))

    rows = pd.concat(
        [pd.read_csv(p, dtype=str, keep_default_na=False) for p in args.extracted],
        ignore_index=True,
    )
    rows["story_id"] = rows["story_id"].str.strip()
    surname = rows["player"].str.split().str[-1].map(norm)
    quote = rows["quote"].map(norm).str.strip(" .\"'")
    in_story = [q[:120] in text.get(sid, "") for q, sid in zip(quote, rows["story_id"])]
    # Quotes in the first person ("I tested positive") name the player in the headline.
    has_name = [
        s in q or s in title.get(sid, "")
        for s, q, sid in zip(surname, quote, rows["story_id"])
    ]
    rows["verified"] = [a and b for a, b in zip(in_story, has_name)]
    rows["reject_reason"] = [
        "" if a and b else ("quote not in story" if not a else "name not in quote")
        for a, b in zip(in_story, has_name)
    ]
    rows[~rows["verified"]].to_csv(args.rejects, index=False)
    ok = rows[rows["verified"]].copy()
    ok["date"] = pd.to_datetime(ok["date"].str[:10], errors="coerce").fillna(
        pd.to_datetime(ok["published"].str[:10], errors="coerce")
    )
    ok = ok[(ok["date"] >= "2020-03-01") & (ok["date"] <= "2022-12-31")]

    def block(df, name, cols):
        sio = io.StringIO()
        w = csv.writer(sio, lineterminator="\n")
        w.writerow(cols)
        w.writerows(df[cols].astype(str).values.tolist())
        return f"```{name}\n{sio.getvalue()}```"

    # A retrospective mention ("who had Covid earlier") carries the later story's date,
    # so it would invent a reinfection; keep those out of the episode list.
    notes = ok["notes"].fillna("").str.lower()
    retro = ok["date_type"].str.contains("retro", case=False) | notes.str.contains(
        r"retrospect|past infection|earlier infection|previous infection|had covid"
    )
    # Positives the reader could only infer (isolating, "forced out") are held back
    # unless another verified row states the positive for the same player.
    implied = notes.str.contains(r"impl|not explicit|does not say|doesn't say")
    explicit = ok[~implied & (ok["status"] == "positive")][["player", "date"]]
    near_explicit = pd.Series(False, index=ok.index)
    for idx, r in ok[implied].iterrows():
        same = explicit[explicit["player"] == r["player"]]
        near_explicit[idx] = bool(
            ((same["date"] - r["date"]).abs().dt.days <= 60).any()
        )
    held = implied & ~near_explicit
    # Not players: public figures or officials sharing a player's name.
    not_player = notes.str.contains(r"prime minister|president|match referee|umpire")
    review = ok[held | not_player].assign(
        held_reason=lambda d: [
            "implied" if h else "not a player" for h in held[d.index]
        ]
    )
    review.to_csv(args.out.with_name(args.out.stem + "_held.csv"), index=False)
    ok = ok[~(held | not_player)]
    notes = notes[ok.index]
    retro = retro[ok.index]
    ok[retro].to_csv(
        args.out.with_name(args.out.stem + "_retrospective.csv"), index=False
    )
    ok = ok[~retro]
    pos = ok[ok["status"] == "positive"].assign(
        country_or_team=lambda d: d["team"],
        level="",
        competition_or_series="",
        date=lambda d: d["date"].dt.date.astype(str),
        symptomatic_reported="unknown",
        source_url=lambda d: d["url"],
        second_source_url="",
        notes=lambda d: ("quote: " + d["quote"] + " | " + d["notes"]).str.strip(" |"),
    )
    cc = ok[ok["status"] == "close_contact"].assign(
        country_or_team=lambda d: d["team"],
        level="",
        competition_or_series="",
        date=lambda d: d["date"].dt.date.astype(str),
        source_url=lambda d: d["url"],
        notes=lambda d: "quote: " + d["quote"],
    )
    inf_cols = [
        "player",
        "country_or_team",
        "level",
        "competition_or_series",
        "date",
        "date_type",
        "symptomatic_reported",
        "source_url",
        "second_source_url",
        "notes",
    ]
    cc_cols = [
        "player",
        "country_or_team",
        "level",
        "competition_or_series",
        "date",
        "date_type",
        "source_url",
        "notes",
    ]
    header = (
        "Players named in archived ESPNcricinfo stories (Wayback Machine CDX index),\n"
        "read from stored story text; each quote was checked verbatim against it.\n"
    )
    args.out.write_text(
        header
        + "\n"
        + block(pos, "infections", inf_cols)
        + "\n\n"
        + block(cc, "close_contacts", cc_cols)
        + "\n"
    )
    fp = ok[ok["status"] == "false_positive"]
    fp.to_csv(args.out.with_name(args.out.stem + "_false_positives.csv"), index=False)
    print(
        f"extracted={len(rows)} verified={int(rows['verified'].sum())} "
        f"rejected={int((~rows['verified']).sum())} in_window={len(ok)} "
        f"positive={len(pos)} close_contact={len(cc)} false_positive={len(fp)} "
        f"retrospective={int(retro.sum())} held_for_review={len(review)}"
    )
    print(rows["reject_reason"].value_counts().to_string())


if __name__ == "__main__":
    main()
