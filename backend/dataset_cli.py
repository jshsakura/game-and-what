"""Ship the name dictionary out, or take somebody else's in.

    python3 dataset_cli.py export                     # -> data/names.ko.json (the seed)
    python3 dataset_cli.py import data/names.ko.json  # merge a file
    python3 dataset_cli.py import https://host/api/dataset/names   # merge from a server

Export writes the file the repo carries and a fresh install seeds itself from. Import
merges without ever overwriting: a name resolved by hand outranks anything a file says,
so re-importing is safe and idempotent.

What goes in it, and the two things that deliberately do not (cover images, IGDB scores),
are settled in app/services/dataset.py — not here.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

from app import db
from app.services import dataset


def load(src: str) -> dict:
    if src.startswith(("http://", "https://")):
        with urllib.request.urlopen(src, timeout=30) as resp:      # noqa: S310 — explicit url
            return json.loads(resp.read().decode("utf-8"))
    return json.loads(Path(src).read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    ex = sub.add_parser("export", help="write the shareable dictionary")
    ex.add_argument("--out", type=Path, default=dataset.SEED_PATH)
    ex.add_argument("--lang", default="ko")

    im = sub.add_parser("import", help="merge a dictionary (file or URL)")
    im.add_argument("src")
    im.add_argument("--lang", default="ko")

    args = ap.parse_args()
    db.init_db()

    if args.cmd == "export":
        with db.connect() as conn:
            payload = dataset.export_names(conn, lang=args.lang)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                            encoding="utf-8")
        print(f"{payload['count']} name(s) -> {args.out}")
        return 0

    payload = load(args.src)
    with db.connect() as conn:
        added, skipped = dataset.import_names(conn, payload, lang=args.lang)
    print(f"{added} added, {skipped} already known (a local name always wins)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
