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

## 2026-10-29 — User changed duration policy

The user explicitly removed the former 60-second cap. New clips may be 15–180 seconds.
The selection goal is now a coherent, self-contained and interesting single cut; the
editor should prefer the shortest complete version and must not cut off a payoff merely
to satisfy one minute. The 180-second ceiling remains for practical short-form rendering.
All validation, dashboard language, prompts, tests, README and Claude handoff must use
this rule. Existing published videos are unchanged. Run all tests after this change.

## 2026-10-29 — Claude — earlier takeover work (PR #1, merged as 8e0f531, code in 18f1eb0)

Recorded here for continuity (it predates this log):
- Cross-batch duplicate-upload guard: `pipeline.upload_conflicts`, `describe_conflicts` and
  `overlap_ratio`. Upload is blocked when an earlier receipt (uploaded or uncertain) has the same
  source and overlaps at least 50% of the shorter clip, or the approved bytes are identical.
  Receipts also store `source_url/start/end`. Review & publish shows a warning.
- A batch publish continues past a blocked clip and reports "N of M clips not published".
- `app_runtime.readiness()`, `python app_runtime.py doctor`, the Mac setup check in Activity &
  settings, and `editorial.require_model()` as a fail-fast check before `prepare` downloads anything.
- `Install-Mac.command` creates `.venv`. The repo's default upload limit is 20. The dashboard
  survives a missing `clip.mp4`. Added `tests/test_dashboard.py` (Streamlit AppTest); CI installs
  `requirements.txt`.
- Tests: 69 passed. CI green.

## 2026-10-29 — Claude — diagnosis and fix of the updater validation failure

Diagnosis: the Mac updater runs the full suite and rolls back on any failure. Reproduced on
`main` at `e89ca0c`: 70 tests ran, with 13 errors and 2 failures. Every failure came from
the tests added in PR #1 (dashboard, readiness, upload guard, batch publish). Cause: commit
`392b3fa` (180-second policy) and commit `4695dff` (boundary expansion) were written from file
copies older than PR #1. They therefore removed `upload_conflicts`/`describe_conflicts`/
`overlap_ratio` and the receipt fields from `pipeline.py`, and removed `readiness`/
`readiness_report`/`doctor`, the `require_model` check and the batch-continue logic from
`app_runtime.py`. They also removed `OLLAMA`/`check_model`/`installed_models`/`require_model`
from `editorial.py`, and removed the setup check, the editor warning, the missing-clip guard and
the duplicate warning from `dashboard.py`. The README and handoff sections were removed too.
The tests stayed, so the suite failed.

Note: the copy of `data/logs/update-checks.log` that reached the project files is an older
snapshot (54 tests, OK). The failure was therefore diagnosed by reproducing it on `main`.

Fix (no tests changed, deleted or skipped): restored the removed code from `18f1eb0`, kept every
Codex change (`MAX_CLIP_SECONDS=180`, the 15–180s prompts and validation, `expand_boundaries`,
the version bumps, the 180s dashboard text and the f-string messages), and restored the README
and handoff sections, with the duration text adapted to 180s. The handoff now has a
section 0 rule: pull the latest `main` and edit in place; never paste an older file copy over
another assistant's work. Added `AGENTS.md` and `CLAUDE.md` pointers to both continuity files.

Duration rule: the code and docs now consistently use 15–180 seconds, per the user's change
recorded above. Earlier instructions said 60 seconds maximum. The user was asked to confirm
which one stands, and this rule should not change again without that confirmation.

Tests: `python -m unittest discover -s tests -v` → 70 passed (with dependencies); bare Python →
68 passed, 2 skipped (Streamlit/libass not installed). `git diff --check` clean.

Next: the owner runs Update app on the Mac. If validation still fails, paste the tail of
`data/logs/update-checks.log` (it contains no secrets).
