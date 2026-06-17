#!/usr/bin/env python3
"""
sync_to_abdobest.py – Copy only changed files from ./output to ../AbdoBest/data
Then git add/commit/push in the AbdoBest directory.
Excludes progress files, backups, and temporary index files.
Includes all JSON files, episodes/, ratings/, and sorted/.
"""

import shutil
import subprocess
import sys
from pathlib import Path

# ========== CONFIGURATION ==========
SCRIPT_DIR = Path(__file__).parent.resolve()          # directory of this script

# Absolute path to the Git repository (AbdoBest folder inside the same repo)
GIT_REPO_DIR = Path(r"C:\Users\abdo\Documents\GitHub\no-fasel-scrapers\AbdoBest")

# Source is "output" next to this script
SOURCE_DIR = SCRIPT_DIR / "output"

# Target is "data" inside the AbdoBest folder
TARGET_DIR = GIT_REPO_DIR / "data"

GIT_COMMIT_MSG = "content update"

# Files/folders to exclude (exact names or patterns)
EXCLUDE_NAMES = {
    "mal_update_progress.txt",
    "episode_update_progress.txt",
    "runtime_update_progress.txt",
    "image-indices.json",
    "baks",
}
EXCLUDE_PREFIXES = ("last_page_",)   # any file starting with this
EXCLUDE_SUFFIXES = (".txt",)         # any .txt file (progress files)
# ===================================

def should_exclude(path: Path) -> bool:
    """Return True if the file/folder should not be synced."""
    name = path.name
    if name in EXCLUDE_NAMES:
        return True
    if name.startswith(EXCLUDE_PREFIXES):
        return True
    if name.endswith(EXCLUDE_SUFFIXES):
        return True
    return False

def sync_files(src: Path, dst: Path) -> bool:
    """Recursively copy changed files from src to dst. Returns True if any file was copied."""
    if not src.exists():
        print(f"❌ Source directory not found: {src}")
        return False

    dst.mkdir(parents=True, exist_ok=True)
    changed = False

    for src_path in src.rglob("*"):
        if should_exclude(src_path):
            continue

        rel_path = src_path.relative_to(src)
        dst_path = dst / rel_path

        if src_path.is_file():
            if not dst_path.exists() or src_path.stat().st_mtime > dst_path.stat().st_mtime:
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_path, dst_path)
                print(f"📁 Copied: {rel_path}")
                changed = True
        elif src_path.is_dir():
            dst_path.mkdir(parents=True, exist_ok=True)

    return changed

def git_commit_and_push():
    """Run git add, commit, push in the AbdoBest repository."""
    if not GIT_REPO_DIR.exists():
        print(f"❌ Git repository not found: {GIT_REPO_DIR}")
        return False

    original_cwd = Path.cwd()
    try:
        # Change to Git repo directory
        print(f"📂 Entering {GIT_REPO_DIR}")
        os.chdir(GIT_REPO_DIR)

        # git add .
        print("➕ git add .")
        subprocess.run(["git", "add", "."], check=True, capture_output=True, text=True)

        # git commit -m "..."
        print(f"📝 git commit -m \"{GIT_COMMIT_MSG}\"")
        result = subprocess.run(
            ["git", "commit", "-m", GIT_COMMIT_MSG],
            capture_output=True,
            text=True
        )
        if result.returncode != 0 and "nothing to commit" not in result.stderr:
            print("⚠️ Commit warning:\n", result.stderr)
        elif "nothing to commit" in result.stderr:
            print("✅ No changes to commit (working tree clean)")

        # git push
        print("🚀 git push")
        subprocess.run(["git", "push"], check=True, capture_output=True, text=True)

        print("✅ Git operations completed.")
        return True

    except subprocess.CalledProcessError as e:
        print(f"❌ Git command failed:\n{e.stderr}")
        return False
    finally:
        # Change back to original directory
        os.chdir(original_cwd)

def main():
    if not SOURCE_DIR.exists():
        print(f"Error: {SOURCE_DIR} does not exist.")
        sys.exit(1)

    print(f"Syncing from {SOURCE_DIR} to {TARGET_DIR}...")
    changed = sync_files(SOURCE_DIR, TARGET_DIR)

    if changed:
        print("✅ Files were copied.")
        print("\n--- Starting Git automation ---")
        git_commit_and_push()
    else:
        print("✅ No changes detected. Skipping Git operations.")

if __name__ == "__main__":
    import os  # for chdir
    main()