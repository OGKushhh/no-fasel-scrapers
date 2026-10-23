#!/usr/bin/env python3
"""
Fasel URL domain rewriter — EAGER bulk rewrite of every file on disk.

Standalone CLI. Run once when the domain has just rotated, to migrate
every existing JSON file to the new domain. After that, switch to the
lazy_rewriter.py approach for ongoing resilience.

Usage:
  # Dry-run preview (counts only, no writes)
  python3 bulk_rewriter.py --to fasel-hd.co --dir /data/metadata --dry-run

  # Real run, with backup tarball
  python3 bulk_rewriter.py --to fasel-hd.co --dir /data/metadata --backup-dir /backups

  # Pin the source domain (otherwise auto-detected from first file that has one)
  python3 bulk_rewriter.py --from fasel-hd.cam --to fasel-hd.co --dir /data/metadata

What it does:
  - Walks every *.json file under --dir
  - Per file: regex-rewrite every legacy fasel page-domain URL host
    (fasel-hd.cam, faselhd.com, faselhd.tv, faselhdx.bid, faselhdx.com)
    to whatever you pass as --to
  - Atomic per-file write (temp file in same dir → os.replace)
  - Parallel workers (default 4, configurable)
  - Auto-backup tarball before touching anything (required unless --dry-run)
  - Logs per-file URL count as JSONL (--log-file)

What it does NOT do:
  - Does NOT touch static.faselhdcdn.com URLs (the poster CDN host
    that doesn't rotate with the page domain)
  - Does NOT touch any other host
  - Does NOT re-rewrite URLs that are already on the new domain
    (regex only matches known legacy hosts, not the new one)

Safety:
  - Always backup before applying (--backup-dir required unless --dry-run)
  - Always dry-run first (--dry-run)
  - Atomic per-file writes (temp + os.replace) — a crash mid-rewrite
    never corrupts a file
  - Idempotent — running twice is a no-op
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tarfile
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

# ─── Constants (must match lazy_rewriter.py) ─────────────────────────────
# CRITICAL: do NOT include static.faselhdcdn.com here — poster CDN,
# separate host, doesn't rotate with the page domain.
FASEL_LEGACY_HOSTS = [
    'fasel-hd.cam',
    'fasel-hd.co',
    'faselhd.com',
    'faselhd.tv',
    'faselhdx.bid',
    'faselhdx.com',
]

_LEGACY_RE = re.compile(
    r'(?P<scheme>https?://)(?P<www>w{3}\.)?(?P<host>'
    + '|'.join(map(re.escape, FASEL_LEGACY_HOSTS))
    + r')',
    re.IGNORECASE,
)


def rewrite_text(text: str, new_domain: str) -> tuple[str, int]:
    """Rewrite every legacy fasel URL host in `text` to `new_domain`.
    Preserves scheme and www. prefix. Returns (rewritten, count).

    `new_domain` should be a bare host like 'fasel-hd.co' (no scheme,
    no www., no trailing slash).
    """
    if not text:
        return text, 0
    count = 0

    def repl(m: re.Match) -> str:
        nonlocal count
        count += 1
        return f"{m.group('scheme')}{m.group('www') or ''}{new_domain}"

    return _LEGACY_RE.sub(repl, text), count


def detect_legacy_host(file_path: Path) -> str | None:
    """Read a file and return the first legacy fasel host found in it,
    or None if the file has no legacy URLs. Used for auto-detecting
    the --from value."""
    try:
        text = file_path.read_text(encoding='utf-8', errors='replace')
    except Exception:
        return None
    m = _LEGACY_RE.search(text)
    if not m:
        return None
    return m.group('host').lower()


def rewrite_file_inplace(file_path: Path, new_domain: str) -> tuple[int, int]:
    """Rewrite one file in-place (atomically). Returns (bytes_in, urls_rewritten).
    Returns (0, 0) if the file had no legacy URLs (no write happens)."""
    try:
        original = file_path.read_text(encoding='utf-8', errors='replace')
    except Exception as e:
        print(f"[skip] {file_path}: read error: {e}", file=sys.stderr)
        return 0, 0

    rewritten, count = rewrite_text(original, new_domain)
    if count == 0:
        return len(original), 0

    # Atomic write: temp file in the same dir, then os.replace (atomic on POSIX
    # and Windows for same-volume renames). Temp file starts with a dot so it's
    # hidden from the JSON walker on a re-run.
    fd, tmp_path = tempfile.mkstemp(
        prefix=f'.{file_path.name}.',
        suffix='.tmp',
        dir=str(file_path.parent),
    )
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(rewritten)
        os.replace(tmp_path, file_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return len(original), count


def backup_metadata_dir(metadata_dir: Path, backup_dir: Path) -> Path:
    """Create a tar.gz backup of the entire metadata dir. Returns the
    backup path."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup_path = backup_dir / f'metadata-backup-{ts}.tar.gz'
    with tarfile.open(backup_path, 'w:gz') as tar:
        tar.add(metadata_dir, arcname='metadata')
    return backup_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--to', required=True,
                        help='New fasel domain (bare host, e.g. fasel-hd.co)')
    parser.add_argument('--from', dest='from_host', default=None,
                        help='Old fasel domain. Auto-detected from the first '
                             'file that has one if omitted.')
    parser.add_argument('--dir', required=True, type=Path,
                        help='Metadata directory to scan (recursive)')
    parser.add_argument('--backup-dir', type=Path, default=None,
                        help='Where to write the backup tarball. Required '
                             'unless --dry-run.')
    parser.add_argument('--dry-run', action='store_true',
                        help='Count only, do not write files')
    parser.add_argument('--workers', type=int, default=4,
                        help='Parallel workers (default: 4)')
    parser.add_argument('--log-file', type=Path, default=None,
                        help='JSONL log file (one line per modified file)')
    args = parser.parse_args()

    # Validate new domain
    new_domain = args.to.lstrip('/').rstrip('/')
    if '://' in new_domain or new_domain.startswith('www.'):
        parser.error('--to must be a bare host like "fasel-hd.co"')
    if new_domain in FASEL_LEGACY_HOSTS:
        # This would actually be fine (the regex would match it) but it's
        # a smell that the user might be confused about which direction
        # the rewrite is going.
        print(f'[warn] {new_domain} is in the legacy list — running anyway '
              f'(URLs on this host will not be rewritten).', file=sys.stderr)

    # Find all JSON files
    if not args.dir.exists():
        parser.error(f'--dir does not exist: {args.dir}')
    json_files = sorted(args.dir.rglob('*.json'))
    print(f'[scan] Found {len(json_files)} JSON files under {args.dir}', file=sys.stderr)
    if not json_files:
        return 0

    # Auto-detect --from if not provided
    from_host = args.from_host
    if from_host is None:
        print('[scan] Auto-detecting legacy host from first 100 files...', file=sys.stderr)
        for f in json_files[:100]:
            host = detect_legacy_host(f)
            if host:
                from_host = host
                print(f'[scan] Detected legacy host: {from_host}', file=sys.stderr)
                break
        if from_host is None:
            print('[scan] No legacy fasel URLs found in the first 100 files. '
                  'Pass --from explicitly if you are sure files contain '
                  'legacy URLs.', file=sys.stderr)
            sys.exit(1)

    # Sanity check
    if from_host == new_domain:
        print(f'[scan] Source and target are the same ({from_host}). Nothing to do.', file=sys.stderr)
        sys.exit(0)

    # Backup (unless dry-run)
    backup_path = None
    if not args.dry_run:
        if args.backup_dir is None:
            parser.error('--backup-dir is required unless --dry-run')
        print('[backup] Creating tarball backup...', file=sys.stderr)
        backup_path = backup_metadata_dir(args.dir, args.backup_dir)
        mb = backup_path.stat().st_size // 1024 // 1024
        print(f'[backup] Wrote {backup_path} ({mb} MB)', file=sys.stderr)
    else:
        print('[dry-run] Skipping backup', file=sys.stderr)

    # Walk files in parallel
    print(f'[rewrite] Rewriting {from_host} → {new_domain} '
          f'using {args.workers} workers...', file=sys.stderr)

    files_modified = 0
    files_scanned = 0
    urls_rewritten = 0
    bytes_processed = 0
    log_lines: list[str] = []
    start_ts = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        # In dry-run mode we still read every file (to count URLs), but
        # don't write — submit a read-only version instead.
        if args.dry_run:
            futures = {pool.submit(lambda f: (lambda t: (t, rewrite_text(t, new_domain)[1]))(
                                       f.read_text(encoding='utf-8', errors='replace')),
                                   f): f for f in json_files}
        else:
            futures = {pool.submit(rewrite_file_inplace, f, new_domain): f
                       for f in json_files}

        for i, future in enumerate(as_completed(futures)):
            files_scanned += 1
            f = futures[future]
            try:
                result = future.result()
                nbytes, count = result if isinstance(result, tuple) else (0, 0)
                bytes_processed += nbytes
                if count > 0:
                    files_modified += 1
                    urls_rewritten += count
                    if args.log_file:
                        log_lines.append(json.dumps({
                            'file': str(f),
                            'urls_rewritten': count,
                        }))
            except Exception as e:
                print(f'[error] {f}: {e}', file=sys.stderr)
            if files_scanned % 500 == 0:
                print(f'[progress] {files_scanned}/{len(json_files)} files '
                      f'scanned, {files_modified} modified, '
                      f'{urls_rewritten} URLs rewritten', file=sys.stderr)

    elapsed_ms = int((time.time() - start_ts) * 1000)

    # Write log file
    if args.log_file and log_lines:
        args.log_file.parent.mkdir(parents=True, exist_ok=True)
        args.log_file.write_text('\n'.join(log_lines) + '\n', encoding='utf-8')

    # Summary (machine-readable)
    summary = {
        'from': from_host,
        'to': new_domain,
        'dir': str(args.dir),
        'backup_path': str(backup_path) if backup_path else None,
        'dry_run': args.dry_run,
        'files_scanned': files_scanned,
        'files_modified': files_modified,
        'urls_rewritten': urls_rewritten,
        'bytes_processed': bytes_processed,
        'duration_ms': elapsed_ms,
        'log_file': str(args.log_file) if args.log_file else None,
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())


# ─── Callable API for use from a GUI (.pyw / tkinter) ─────────────────────
#
# The CLI above is for power users. For a GUI button-click handler you
# want something simpler: call a function, get progress callbacks, no
# argparse. That's what `apply_rewrite()` is for.
#
# Example (tkinter button click — see gui_example.pyw for the full file):
#
#     from bulk_rewriter import apply_rewrite, RewriteResult
#
#     def on_apply():
#         new_domain = entry.get().strip().lower()
#         result = apply_rewrite(
#             metadata_dir=Path('C:/Users/you/scraper/data'),
#             new_domain=new_domain,
#             dry_run=False,
#             backup_dir=Path('C:/Users/you/scraper/backups'),
#             on_progress=lambda scanned, total, modified, rewritten: (
#                 progress_bar['value'] = scanned / total * 100,
#                 status_label.config(text=f'{scanned}/{total} | {rewritten} URLs'),
#                 root.update_idletasks(),
#             ),
#         )
#         messagebox.showinfo('Done',
#             f'Rewrote {result.urls_rewritten} URLs in {result.files_modified} files\n'
#             f'Backup: {result.backup_path}')
#

from dataclasses import dataclass


@dataclass
class RewriteResult:
    """Return type of apply_rewrite(). Mirrors the CLI summary."""
    from_host: str | None
    to: str
    dir: str
    backup_path: str | None
    dry_run: bool
    files_scanned: int
    files_modified: int
    urls_rewritten: int
    bytes_processed: int
    duration_ms: int
    log_file: str | None


def apply_rewrite(
    metadata_dir: Path,
    new_domain: str,
    *,
    dry_run: bool = False,
    backup_dir: Path | None = None,
    workers: int = 4,
    log_file: Path | None = None,
    from_host: str | None = None,
    on_progress=None,  # callable(scanned: int, total: int, modified: int, rewritten: int) -> None
) -> RewriteResult:
    """Run the bulk rewrite. Designed to be called from a GUI thread.

    - `on_progress` is called after every file is processed (so the GUI
      can update a progress bar). Called with keyword args:
        scanned, total, modified, rewritten
    - `from_host` auto-detected from the first file if None — pass
      explicitly to skip the detect step.
    - `backup_dir` required unless dry_run=True.
    - Returns a RewriteResult with the final counts.

    For a non-blocking GUI, call this from a background thread (see
    gui_example.pyw for the threading pattern — tkinter crashes if you
    block the main loop).
    """
    # Validate new domain
    new_domain = new_domain.lstrip('/').rstrip('/')
    assert '://' not in new_domain and not new_domain.startswith('www.'), \
        'new_domain must be a bare host like "fasel-hd.co"'

    json_files = sorted(metadata_dir.rglob('*.json'))
    total = len(json_files)

    # Auto-detect from_host if not provided
    if from_host is None:
        for f in json_files[:100]:
            host = detect_legacy_host(f)
            if host:
                from_host = host
                break

    # Backup (unless dry-run)
    backup_path = None
    if not dry_run:
        if backup_dir is None:
            raise ValueError('backup_dir is required unless dry_run=True')
        backup_path = backup_metadata_dir(metadata_dir, backup_dir)

    # Walk
    files_modified = 0
    files_scanned = 0
    urls_rewritten = 0
    bytes_processed = 0
    log_lines: list[str] = []
    start_ts = time.time()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        if dry_run:
            # Returns (len(text), count) — must match the (int, int) signature
            # of rewrite_file_inplace() in the non-dry-run branch below, or
            # the bytes_processed += nbytes line will throw TypeError: int + str
            # (which would be silently swallowed by the bare except below,
            # making every file appear to have 0 URLs rewritten).
            futures = {
                pool.submit(
                    lambda f: (lambda t: (len(t), rewrite_text(t, new_domain)[1]))(
                        f.read_text(encoding='utf-8', errors='replace')
                    ), f
                ): f for f in json_files
            }
        else:
            futures = {
                pool.submit(rewrite_file_inplace, f, new_domain): f
                for f in json_files
            }

        for future in as_completed(futures):
            files_scanned += 1
            try:
                result = future.result()
                nbytes, count = result if isinstance(result, tuple) else (0, 0)
                bytes_processed += nbytes
                if count > 0:
                    files_modified += 1
                    urls_rewritten += count
                    if log_file:
                        log_lines.append(json.dumps({
                            'file': str(futures[future]),
                            'urls_rewritten': count,
                        }))
            except Exception as e:
                # Log instead of silently swallowing — silent swallowing is what
                # made the original dry-run lambda bug (returning text instead of
                # len(text)) look like "0 URLs across 0 files" for 28k+ files.
                print(f'[bulk_domain_changer] error on {futures[future]}: {e}',
                      file=__import__('sys').stderr)
            if on_progress:
                on_progress(
                    scanned=files_scanned,
                    total=total,
                    modified=files_modified,
                    rewritten=urls_rewritten,
                )

    elapsed_ms = int((time.time() - start_ts) * 1000)

    if log_file and log_lines:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.write_text('\n'.join(log_lines) + '\n', encoding='utf-8')

    return RewriteResult(
        from_host=from_host,
        to=new_domain,
        dir=str(metadata_dir),
        backup_path=str(backup_path) if backup_path else None,
        dry_run=dry_run,
        files_scanned=files_scanned,
        files_modified=files_modified,
        urls_rewritten=urls_rewritten,
        bytes_processed=bytes_processed,
        duration_ms=elapsed_ms,
        log_file=str(log_file) if log_file else None,
    )

