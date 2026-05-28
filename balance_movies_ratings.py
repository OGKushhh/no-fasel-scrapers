#!/usr/bin/env python3
"""
balance_movies_ratings.py – Check number of rating files in movies/ folder.
If > 10,000, move random extra files to movies2/ until under limit.
"""

import random
import shutil
from pathlib import Path

RATINGS_DIR = Path("./output/ratings")
MOVIES_DIR = RATINGS_DIR / "movies"
MOVIES2_DIR = RATINGS_DIR / "movies2"
LIMIT = 10000
SAFE_LIMIT = 9500   # we will move until below this number

def main():
    if not MOVIES_DIR.exists():
        print(f"❌ {MOVIES_DIR} not found.")
        return

    files = list(MOVIES_DIR.glob("*.json"))
    total = len(files)
    print(f"Current files in movies/: {total}")

    if total <= LIMIT:
        print(f"✅ Under limit ({LIMIT}). No action needed.")
        return

    to_move = total - SAFE_LIMIT
    if to_move <= 0:
        print("Already within safe limit.")
        return

    print(f"Need to move {to_move} files to movies2/")
    MOVIES2_DIR.mkdir(parents=True, exist_ok=True)

    # Randomly select files to move
    selected = random.sample(files, to_move)

    moved = 0
    for src in selected:
        dst = MOVIES2_DIR / src.name
        shutil.move(str(src), str(dst))
        moved += 1
        if moved % 1000 == 0:
            print(f"Moved {moved} files...")

    print(f"✅ Moved {moved} files to {MOVIES2_DIR}.")
    # Verify new count
    remaining = list(MOVIES_DIR.glob("*.json"))
    print(f"movies/ now has {len(remaining)} files.")

if __name__ == "__main__":
    main()