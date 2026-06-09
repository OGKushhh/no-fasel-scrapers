"""
slug_audit.py — Fasel-HD episode slug discrepancy scanner
Scans output/episodes/<category>/ JSON files and reports slugs that are
truncated, have unknown suffixes, mismatched paths, duplicates, or
missing episode markers.

Usage:
    python slug_audit.py
    python slug_audit.py --dir "C:/path/to/output/episodes"
    python slug_audit.py --dir ./output/episodes --no-report

Output: console summary + slug_audit_report.txt in the same folder as
this script (unless --no-report is passed).
"""

import argparse
import json
import os
import re
from collections import defaultdict
from datetime import datetime
from urllib.parse import unquote

# ── Configuration ────────────────────────────────────────────────────────────

# Default path — override with --dir or change this string
DEFAULT_EPISODES_DIR = r"output/episodes"

# Folders to skip entirely
SKIP_CATEGORIES = {"arabic-series"}

# Expected URL path segment per category folder name
CATEGORY_PATH_SEGMENT = {
    "series":       "/episodes/",
    "asian-series": "/asian-episodes/",
    "tvshows":      "/tvepisodes/",
    "anime":        "/anime-episodes/",
}

# ── Known slug suffixes (after the episode number) ───────────────────────────
# Anything not matching these is flagged as UNKNOWN_SUFFIX.
# Each entry is (regex_pattern, human_label).
KNOWN_SUFFIXES = [
    # Dubbed variants
    (r"مدبلجة-م$",                 "Egyptian Dubbed"),
    (r"مدبلجة-ن$",                 "B&W Dubbed"),
    (r"مدبلجة$",                   "Dubbed"),
    # B&W version (subbed)
    (r"نسخة.*",                    "B&W Version"),
    # Final episode markers
    (r"والأخيرة$",                  "Final Episode"),
    (r"والاخيرة$",                  "Final Episode"),
    (r"الأخيرة$",                   "Final Episode"),
    (r"الاخيرة$",                   "Final Episode"),
    # Double/range episode  e.g. الحلقة-220-221
    (r"\d+$",                      "Double/Range Episode"),
    # الجزء (part two etc.)
    (r"الجزء-.+",                   "Episode Part"),
]

# ── Issue severity levels ─────────────────────────────────────────────────────
ERROR = "ERROR"
WARN  = "WARN"
INFO  = "INFO"

# ── ANSI colours (disabled on Windows if not supported) ──────────────────────
def _supports_colour():
    return os.name != "nt" or "ANSICON" in os.environ or "WT_SESSION" in os.environ

USE_COLOUR = _supports_colour()
RESET  = "\033[0m"  if USE_COLOUR else ""
RED    = "\033[31m" if USE_COLOUR else ""
YELLOW = "\033[33m" if USE_COLOUR else ""
CYAN   = "\033[36m" if USE_COLOUR else ""
BOLD   = "\033[1m"  if USE_COLOUR else ""
DIM    = "\033[2m"  if USE_COLOUR else ""

LEVEL_COLOUR = {ERROR: RED, WARN: YELLOW, INFO: CYAN}

# ─────────────────────────────────────────────────────────────────────────────

def get_episodes(season_value):
    """
    Handle both season structures:
      - {poster, episodes: [...]}   (series / asian-series / tvshows)
      - [...]                       (anime — direct list)
    """
    if isinstance(season_value, list):
        return season_value
    if isinstance(season_value, dict):
        return season_value.get("episodes", [])
    return []


def extract_slug(url: str, category: str) -> str:
    """Return the decoded slug segment from the URL."""
    path_seg = CATEGORY_PATH_SEGMENT.get(category, "/episodes/")
    decoded = unquote(url)
    if path_seg in decoded:
        return decoded.split(path_seg, 1)[-1]
    # Fallback: take everything after the last /
    return decoded.rstrip("/").split("/")[-1]


def check_path_segment(url: str, category: str):
    """Return an issue dict if the URL uses the wrong path segment, else None."""
    expected = CATEGORY_PATH_SEGMENT.get(category)
    if expected is None:
        return None
    decoded = unquote(url).lower()
    if expected not in decoded:
        # Find which segment IS present
        found = next(
            (seg for seg in CATEGORY_PATH_SEGMENT.values() if seg in decoded),
            None,
        )
        return {
            "level": ERROR,
            "code":  "PATH_MISMATCH",
            "detail": f"expected '{expected}', got '{found or '?'}'",
        }
    return None


def classify_slug(slug: str, category: str):
    """
    Classify a slug and return a list of issue dicts (may be empty = clean).

    Possible codes:
      TRUNCATED        slug ends with الحلق (missing ة + number)
      NO_EP_MARKER     no الحلقة and no known alternative (OVA, raw English)
      OVA              contains الاوفا  (informational)
      RAW_ENGLISH      no Arabic at all (anime ep 1 pattern)
      UNKNOWN_SUFFIX   suffix after episode number not in KNOWN_SUFFIXES
    """
    issues = []

    # ── Truncated: ends with الحلق without ة ─────────────────────────────────
    if re.search(r"الحلق$", slug) or re.search(r"الحلق-\d*$", slug.rstrip("-")):
        issues.append({
            "level":  ERROR,
            "code":   "TRUNCATED",
            "detail": "slug ends with الحلق (missing ة and/or episode number)",
        })
        return issues  # No point checking further

    # ── No Arabic at all (raw English slug) ──────────────────────────────────
    if not re.search(r"[\u0600-\u06FF]", slug):
        issues.append({
            "level":  INFO,
            "code":   "RAW_ENGLISH",
            "detail": f"no Arabic in slug: '{slug}'",
        })
        return issues

    # ── OVA ──────────────────────────────────────────────────────────────────
    if "الاوفا" in slug or "أوفا" in slug:
        issues.append({
            "level":  INFO,
            "code":   "OVA",
            "detail": "OVA episode (no الحلقة expected)",
        })
        return issues

    # ── No episode marker at all ─────────────────────────────────────────────
    if "الحلقة" not in slug and "الحلقه" not in slug:
        issues.append({
            "level":  WARN,
            "code":   "NO_EP_MARKER",
            "detail": f"neither الحلقة nor الحلقه found in: '{slug}'",
        })
        return issues

    # ── Extract what comes after الحلقة-<number> ─────────────────────────────
    # Matches: الحلقة-123  or  الحلقة-123-456  (double ep)
    m = re.search(r"[الحلقةه]{6}-(\d+)(.*?)$", slug)
    if not m:
        # الحلقة present but no number follows
        issues.append({
            "level":  WARN,
            "code":   "NO_EP_NUMBER",
            "detail": f"الحلقة found but no number follows in: '{slug}'",
        })
        return issues

    remainder = m.group(2).lstrip("-")  # whatever trails the first episode number

    if not remainder:
        return []  # Clean plain slug

    # ── Check against known suffixes ─────────────────────────────────────────
    for pattern, label in KNOWN_SUFFIXES:
        if re.match(pattern, remainder):
            return []  # Known — clean

    # Nothing matched
    issues.append({
        "level":  WARN,
        "code":   "UNKNOWN_SUFFIX",
        "detail": f"unrecognised suffix '-{remainder}' in: '{slug}'",
    })
    return issues


def audit_file(filepath: str, category: str):
    """
    Audit one JSON file. Returns a list of finding dicts:
      { season, url, slug, level, code, detail }
    """
    findings = []

    try:
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return [{"season": "—", "url": "", "slug": "", "level": ERROR,
                 "code": "JSON_ERROR", "detail": str(e)}]

    seasons = data.get("seasons", {})
    if not isinstance(seasons, dict):
        return [{"season": "—", "url": "", "slug": "", "level": ERROR,
                 "code": "BAD_STRUCTURE", "detail": "'seasons' is not a dict"}]

    for sk, sv in seasons.items():
        eps = get_episodes(sv)
        seen_urls = {}  # url → first index

        for idx, url in enumerate(eps):
            slug = extract_slug(url, category)

            # Duplicate check
            if url in seen_urls:
                findings.append({
                    "season": sk, "url": url, "slug": slug,
                    "level": ERROR, "code": "DUPLICATE_URL",
                    "detail": f"also at index {seen_urls[url]}",
                })
                continue
            seen_urls[url] = idx

            # Path segment check
            path_issue = check_path_segment(url, category)
            if path_issue:
                findings.append({"season": sk, "url": url, "slug": slug, **path_issue})

            # Slug classification
            for issue in classify_slug(slug, category):
                findings.append({"season": sk, "url": url, "slug": slug, **issue})

    return findings


def level_order(level):
    return {ERROR: 0, WARN: 1, INFO: 2}.get(level, 3)


def run_audit(episodes_dir: str, write_report: bool):
    if not os.path.isdir(episodes_dir):
        print(f"{RED}[ERROR]{RESET} Directory not found: {episodes_dir}")
        return

    print(f"\n{BOLD}Fasel-HD Slug Auditor{RESET}")
    print(f"Scanning: {episodes_dir}")
    print(f"Skipping: {', '.join(sorted(SKIP_CATEGORIES))}\n")
    print("─" * 70)

    # Counters
    total_files = total_eps = 0
    counts = defaultdict(int)   # level → count
    # Results: category → filename → [findings]
    results = defaultdict(dict)

    categories = sorted(
        d for d in os.listdir(episodes_dir)
        if os.path.isdir(os.path.join(episodes_dir, d)) and d not in SKIP_CATEGORIES
    )

    for cat in categories:
        cat_dir = os.path.join(episodes_dir, cat)
        json_files = sorted(f for f in os.listdir(cat_dir) if f.endswith(".json"))

        for fname in json_files:
            total_files += 1
            fpath = os.path.join(cat_dir, fname)

            # Count episodes in this file for stats
            try:
                with open(fpath, encoding="utf-8") as f:
                    d = json.load(f)
                for sv in d.get("seasons", {}).values():
                    total_eps += len(get_episodes(sv))
            except Exception:
                pass

            findings = audit_file(fpath, cat)
            if findings:
                results[cat][fname] = sorted(findings, key=lambda x: level_order(x["level"]))
                for f in findings:
                    counts[f["level"]] += 1

    # ── Console output ────────────────────────────────────────────────────────
    report_lines = []

    def emit(line=""):
        print(line)
        report_lines.append(re.sub(r"\033\[\d+m", "", line))  # strip ANSI for file

    emit(f"Scanned {total_files} files / {total_eps:,} episodes across {len(categories)} categories")
    emit(f"Issues found — {RED}ERROR: {counts[ERROR]}{RESET}  "
         f"{YELLOW}WARN: {counts[WARN]}{RESET}  "
         f"{CYAN}INFO: {counts[INFO]}{RESET}")
    emit("─" * 70)

    if not any(results.values()):
        emit(f"\n✓ No issues found.")
    else:
        for cat in categories:
            if cat not in results:
                continue
            emit(f"\n{BOLD}[{cat}]{RESET}")
            for fname, findings in sorted(results[cat].items()):
                content_id = fname.replace(".json", "")
                emit(f"  {DIM}{content_id}{RESET}  ({len(findings)} issue{'s' if len(findings)!=1 else ''})")
                for f in findings:
                    col = LEVEL_COLOUR.get(f["level"], "")
                    emit(f"    {col}[{f['level']:5}]{RESET} [{f['code']}]  "
                         f"season={f['season']}  {f['detail']}")
                    if f["slug"] and f["code"] not in ("DUPLICATE_URL", "PATH_MISMATCH", "JSON_ERROR"):
                        emit(f"           {DIM}slug: {f['slug']}{RESET}")

    emit("\n" + "─" * 70)
    emit(f"Done — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # ── Write report file ─────────────────────────────────────────────────────
    if write_report:
        report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "slug_audit_report.txt")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(report_lines))
        print(f"\nReport saved → {report_path}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit fasel-hd episode slug files")
    parser.add_argument(
        "--dir",
        default=DEFAULT_EPISODES_DIR,
        help="Path to the output/episodes directory",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Skip writing slug_audit_report.txt",
    )
    args = parser.parse_args()
    run_audit(args.dir, not args.no_report)
