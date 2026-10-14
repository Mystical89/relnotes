---
name: relnotes
description: "Generate user-facing release notes / changelog from git history using an open-weight model (Ollama or any OpenAI-compatible endpoint). Use when preparing a release, tagging a version, or writing changelog entries."
version: 0.1.0
license: MIT
metadata:
  hermes:
    tags: [release-notes, changelog, git, open-weight-model, hacktoberfest]
---

# relnotes

Turn a git log into a human-readable changelog. Open-weight model first,
deterministic fallback so a release never breaks.

## When to use

- Before tagging a release, when the user asks for release notes or a changelog
- When asked to "summarize what changed since <ref>"

## Run it

```bash
# Offline template — always safe, no model needed
~/.devrelay/bin/../projects/relnotes/relnotes.py --since v1.2.0 --offline

# With a local open-weight model
python3 relnotes.py --since v1.2.0

# Into the actual file
python3 relnotes.py --since v1.2.0 -o RELEASE_NOTES.md
```

## Pitfalls

- **Always pass `--since`.** Without it the whole history is summarised.
- **`--offline` first when unsure.** The model call has a 120 s timeout and a
  fallback, but offline is instant and never surprises a pipeline.
- **Never invent notes.** Output comes from real commits; if the range is
  empty the tool prints `_No commits in range._` — don't paper over that.
- The model groups and shortens; it does not add features that aren't in the
  log. If a user asks for a specific entry that isn't there, say so.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `RELNOTES_BASE_URL` | `http://127.0.0.1:11434/v1` | OpenAI-compatible endpoint |
| `RELNOTES_MODEL` | `qwen2.5:3b` | Model name |
| `RELNOTES_API_KEY` | *(unset)* | For endpoints that require a key |
