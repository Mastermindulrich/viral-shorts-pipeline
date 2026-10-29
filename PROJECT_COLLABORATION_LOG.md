# Project collaboration log

This is the shared continuity record for Codex and Claude Code. Read it before work,
append a dated entry after every meaningful change, and commit it with the code.

## 2026-10-29 — Scene validation bug fix

The dashboard reported “No valid complete scenes survived editorial checks” because the
local Ollama editor sometimes proposed an interesting 10–14 second transcript fragment.
The existing strict validator rejected it even when adjacent transcript segments could
form a valid 15–60 second Short.

editorial.py now uses expand_boundaries(). It extends a short proposed boundary only with
adjacent transcript segments inside the allowed section. It accepts the repair only when
the final scene is 15–60 seconds. Evidence quotes, English-language checks, title claims,
payoff scores and the final context audit remain strict.

### Next validation

cd ~/viral-shorts-pipeline
source .venv/bin/activate
python -m unittest discover -s tests -v

Update the Mac from GitHub, then retry the same source. If it still fails, append the
exact rejection text and a minimal transcript fixture before changing policy. Do not
weaken evidence checks simply to force a clip.

### Collaboration protocol

- Read CLAUDE_HANDOFF.md, this log, git log -5 and tests before editing.
- Preserve existing architecture and all user constraints.
- After work, run tests, append what changed and why, record the commit hash, and update
  CLAUDE_HANDOFF.md when behavior or setup changes.
- Never commit data/, OAuth tokens, media, exports or secrets.
- Never reset or overwrite another agent’s commit; inspect and pull first.
- When switching agents, provide the latest commit hash and require both continuity files
  to be read.

## Current next task

Retry the failed source after updating the Mac. Confirm whether boundary expansion yields
valid clips. If it fails again, capture the model’s raw proposal safely in local
diagnostics without media or tokens, add a regression test, and make the smallest fix.
