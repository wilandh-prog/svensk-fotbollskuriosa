"""The single idempotent update entrypoint: python -m pipeline.update

fetch latest data -> upsert (transactional) -> sanity gate -> recompute
curiosities -> export site data. Exits non-zero (without exporting) if
any sanity check fails, so CI never commits or deploys partial data.
"""
from __future__ import annotations

import sys

from . import (
    db,
    export,
    ingest_openfootball,
    ingest_sportomedia,
    ingest_wfb,
    ingest_wiki,
    sanity,
)


def main() -> int:
    conn = db.connect()
    try:
        print("== Wikipedia-säsonger ==")
        ingest_wiki.run(conn)
        print("== openfootball ==")
        ingest_openfootball.run(conn)
        print("== cache.wfb ==")
        ingest_wfb.run(conn)
        # last, so its dated (and separately verified) match data wins over
        # the date-less Wikipedia matrices wherever it checks out
        print("== spelprogram och datumsatta matcher (liga-API) ==")
        ingest_sportomedia.run(conn)

        print("== Sanity-kontroller ==")
        failures = sanity.run(conn)
        if failures:
            print(f"{len(failures)} sanity-fel — avbryter utan att exportera:")
            for f in failures:
                print(" -", f)
            return 1
        print("Alla sanity-kontroller OK")

        print("== Export ==")
        export.run(conn)
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
