#!/usr/bin/env python3
"""relnotes — release notes from git history, built on an open-weight model.

Turns a git log into human-readable release notes (changelog) using any
OpenAI-compatible endpoint backed by an open-weight model (Ollama, LM Studio,
llama.cpp server, vLLM, ...). Falls back to a deterministic template when no
model endpoint is configured, so the tool never breaks a release pipeline.

Part of the Hacktoberfest Open-Source AI Challenge: Week 2 (Side Hustle).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

__version__ = "0.1.0"

DEFAULT_BASE_URL = "http://127.0.0.1:11434/v1"  # Ollama's OpenAI-compatible API
DEFAULT_MODEL = "qwen2.5:3b"

SYSTEM_PROMPT = (
    "You are a release-notes writer. You rewrite raw git commits into a short, "
    "plain-English changelog for end users. Rules: group under Added / Fixed / "
    "Changed; one bullet per commit, max 12 words each, no commit hashes, no "
    "file names, no jargon like 'refactor' or 'chore'; skip merge commits; if a "
    "commit is uninformative, drop it. Output markdown bullets only."
)

CONVENTIONAL = re.compile(
    r"^(?P<type>feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)"
    r"(?:\((?P<scope>[^)]+)\))?!?:\s*(?P<subject>.+)$"
)

TYPE_TO_SECTION = {
    "feat": "Added",
    "fix": "Fixed",
    "perf": "Changed",
    "refactor": "Changed",
    "docs": "Changed",
    "build": "Changed",
    "ci": "Changed",
    "style": "Changed",
    "test": "Changed",
    "chore": "Changed",
    "revert": "Fixed",
}


@dataclass
class Commit:
    sha: str
    subject: str
    body: str = ""
    section: str = "Changed"
    text: str = ""

    @classmethod
    def parse(cls, raw: str) -> "Commit | None":
        lines = raw.split("\n")
        if len(lines) < 2:
            return None
        sha, subject = lines[0].strip(), lines[1].strip()
        if not subject or subject.lower().startswith("merge "):
            return None
        body = "\n".join(lines[2:]).strip()
        match = CONVENTIONAL.match(subject)
        if match:
            section = TYPE_TO_SECTION.get(match.group("type"), "Changed")
            text = match.group("subject").strip()
            if match.group("scope"):
                text = f"{match.group('scope')}: {text}"
        else:
            section = "Changed"
            text = subject
        return cls(sha=sha[:7], subject=subject, body=body, section=section, text=text)


@dataclass
class Options:
    base_url: str = os.environ.get("RELNOTES_BASE_URL", DEFAULT_BASE_URL)
    model: str = os.environ.get("RELNOTES_MODEL", DEFAULT_MODEL)
    api_key: str = os.environ.get("RELNOTES_API_KEY", "")
    offline: bool = False
    max_commits: int = 60


def run_git(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        sys.stderr.write(f"relnotes: git {' '.join(args)} failed: {result.stderr.strip()}\n")
        raise SystemExit(result.returncode)
    return result.stdout


def collect_commits(since: str | None, until: str | None) -> list[Commit]:
    range_spec = "HEAD"
    if since:
        range_spec = f"{since}..HEAD" if not until else f"{since}..{until}"
    elif until:
        range_spec = until
    log = run_git(
        ["log", range_spec, "--no-merges", "--pretty=format:%H%n%s%n%b%n==END=="]
    )
    commits = []
    for block in log.split("==END=="):
        commit = Commit.parse(block.strip("\n"))
        if commit:
            commits.append(commit)
    return commits


def _post_chat(base_url: str, model: str, api_key: str, messages: list[dict]) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    payload = json.dumps({"model": model, "messages": messages, "temperature": 0.3}).encode()
    request = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    if api_key:
        request.add_header("Authorization", f"Bearer {api_key}")
    with urllib.request.urlopen(request, timeout=120) as response:
        data = json.loads(response.read().decode())
    return data["choices"][0]["message"]["content"].strip()


def model_available(opts: Options) -> bool:
    try:
        urllib.request.urlopen(opts.base_url.rstrip("/") + "/models", timeout=3)
        return True
    except Exception:
        return False


def render_with_model(commits: list[Commit], opts: Options) -> str:
    digest = "\n".join(f"- [{c.section}] {c.text}" for c in commits)
    try:
        return _post_chat(
            opts.base_url,
            opts.model,
            opts.api_key,
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": digest},
            ],
        )
    except Exception as exc:  # never break a release because a model hiccuped
        sys.stderr.write(f"relnotes: model call failed ({exc}); using offline template\n")
        return render_offline(commits)


def render_offline(commits: list[Commit]) -> str:
    sections: dict[str, list[str]] = {"Added": [], "Fixed": [], "Changed": []}
    for commit in commits:
        sections.setdefault(commit.section, []).append(commit.text)
    blocks = []
    for title in ("Added", "Fixed", "Changed"):
        bullets = sections.get(title) or []
        if bullets:
            rendered = "\n".join(f"- {text}" for text in bullets)
            blocks.append(f"### {title}\n\n{rendered}")
    return "\n\n".join(blocks) if blocks else "_No user-facing changes._"


def render(commits: list[Commit], opts: Options) -> str:
    if not commits:
        return "_No commits in range._"
    if opts.offline or not model_available(opts):
        return render_offline(commits)
    return render_with_model(commits, opts)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="relnotes",
        description="Generate user-facing release notes from git history "
        "using an open-weight model.",
    )
    parser.add_argument("--since", help="start ref, e.g. v1.2.0 or a date")
    parser.add_argument("--until", default="HEAD", help="end ref (default HEAD)")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="skip the model and use the deterministic template",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"OpenAI-compatible endpoint (default {DEFAULT_BASE_URL}, "
        "or set RELNOTES_BASE_URL)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"model name (default {DEFAULT_MODEL}, or set RELNOTES_MODEL)",
    )
    parser.add_argument("-o", "--out", type=Path, help="write to file instead of stdout")
    parser.add_argument("--version", action="version", version=f"relnotes {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    opts = Options(
        base_url=args.base_url,
        model=args.model,
        offline=args.offline,
    )
    commits = collect_commits(args.since, args.until)[: opts.max_commits]
    notes = render(commits, opts)
    if args.out:
        args.out.write_text(notes + "\n", encoding="utf-8")
        sys.stderr.write(f"relnotes: wrote {args.out}\n")
    else:
        print(notes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
