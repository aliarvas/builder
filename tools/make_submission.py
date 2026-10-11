#!/usr/bin/env python3
"""T-049: write submission.json for the final.

    python3 tools/make_submission.py --team "Team" --member "Name <mail@example.com>" \
        --repo https://github.com/team/builder --mock-url https://mock.workers.dev

The commit is the repository's HEAD. The workflow and trace paths are the ones the final build
writes with ``--slot final``; the script warns when they are missing, or when the working tree
has uncommitted changes (the commit would then not be what ran).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN_COMMAND = "python3 builder/build.py --slot final {case_folder} {mock_url}"
WORKFLOW = "submission/final.workflow.json"
TRACE = "traces/final.log"


def member(text: str) -> dict[str, str]:
    match = re.fullmatch(r"\s*(.+?)\s*<\s*([^<>\s]+@[^<>\s]+)\s*>\s*", text)
    if not match:
        raise argparse.ArgumentTypeError(f"member must look like 'Name <mail@example.com>': {text!r}")
    return {"name": match.group(1), "email": match.group(2)}


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write submission.json for the final.")
    parser.add_argument("--team", required=True)
    parser.add_argument("--member", dest="members", type=member, action="append", required=True,
                        help="'Name <mail@example.com>'; repeat for each member")
    parser.add_argument("--repo", required=True, help="repository URL")
    parser.add_argument("--mock-url", required=True, help="the deployed mock (https://...)")
    parser.add_argument("--commit", help="defaults to git HEAD")
    parser.add_argument("--out", default="submission.json")
    args = parser.parse_args(argv)

    if not re.match(r"https://", args.mock_url):
        parser.error("--mock-url must start with https://")
    commit = args.commit or git("rev-parse", "HEAD")
    data = {
        "team": args.team,
        "members": args.members,
        "repo": args.repo,
        "commit": commit,
        "run_command": RUN_COMMAND,
        "workflow": WORKFLOW,
        "trace": TRACE,
        "mock_url": args.mock_url.rstrip("/"),
    }
    out = ROOT / args.out
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out}")

    warnings = []
    for path in (WORKFLOW, TRACE):
        if not (ROOT / path).exists():
            warnings.append(f"{path} does not exist yet")
    try:
        dirty = git("status", "--porcelain", "--", "builder", "tools")
        if dirty:
            warnings.append("builder/ or tools/ has uncommitted changes: commit them, then run this again so "
                            "the commit is the code that ran")
        if not args.commit and git("rev-parse", "HEAD") != commit:
            warnings.append("HEAD moved while writing")
    except subprocess.CalledProcessError as exc:
        warnings.append(f"git check failed: {exc}")
    trace = ROOT / TRACE
    if trace.exists():
        text = trace.read_text(encoding="utf-8", errors="replace")
        if re.search(r"(?m)^status: (?!ok)", text):
            warnings.append(f"{TRACE} does not end with status ok")
        if args.mock_url.rstrip("/") not in text:
            warnings.append(f"{TRACE} does not mention the mock URL {args.mock_url}")
    for warning in warnings:
        print("warning: " + warning, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
