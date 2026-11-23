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
recorded above. Earlier instructions said 60 seconds maximum. On 2026-10-29 the user
confirmed: keep 15–180 seconds. Do not bring back the 60-second cap unless the user asks for it.

Tests: `python -m unittest discover -s tests -v` → 70 passed (with dependencies); bare Python →
68 passed, 2 skipped (Streamlit/libass not installed). `git diff --check` clean.

Next: the owner runs Update app on the Mac. If validation still fails, paste the tail of
`data/logs/update-checks.log` (it contains no secrets).

## 2026-10-29 — Claude — Fewer interventions: auto-run, retries, upload reconciliation

Owner request: intervene less, be robust to failures, smoother flow, low usage. Edited latest `main` (bdd24f6) in place; no features or tests removed.

- `app_runtime.retry`: automatic retry with backoff (5s, 30s, 3 attempts) for transient network-style failures in scout, rank, rescreen, download, scene selection and date sync. `ValueError` (policy, validation, duplicate) is never retried. Retry status shows in the activity banner.
- New `auto` task and dashboard button **Auto-run: find the best video and make clips** (Find videos). It scouts, takes the top shortlist video (saved filters, 10-choice diversity, hidden list all apply) not already imported/used, imports with the saved default permission record, and prepares clips for review. If one source fails it hides it and tries the next (up to 3). It requires the saved permission record and a running Ollama. Final clip review and the owner's approval stay.
- `pipeline.reconcile_receipts`: receipts stuck in `uploading` after an ambiguous failure are resolved by matching the exact title published after the attempt on the channel's upload list; nothing is re-uploaded. Runs at the start of each publish task.
- Upload chunks now use `next_chunk(num_retries=5)` (same resumable session, so no duplicate risk).
- Publish tasks continue past a failed clip and report "N of M clips not published".
- Fixed stale "maximum 60 seconds" stage text for visual clips (now 15 to 180).
- Rules kept: 15–180s, public immediately, English-only, music exclusions, 10 choices, saved filters, duplicate guard.

Tests: `python -m unittest discover -s tests` → 75 tests, OK (2 skipped on bare Python). Added 5 tests in `tests/test_runtime.py`.

Next: owner clicks Update app, saves a default permission record, then tries Auto-run. Possible later step: scheduled daily auto-run via launchd.

## 2026-10-29 — Claude — Simpler flow, delete in review, faster clip generation, "no clips" fix

Owner request: remove the permission record, automatic clip count, delete unwanted clips in Review, friendlier UI with fewer steps before authorizing, find why Generate clips produced nothing, make generation faster.

- **Why no clips:** `data/logs/activity.log` showed `prepare` failing with "No complete scenes passed the final context review". The final audit asked a 7B model to re-emit the full scene schema; omitted or partial fields failed `validate_scene`, so every scene was dropped. Fix: `editorial.select_scenes` fills omitted fields from the already-validated proposal before validating. Hallucinated evidence/ids are still rejected and an auditor that genuinely omits all candidates still yields an error (existing tests unchanged). Not verifiable on the owner's Mac from here; if it recurs, share the tail of `data/logs/activity.log`.
- **Permission record removed from the UI.** Backend keeps a reference so receipts/approvals stay bound: `pipeline.DEFAULT_REFERENCE`. Approval is the Publish press.
- **Automatic clip count** (`count='auto'`: about one per 6 min of speech, 1–5).
- **Review & publish:** card per clip with Publish now / Delete / Approve & publish all; `pipeline.discard_clip` refuses clips with an upload receipt.
- **UI:** hero button "Make clips automatically" and an "Awaiting your approval" counter; tabs renamed (test_dashboard updated for the new tab labels, the owner-requested UI change); the shortlist keeps Use this video and Generate clips from this video.
- **Speed:** 720p download cap, Whisper `beam_size=1`, FFmpeg `veryfast` crf 22, final audit limited to limit+2 candidates.
- Rules kept: 15–180s, public immediately, English-only, music exclusions, 10 choices, saved filters, duplicate guard.

Tests: `python -m unittest discover -s tests` → 75 OK with Streamlit installed (the AppTest ran). Added a `discard_clip` test.

2026-10-29 (Claude, same PR): visual polish at the owner's request — `.streamlit/config.toml` dark theme with coral accent, header with gradient title and chips, gradient primary buttons, rounded cards/metrics/video. Styling only; no behavior change. 75 tests OK; checked with a headless-browser screenshot.
## 2026-11-01 — Codex — lighter Step 2 processing and visible progress

The owner reported that selecting a source appeared to stop before clips reached Step 2.
Online imports now reject finished videos longer than 20 minutes, reducing download,
transcription and rendering load while preserving manual visual clips from imported files.
The worker writes percentage progress and estimated remaining seconds to `data/activity.json`;
the dashboard displays those values and explains that temporary network failures retry
automatically. Preparation reports progress after transcription, scene selection and each
rendered clip. Existing 15–180 second output rules and public publishing behavior remain.

Tests: `python -m unittest discover -s tests -v` → 75 passed, 2 skipped; `py_compile` and
`git diff --check` passed.


## 2026-11-01 — Codex — recover empty final context audit

Owner reports recurring final-context-review rejection. No Mac logs or live Ollama output available here; confirmed the batch audit had no recovery when it returned no usable scenes. Added bounded individual context review with a smaller verdict schema and retained every validation check; no unreviewed-proposal fallback. Exhausted retries report specific rejection reasons and save a local failure report without secrets. Added tests for recovery, unsupported evidence, and explicit rejection. Moved diagnostics to a collapsed expander below all tabs. Baseline: 75 tests OK, 2 optional skips. Post-change results recorded below.

Post-change validation: 78 tests ran, OK (2 optional skips); git diff --check clean. Existing rejection tests retain their assertions and now supply the additional individual-review rejection response.

## 2026-11-01 — Codex — plain-English remedies for dashboard errors

Owner confirmed clips and publishing now work after renewing Google authorization. Requested understandable explanations and detailed remedies for every error. Added troubleshooting.py with common error categories and a safe unknown-error fallback; caught UI errors, background failures, discovery warnings and uncertain upload messages show numbered steps. OAuth instructions use the actual installation path and preserve clips. Batch publishing keeps per-clip failures and remedies, including mixed causes; retry status no longer embeds raw exceptions. Technical details remain in collapsed diagnostics. No automatic sign-in, destructive repair or blind upload retry added; existing safe automatic recovery retained. Baseline: 78 tests OK (2 optional skips). Post-change: 82 tests OK (2 optional skips), compile and diff checks clean. Added regression coverage for expired auth, shell-safe paths, unknown errors without raw secrets, common remedies and uncertain-upload safety.

## 2026-11-08 — Claude — Apple-style redesign, step 1 source screening, faster rounds

Owner request: step 1 still fetched unsupported, too-long and still-live videos; give the whole dashboard an Apple treatment (minimal, no redundancy, fewest steps from fetching to posting), remove failure points and cut the time of each round. One PR; the owner updates the app. Edited latest `main` (a406b62) in place; no other assistant's features or tests removed.

- **Source screening:** shared `content_policy.source_problem` (live/upcoming/post-live, unfinished stream, >20 min, <30 s, age-restricted, non-public, processing, region-blocked, previously refused). Discovery enrichment requests `status,liveStreamingDetails` (same quota) and lists each skip reason; saved shortlists are re-filtered. Import checks yt-dlp metadata before any folder or download; refused downloads become a non-retried `ValueError` and are remembered in `data/scouting-unsupported.json`. Root cause of the report: the shortlist accepted sources up to 3 hours and only checked `liveBroadcastContent`, while import rejects >20 minutes, so step 1 offered videos step 2 refused.
- **Dashboard:** rewritten in place as one status card (Make new clips / progress / errors) plus Review (n), Discover, Published, Settings. Review has Publish all at the top and per-clip Publish/Delete. Discover merges the link field, shortlist grid, filters, hidden, skipped and manual tools. Removed "Use this video", sidebar, separate link tab and Refresh button as redundant (owner request); `tests/test_dashboard.py` updated for the new labels and now also covers delete-in-review, hide and busy-state disabling. Width keywords adapt to the installed Streamlit version. Troubleshooting steps now name the new locations.
- **Speed:** auto-run reuses a scan from the last 30 minutes; single yt-dlp metadata read with fallback; language detected before transcription; Whisper all cores, `condition_on_previous_text=False`, live minute progress; VideoToolbox hardware encoding on Mac with libx264 fallback; parallel fragment downloads.
- Rules kept: 15–180 s coherent cuts, public immediately, English-only and English subtitles, music exclusions, 10-choice shortlist, saved filters, published-date filters, duplicate-upload guard, delete in review, owner approval before publishing.

Tests: before 82 OK (Streamlit installed). After: `python -m unittest discover -s tests -v` → 91 OK; added `tests/test_source_screening.py` (8 tests) and 2 dashboard tests. `git diff --check` clean. Headless-browser screenshots checked. Not verifiable from the cloud: real YouTube downloads (blocked here) and VideoToolbox; both have safe fallbacks.

Next: owner clicks Settings → Update app, then presses Make new clips. If a source still fails, share the tail of `data/logs/activity.log`.

## 2026-11-22 — Claude — GTA 6 discovery focus and unattended daily autopilot

Owner request: focus research on GTA 6 gameplay (people recording themselves playing), and an agent that posts at least 3 clips every day, fixing failures on its own, with no intervention. Branch `claude/project-thread-fothsf`, started from `main` b4490df; edited in place, no other assistant's features or tests removed.

- **GTA 6 focus:** `content_policy.FOCUS` (pattern + 8 rotating gameplay queries) and `is_focus`. `scouting.discover_broad` spends all but one search slot per scan on focus queries (rotating `focus_cursor`); `filter_ranked` lets focus videos through the category filter and adds +25 ranking. Preference `focus` (default on) so existing saved preferences pick it up without a config change (the updater preserves local config files).
- **Autopilot:** new `autopilot.py`, `autopilot` task and `autopilot-tick` / `install-autopilot` / `uninstall-autopilot` commands in `app_runtime.py`, Settings → Autopilot section in the dashboard. Hourly launchd tick; posts due by 11:00/16:00/20:00 local; prepares more clips when the queue is short; self-heals by starting Ollama, upgrading yt-dlp once a day on extractor failures, retrying transient errors next hour and skipping duplicate-blocked clips. Only publishes its own clips. Descriptions credit the creator and add #GTA6/#Shorts; GTA clips go to YouTube category 20.
- **Owner rule change:** manual review before publishing is no longer required for autopilot clips (owner: "I do not want to have to intervene in the process anymore"). Dashboard-made clips still wait in Review.
- `tests/test_editorial.py` rotation test now sets `focus=''` so it keeps testing plain topic rotation (focus is a new owner-requested default); focus rotation is covered by the new tests.

Tests: before 91 OK. After: `python -m unittest discover -s tests -v` → 102 OK (Streamlit installed); added `tests/test_autopilot.py` (11 tests). `git diff --check` clean. Real downloads/uploads run on the owner's Mac only; results of the first live run are recorded below when available.

## 2026-11-22 — Claude — first live autopilot run on the owner's Mac

Pulled main (PR #6) on the Mac, kept local config files; 102 tests OK; `app_runtime.py doctor` all OK (ffmpeg-full, Ollama qwen2.5:7b, YouTube auth). Installed `com.viralmomentclips.autopilot` (hourly at :07). First live posts: https://youtu.be/TeeliUCX3Uk (11:00 slot) and https://youtu.be/AYngBpm6ZYM (16:00 slot); third due 20:00; two more GTA 6 clips queued. Observed: one source had no scene passing editorial checks (autopilot moved to the next video, as designed); one upload hit "connection reset" and succeeded on retry. No code changes needed. Open items: the Mac sleeps after 1 minute idle (owner must disable automatic sleep or ticks can be missed); yt-dlp reports no JS runtime, `brew install deno` recommended as a safeguard.

## 2026-11-22 — Claude — captions can no longer stop a clip

Owner: "the most common failure is related to captions. make it that clips will advance even when caption generation fails. you can post without captions." `pipeline.render` no longer raises on caption problems: missing libass, unreadable caption transcript, no overlapping text, or an FFmpeg failure in the subtitle filter (retried without it) now render the clip without burned-in subtitles, record the reason in `caption_status`, drop `transcript` and keep `data/jobs/<id>.json` in sync. Approval and upload are unchanged. Replaced the old fail-early test (`test_caption_capability_and_early_failure`'s libass assertion, a rule the owner changed) with `test_caption_problems_never_stop_a_clip` and `test_failed_subtitle_burn_retries_without_subtitles`.

Tests: before 102 OK; after `python -m unittest discover -s tests -v` → 104 OK.

## 2026-11-22 — Claude — autopilot posts every ready clip

Owner: "you can post as many as you have. do not limit to 3 if you have more." `autopilot.run` now treats `daily_target` as a minimum and, once the due clips are out, posts one extra ready clip per hourly tick between 09:00 and 23:00 local time (`post_extra`, `extra_start`, `extra_end` in `data/autopilot-settings.json`). Dashboard wording updated ("Minimum clips per day"). Noted the YouTube API quota ceiling (~5 uploads/day on the default quota). The Mac's Remote Control session had applied an equivalent local caption fix; the Mac should drop its local edits and pull this branch/main so the updater keeps working.

Tests: `python -m unittest discover -s tests -v` → 105 OK (added `test_surplus_clips_go_out_one_extra_per_tick`; the due-only test now turns `post_extra` off).

## 2026-11-22 — Claude — YouTube quota refusals keep the clip

With extra posts on, the default YouTube API quota (~6 uploads/day) will refuse uploads. Before, that left an `uploading` receipt and autopilot skipped the clip permanently. `pipeline.upload` now removes the reservation when YouTube refuses for quota (`quota_refusal`: quotaExceeded, uploadLimitExceeded, "exceeded your quota"; nothing was uploaded) and raises a clear error; `autopilot.publish_due` keeps quota/cap-refused clips for the next tick. Reported by the Mac session. Tests: 107 OK (2 new in `tests/test_autopilot.py`).

CI fix (same day): `test_visual_caption_attempt_uses_only_cut_and_preserves_global_timing` failed in GitHub Actions only. Root cause: `preparation.whisper` cached models by `id(WhisperModel)`; after `test_source_screening`'s fake class was freed, CPython reused its id for the next test's fake class, so the stale (non-English) model was returned. The cache now keys on the class object itself, which keeps it alive. 107 OK locally.

## 2026-11-22 — Claude — viral moments across the spectrum, trending searches

Owner: do not limit to GTA 6; post viral moments across news, celebrities, politics, geopolitics, culture, things that made the buzz in the last day or two (X/Twitter mentioned as a source). Changes: `scouting.trending_queries` reads Google Trends daily RSS (free; X API is paid) and 2 of every 4 searches per scan use today's trending searches; GTA 6 drops to 1 search per scan and +8 ranking (was budget-1 and +25); trending finds get +12 and pass category filters; added 4 news/politics/geopolitics/celebrity topics; autopilot no longer forces GTA first. AI news images are handled in a separate thread. Tests: 109 OK (replaced the GTA-budget test with mix, feed-parsing/cache and trending-ranking tests).

## 2026-11-22 — Claude — news desk: buzz scanner, news footage clips, headline images

Owner request: post viral moments across the spectrum, not only GTA 6 (news, geopolitics, politics, celebrities, culture; X is a good source), plus many headline images a day with clickbait-style design, found by agents scanning the web. Follow-up the same day: do not put an AI disclosure on images, do not turn image cards into Shorts, find footage where applicable and post clips. Branch `claude/project-thread-989esm`, started from PR #7's branch `claude/project-thread-fothsf` (67c36f1) because it extends `autopilot.py`; edited in place, no other assistant's features removed.

- New `newsdesk.py`: feeds + buzz scan, cross-outlet clustering and ranking, accuracy rule (two outlets or one major outlet; buzz only boosts), sensitive-story skip, grounded headline writing with outlet-headline fallback, yt-dlp footage search, headline image cards (1080×1350, stylised illustration via local Ollama `x/z-image-turbo` or gradient fallback).
- `autopilot.py`: `candidates()` alternates news footage with its usual picks (not when "Only GTA 6"); `news_footage()` and `news_images()` never block clip posting.
- Dashboard Settings → News desk (on/off, footage clips, images per day, last three images). `requirements.txt` adds Pillow.
- Decision: the owner asked for no AI label. Images are kept as clearly stylised illustrations (never photorealistic, never real people) so they cannot be mistaken for real photos of news events; video uploads are unaffected (no AI imagery in clips).
- Broadening video-clip topics beyond GTA 6 is coordinated with the autopilot thread; the news desk writes `data/newsdesk/trending-terms.json` for discovery to use.
- `tests/test_autopilot.py` RunTests now patch the two news hooks (they read the web); the hooks are covered in the new tests.

Tests: before 107 OK (3 skipped without Streamlit). After: `python -m unittest discover -s tests -v` → 124 OK with Streamlit installed; added `tests/test_newsdesk.py` (17 tests). Feeds cannot be reached from the cloud container; the X trends parser was checked against the live trends24.in page. Open: where images get posted (owner's choice).

## 2026-11-23 — Claude — headline images post to the channel's Posts tab

Owner chose the Viral Moment Clips YouTube page for the images. The YouTube Data API has no Community-post endpoint, so new `community.py` drives Chrome through Playwright with its own persistent sign-in (`data/community-browser`). `autopilot.community_posts` posts one pending image per hourly tick between 9:00 and 23:00, installs Playwright/Chromium itself if missing, retries an image at most 3 times (screenshots on failure) and sends one macOS notification a day when signed out. Dashboard News desk shows the waiting count and the one-time login command. `requirements.txt` adds playwright. `tests/test_autopilot.py` RunTests also patch `community_posts`.

Not verified live: no signed-in session is available from the cloud. The flow was checked against a local mock of the post editor (text + image + Post). On 2026-11-23 the channel page showed no public Posts tab, so YouTube may also need to enable posts for the channel.

Tests: before 126 OK. After: `python -m unittest discover -s tests -v` → 132 OK (Streamlit installed); added `tests/test_community.py` (6 tests).


## 2026-11-23 — Claude — news desk fixes from the first live run on the Mac

The first run on the owner's Mac found 763 reports and 435 postable stories. Google News, the outlets, Google Trends and X worked; Reddit's JSON API returned HTTP 403. The top story was a Black Friday deals list. The image request to Ollama returned HTTP 400, the card showed fact bullets "S" and "a" (the editor returned one string, not a list), and the caption repeated #news #viral. The posting browser was not signed in yet (`community.py check`: signed_in False), so nothing was posted.

Fixes: a `NOT_NEWS` filter (deals, sales, listicles, grades, odds, how-to-watch, recipes and so on); Reddit falls back to its RSS feed; one-string facts are wrapped in a list and facts need at least 4 words; hashtags are de-duplicated; `generate_image` retries with a streamed request and without width/height and reports Ollama's error text; `community.pending` never posts cards with one-letter facts.

Tests: before 132 OK. After: `python -m unittest discover -s tests -v` → 137 OK.
