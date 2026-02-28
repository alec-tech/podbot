#!/usr/bin/env python3
"""
migrate_to_multishow.py — One-time migration from flat paths to per-show directories.

Moves legacy flat-path data into the new shows/{slug}/ and per-show runtime directories.
Safe to run multiple times (idempotent — skips files that already exist at destination).

Usage:
    python migrate_to_multishow.py          # Dry run (shows what would happen)
    python migrate_to_multishow.py --apply  # Actually move files
"""

import shutil
import argparse
from pathlib import Path

ROOT = Path(__file__).parent

# (source, destination, description)
MIGRATIONS = [
    # Website data → per-show website dir
    ("website/episodes.json", "website/the-signal/episodes.json", "Episode data"),
    ("website/feed.xml", "website/the-signal/feed.xml", "RSS feed"),

    # Old flat database → per-show database dir (if not already migrated)
    ("database/story_memory.db", "database/the-signal/story_memory.db", "Story memory DB"),

    # Old flat injected stories → per-show data dir
    ("data/injected_stories.json", "data/the-signal/injected_stories.json", "Injected stories"),
]

# Files that are superseded and can be removed after migration
SUPERSEDED = [
    ("config/show_config.json", "Superseded by shows/the-signal/show.json"),
]


def run(apply: bool = False):
    print(f"{'APPLYING' if apply else 'DRY RUN'}: Multi-show data migration\n")

    moved = 0
    skipped = 0
    already = 0

    for src_rel, dst_rel, desc in MIGRATIONS:
        src = ROOT / src_rel
        dst = ROOT / dst_rel

        if not src.exists():
            print(f"  SKIP  {src_rel} (not found)")
            skipped += 1
            continue

        if dst.exists():
            # Check if it's the same file (already migrated in-place)
            if src.resolve() == dst.resolve():
                print(f"  OK    {dst_rel} (same file)")
                already += 1
                continue
            print(f"  EXISTS {dst_rel} (already migrated)")
            already += 1
            continue

        if apply:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dst))
            print(f"  COPY  {src_rel} → {dst_rel}  ({desc})")
        else:
            print(f"  WOULD COPY  {src_rel} → {dst_rel}  ({desc})")
        moved += 1

    print()
    for path_rel, reason in SUPERSEDED:
        path = ROOT / path_rel
        if path.exists():
            if apply:
                path.unlink()
                print(f"  REMOVED  {path_rel}  ({reason})")
            else:
                print(f"  WOULD REMOVE  {path_rel}  ({reason})")

            # Remove parent dir if empty
            if apply and path.parent.exists() and not any(path.parent.iterdir()):
                path.parent.rmdir()
                print(f"  REMOVED  {path.parent.relative_to(ROOT)}/  (empty dir)")
        else:
            print(f"  SKIP  {path_rel} (already removed)")

    print(f"\nSummary: {moved} copied, {already} already done, {skipped} not found")
    if not apply and moved > 0:
        print("\nRun with --apply to execute the migration.")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Migrate flat-path data to per-show directories")
    p.add_argument("--apply", action="store_true", help="Actually move files (default: dry run)")
    args = p.parse_args()
    run(apply=args.apply)
