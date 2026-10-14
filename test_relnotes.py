"""Tests for relnotes — no network, no model required."""

import subprocess
import sys
from pathlib import Path

import relnotes

REPO = Path(__file__).resolve().parent


def make_repo(tmp: Path) -> Path:
    repo = tmp / "demo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.dev"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True)
    for subject in (
        "feat(cli): add --since flag",
        "fix: stop crashing on empty repo",
        "Merge branch 'main'",
        "chore: bump version",
        "docs: explain install steps",
    ):
        subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", subject], cwd=repo, check=True)
    return repo


def test_conventional_parsing():
    commit = relnotes.Commit.parse("abc123\nfeat(cli): add --since flag\n\nbody\n==END==")
    assert commit is not None
    assert commit.section == "Added"
    assert commit.text == "cli: add --since flag"
    assert commit.sha == "abc123"


def test_merges_and_empty_skipped():
    assert relnotes.Commit.parse("a\nMerge branch 'main'\n") is None
    assert relnotes.Commit.parse("a\n\nbody\n") is None


def test_offline_template_groups_sections():
    commits = [
        relnotes.Commit.parse(f"{i:040d}\n{subject}\n==END==")
        for i, subject in enumerate(
            ["feat: thing a", "fix: thing b", "docs: thing c"]
        )
    ]
    out = relnotes.render_offline(commits)
    assert "### Added" in out and "- thing a" in out
    assert "### Fixed" in out and "- thing b" in out
    assert "### Changed" in out and "- thing c" in out


def test_cli_end_to_end(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    monkeypatch.chdir(repo)
    rc = relnotes.main(["--offline"])
    assert rc == 0


def test_cli_writes_file(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    monkeypatch.chdir(repo)
    out = tmp_path / "notes.md"
    rc = relnotes.main(["--offline", "-o", str(out)])
    assert rc == 0
    assert "### Added" in out.read_text()
