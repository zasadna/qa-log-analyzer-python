from __future__ import annotations

import csv
import re
import sys
from pathlib import Path
from collections import defaultdict, Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Iterable, Tuple, Set


# ============================================================
# CONFIGURATION
# ============================================================

# Input folder with logs
LOG_FOLDER = Path("example_logs")

# Folder where reports will be created
REPORTS_ROOT = Path("reports")

# File extensions to scan
ALLOWED_EXTENSIONS = {".log", ".txt", ".out"}

# Folders to skip completely
SKIP_DIR_NAMES = {
    ".git",
    ".idea",
    "__pycache__",
    "node_modules",
}

# Optional: skip files larger than this size in MB (None = no limit)
MAX_FILE_SIZE_MB = None

# Optional: maximum number of detail rows to write (None = all)
MAX_DETAIL_ROWS = None

KEYWORD_GROUPS: Dict[str, List[str]] = {
    "Critical Errors": [
        "error",
        "exception",
        "fatal",
        "failed",
        "failure",
        "panic",
        "crash",
        "abort",
    ],
    "Warnings": [
        "warn",
        "warning",
        "deprecated",
        "unstable",
        "retry",
        "fallback",
    ],
    "Data Issues": [
        "invalid",
        "null",
        "undefined",
        "missing",
        "empty",
        "unexpected",
        "out of range",
        "not found",
    ],
    "Permission Issues": [
        "denied",
        "unauthorized",
        "forbidden",
        "permission",
        "authentication",
        "token expired",
    ],
    "System Issues": [
        "timeout",
        "unavailable",
        "overload",
        "connection refused",
        "connection reset",
        "disk full",
        "memory",
    ],
    "Logic Issues": [
        "unexpected",
        "inconsistent",
        "corrupt",
        "duplicate",
        "conflict",
    ],
}


@dataclass
class FileStats:
    total_lines: int = 0
    matched_lines: int = 0
    unreadable: bool = False
    error_message: str = ""


def build_output_dir() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = REPORTS_ROOT / f"log_scan_report_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def should_skip_dir(path: Path) -> bool:
    return path.name.lower() in {d.lower() for d in SKIP_DIR_NAMES}


def is_allowed_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in ALLOWED_EXTENSIONS


def is_file_too_large(path: Path) -> bool:
    if MAX_FILE_SIZE_MB is None:
        return False
    try:
        size_bytes = path.stat().st_size
        return size_bytes > MAX_FILE_SIZE_MB * 1024 * 1024
    except OSError:
        return False


def compile_keyword_patterns(
    keyword_groups: Dict[str, List[str]]
) -> Tuple[Dict[str, List[str]], Dict[str, re.Pattern]]:
    keyword_to_groups: Dict[str, List[str]] = defaultdict(list)

    for group_name, keywords in keyword_groups.items():
        for keyword in keywords:
            normalized = keyword.strip().lower()
            keyword_to_groups[normalized].append(group_name)

    keyword_patterns: Dict[str, re.Pattern] = {}

    for keyword in keyword_to_groups.keys():
        escaped = re.escape(keyword)
        if " " not in keyword and "-" not in keyword:
            pattern = re.compile(rf"\b{escaped}\b", re.IGNORECASE)
        else:
            pattern = re.compile(escaped, re.IGNORECASE)
        keyword_patterns[keyword] = pattern

    return keyword_to_groups, keyword_patterns


def discover_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if path.is_dir() and should_skip_dir(path):
            continue
        if is_allowed_file(path):
            if not any(part.lower() in {d.lower() for d in SKIP_DIR_NAMES} for part in path.parts):
                yield path


def safe_open_text_file(path: Path):
    encodings = ("utf-8", "utf-8-sig", "cp1252", "latin-1")
    last_error = None

    for encoding in encodings:
        try:
            return open(path, "r", encoding=encoding, errors="ignore")
        except Exception as exc:
            last_error = exc

    raise last_error if last_error else OSError(f"Unable to open file: {path}")


def write_csv(path: Path, headers: List[str], rows: Iterable[Dict[str, object]]) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def print_console_block(title: str, items: Iterable[Tuple[str, int]], limit: int = 15) -> None:
    print(f"\n{title}")
    print("-" * len(title))
    for i, (name, count) in enumerate(items):
        if i >= limit:
            break
        print(f"{name}: {count}")


def main() -> int:
    if not LOG_FOLDER.exists():
        print(f"[ERROR] Log folder does not exist: {LOG_FOLDER}")
        return 1

    output_dir = build_output_dir()

    keyword_to_groups, keyword_patterns = compile_keyword_patterns(KEYWORD_GROUPS)
    all_keywords = sorted(keyword_patterns.keys())

    total_group_counts: Counter = Counter()
    total_keyword_counts: Counter = Counter()

    file_group_counts: Dict[str, Counter] = defaultdict(Counter)
    file_keyword_counts: Dict[str, Counter] = defaultdict(Counter)
    file_stats: Dict[str, FileStats] = {}

    detail_rows: List[Dict[str, object]] = []
    unreadable_rows: List[Dict[str, object]] = []

    scanned_files = 0
    skipped_large_files = 0

    files = list(discover_files(LOG_FOLDER))

    for file_path in files:
        file_str = str(file_path)
        file_stats[file_str] = FileStats()

        if is_file_too_large(file_path):
            skipped_large_files += 1
            unreadable_rows.append({
                "file_path": file_str,
                "error": f"Skipped because file is larger than {MAX_FILE_SIZE_MB} MB",
            })
            continue

        scanned_files += 1

        try:
            with safe_open_text_file(file_path) as f:
                for line_number, raw_line in enumerate(f, start=1):
                    line = raw_line.rstrip("\n")
                    file_stats[file_str].total_lines += 1

                    matched_keywords: Set[str] = set()
                    matched_groups: Set[str] = set()

                    for keyword, pattern in keyword_patterns.items():
                        if pattern.search(line):
                            matched_keywords.add(keyword)
                            for group_name in keyword_to_groups[keyword]:
                                matched_groups.add(group_name)

                    if not matched_keywords:
                        continue

                    file_stats[file_str].matched_lines += 1

                    for keyword in matched_keywords:
                        file_keyword_counts[file_str][keyword] += 1
                        total_keyword_counts[keyword] += 1

                    for group_name in matched_groups:
                        file_group_counts[file_str][group_name] += 1
                        total_group_counts[group_name] += 1

                    if MAX_DETAIL_ROWS is None or len(detail_rows) < MAX_DETAIL_ROWS:
                        detail_rows.append({
                            "file_path": file_str,
                            "line_number": line_number,
                            "matched_groups": "; ".join(sorted(matched_groups)),
                            "matched_keywords": "; ".join(sorted(matched_keywords)),
                            "line_text": line,
                        })

        except Exception as exc:
            file_stats[file_str].unreadable = True
            file_stats[file_str].error_message = str(exc)
            unreadable_rows.append({
                "file_path": file_str,
                "error": str(exc),
            })

    file_summary_headers = [
        "file_path",
        "total_lines",
        "matched_lines",
        "match_rate_percent",
    ]
    file_summary_headers += [f"group::{group}" for group in KEYWORD_GROUPS.keys()]
    file_summary_headers += [f"keyword::{keyword}" for keyword in all_keywords]

    file_summary_rows = []

    total_lines_all = sum(stats.total_lines for stats in file_stats.values())
    total_matched_lines_all = sum(stats.matched_lines for stats in file_stats.values())
    total_row = {
        "file_path": "__TOTAL__",
        "total_lines": total_lines_all,
        "matched_lines": total_matched_lines_all,
        "match_rate_percent": round(
            (total_matched_lines_all / total_lines_all * 100), 2
        ) if total_lines_all else 0.0,
    }
    for group in KEYWORD_GROUPS.keys():
        total_row[f"group::{group}"] = total_group_counts[group]
    for keyword in all_keywords:
        total_row[f"keyword::{keyword}"] = total_keyword_counts[keyword]
    file_summary_rows.append(total_row)

    for file_path in sorted(file_stats.keys()):
        stats = file_stats[file_path]
        row = {
            "file_path": file_path,
            "total_lines": stats.total_lines,
            "matched_lines": stats.matched_lines,
            "match_rate_percent": round(
                (stats.matched_lines / stats.total_lines * 100), 2
            ) if stats.total_lines else 0.0,
        }
        for group in KEYWORD_GROUPS.keys():
            row[f"group::{group}"] = file_group_counts[file_path][group]
        for keyword in all_keywords:
            row[f"keyword::{keyword}"] = file_keyword_counts[file_path][keyword]
        file_summary_rows.append(row)

    write_csv(output_dir / "file_summary.csv", file_summary_headers, file_summary_rows)
    write_csv(
        output_dir / "details.csv",
        ["file_path", "line_number", "matched_groups", "matched_keywords", "line_text"],
        detail_rows,
    )
    write_csv(
        output_dir / "keyword_totals.csv",
        ["keyword", "count"],
        [{"keyword": keyword, "count": total_keyword_counts[keyword]}
         for keyword in sorted(all_keywords, key=lambda k: (-total_keyword_counts[k], k))],
    )
    write_csv(
        output_dir / "group_totals.csv",
        ["group_name", "count"],
        [{"group_name": group, "count": total_group_counts[group]}
         for group in sorted(KEYWORD_GROUPS.keys(), key=lambda g: (-total_group_counts[g], g))],
    )

    top_file_rows = []
    for file_path, stats in file_stats.items():
        total_group_hits = sum(file_group_counts[file_path].values())
        total_keyword_hits = sum(file_keyword_counts[file_path].values())
        top_file_rows.append({
            "file_path": file_path,
            "total_lines": stats.total_lines,
            "matched_lines": stats.matched_lines,
            "group_hits_total": total_group_hits,
            "keyword_hits_total": total_keyword_hits,
            "critical_errors": file_group_counts[file_path]["Critical Errors"],
            "warnings": file_group_counts[file_path]["Warnings"],
            "system_issues": file_group_counts[file_path]["System Issues"],
            "match_rate_percent": round(
                (stats.matched_lines / stats.total_lines * 100), 2
            ) if stats.total_lines else 0.0,
        })

    top_file_rows.sort(
        key=lambda r: (
            -int(r["critical_errors"]),
            -int(r["keyword_hits_total"]),
            -int(r["matched_lines"]),
            str(r["file_path"]).lower(),
        )
    )

    write_csv(
        output_dir / "top_files.csv",
        [
            "file_path",
            "total_lines",
            "matched_lines",
            "group_hits_total",
            "keyword_hits_total",
            "critical_errors",
            "warnings",
            "system_issues",
            "match_rate_percent",
        ],
        top_file_rows,
    )

    if unreadable_rows:
        write_csv(output_dir / "unreadable_files.csv", ["file_path", "error"], unreadable_rows)

    print("=" * 72)
    print("LOG SCAN COMPLETED")
    print("=" * 72)
    print(f"Root folder: {LOG_FOLDER.resolve()}")
    print(f"Output folder: {output_dir.resolve()}")
    print(f"Discovered files: {len(files)}")
    print(f"Scanned files: {scanned_files}")
    print(f"Skipped large files: {skipped_large_files}")
    print(f"Unreadable files: {len(unreadable_rows)}")

    group_items = sorted(total_group_counts.items(), key=lambda x: (-x[1], x[0].lower()))
    keyword_items = sorted(total_keyword_counts.items(), key=lambda x: (-x[1], x[0].lower()))

    print_console_block("Top groups", group_items, limit=20)
    print_console_block("Top keywords", keyword_items, limit=20)

    return 0


if __name__ == "__main__":
    sys.exit(main())
