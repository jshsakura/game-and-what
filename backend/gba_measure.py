"""Push the measured GBA numbers into the library, by hand.

`scripts/gba_idle_loop_db.json` is the source of truth: per game code, the idle-loop
address gpSP needs, the cycles the game spends working per frame, and the sound driver
the firmware replaces (measured by running the rom — see scripts/idlefind). This copies
them onto the roms table so the library shows a verdict instead of just "the skip exists".

The app now does exactly this at startup for every deployment (services/gba_seed), so a
Docker install already arrives measured. This stays as the CLI form — useful for stamping
a running deployment right after refreshing the table, without a restart. Both call the
same code; reads the game code from each cart header, so the filename does not matter.
Idempotent.
"""
from app import db
from app.services import gba_seed


def main() -> None:
    # The schema is migrated on app startup, and this script does not go through it — so a
    # run right after a new column is added would fail on a column the app would have made.
    # Ask for it here; init_db is idempotent.
    db.init_db()
    with db.connect() as conn:
        updated = gba_seed.apply_table(conn)
    print(f"{updated} rom(s) updated from the table")


if __name__ == "__main__":
    main()
