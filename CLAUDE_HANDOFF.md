# Viral Moment Clips — Shared Handoff (Claude and Codex/ChatGPT)

Updated: 2026-10-29 (America/Toronto)
Canonical repository: `https://github.com/Mastermindulrich/viral-shorts-pipeline`
Canonical GitHub branch: `main`
Last recorded state: see the newest entry in `PROJECT_COLLABORATION_LOG.md`.

## 0. Start here — rules for every AI assistant

The owner (Ulrich) switches between Claude and Codex/ChatGPT on this repository. Two files are the shared memory: this handoff (current state and rules) and `PROJECT_COLLABORATION_LOG.md` (dated chronology: what changed, why, tests). `AGENTS.md` and `CLAUDE.md` point both tools here. Each assistant, in every session:

1. Read this file, then `PROJECT_COLLABORATION_LOG.md`, then `git log -5`.
2. Run `python -m unittest discover -s tests -v` before editing and record the result.
3. **Never remove or rewrite another assistant's features while editing nearby code.** Start from the latest `main` (pull first) and edit in place; do not paste in an older copy of a file. A failing test written by the other assistant describes required behavior: fix the code, not the test, unless the owner changed that rule.
4. Keep every rule in section 2 and the workflow in section 3.
5. In the same commit or PR as any change: append a dated entry to `PROJECT_COLLABORATION_LOG.md` (assistant, commit/PR, what changed, decisions and why, tests run and results) and update any section here whose facts changed.
6. Commit only when the complete suite passes. Never commit secrets, OAuth tokens or `data/`.

## 1. Product goal

This project is a local macOS application for operating the user's YouTube Shorts channel, **Viral Moment Clips**. It discovers recent YouTube videos, identifies strong short-form moments, creates vertical clips with original audio, helps the owner review them, and uploads approved clips to YouTube.

The channel targets English-speaking viewers. The user wants high-interest, recent, newsworthy and unofficial-looking moments whenever possible:

- Champions League and football/soccer moments
- major sports people and truly viral sports moments
- sports controversies and apologies, such as an athlete addressing a controversy
- influencers and influencer lifestyle moments
- streamers and gaming personalities
- surprising incidents and things that just happened
- hot interviews, debates and revealing conversations
- African urban dance, amapiano, afrobeats, azonto and TikTok dance challenges
- movie trailers and short movie/fan cuts
- engineering hacks, inventions, mechanisms and clever demonstrations
- sexy/celebrity viral footage, red carpets, paparazzi, fashion and premieres
- music reactions are allowed

Standalone official artist music videos/audio are excluded. Music-category uploads are also screened out unless the title and metadata clearly indicate an allowed reaction, interview, trailer or visual dance format. This is heuristic metadata screening, not a verified copyright or ownership system.

The user prefers unofficial/independent uploads because they often perform better as Shorts, but the app must treat independent status as an estimate. It must not claim that a channel is unofficial merely from weak metadata clues.

The user wants minimal input, but final review and the user's external permission/licensing decision remain explicit. The app records a permission reference; it does not verify rights.

## 2. Non-negotiable content rules

- The former 60-second cap is removed. New clips are 15–180 seconds, with the shortest coherent self-contained cut preferred. The 180-second ceiling is checked in validation, rendering, approval and upload, including measured media duration.
- Automatically edited dialogue must be English. High-confidence non-English transcription blocks automatic dialogue editing.
- Visual dance, sports action and other silent/visual moments can be selected manually.
- Original audio is preserved. There is no narration or synthetic voice.
- Titles, descriptions and explanations are written in English.
- Clips must have a coherent opening/setup and a complete payoff. Avoid mid-sentence cuts, ads, intros, topic changes, context-dependent fragments and unsupported claims.
- Videos are uploaded with `privacyStatus=public` immediately after approval. YouTube processing can still delay playback.
- The app verifies the expected YouTube channel before upload. Expected channel name is Viral Moment Clips; expected ID is `UC66Gf5TgUNxGHM7DbPUqrSw`.
- Upload attempts reserve a receipt before network upload to avoid automatic duplicate retries after ambiguous failures.
- Cross-job duplicate guard: upload is refused when any earlier receipt (uploaded or uncertain) has the same `source_url` and overlaps at least 50% of the shorter clip, or its approved video bytes are identical (`pipeline.upload_conflicts`). New receipts also store `source_url`, `start` and `end`. Review & publish shows these as warnings, and a multi-clip publish continues past a blocked clip, then reports "N of M clips not published".
- Daily upload attempt limit is stored in `config/settings.json` and currently defaults to 20 UTC-day attempts.

## 3. Current user workflow

The dashboard tabs are:

1. **Find videos**
2. **Make clips**
3. **Review & publish**
4. **Published**
5. **Activity & settings**

### Find videos

A scan searches rotating categories/event queries, recent YouTube search results and popular charts, enriches candidate metadata, screens out disallowed releases and ranks remaining candidates. The dashboard displays up to **10 choices per round**, with a maximum of two choices from the same channel and duplicate-title suppression.

Default saved discovery settings:

- uploaded within the last 3 days
- at least 5,000 source views
- at least 200 source views per hour
- prefer independent/unverified-looking sources
- all current policy topics unless the user narrows them

The user can save:

- categories
- 1/3/7/30-day freshness window
- minimum source views
- minimum views/hour
- source preference: Prefer independent / Any source / Exclude likely official
- specific event queries, one per line
- required keywords
- excluded keywords
- blocked exact channel names or IDs

The app distinguishes measured growth from lifetime average. Measured momentum requires at least two observations separated by 15 minutes; before that, the UI labels the signal as a lifetime average. Ranking combines momentum or average velocity, freshness, engagement, source-relative performance and event-language signals.

The shortlist can contain fewer than 10 items if fewer meet the filters. Do not fill it with weak videos merely to reach 10.

`Use this video` always remains enabled while background work runs. `Generate clips from this video` can launch directly when a saved default permission reference exists; otherwise the user enters a reference in Make clips.

`Hide this video` persists by video ID in `data/scouting-hidden.json` and removes it from later scans. Hidden items can be restored.

### Make clips

The user may start from a YouTube link or an already imported video.

For an online source, the user provides a permission/clearance reference. The app downloads a single YouTube video through yt-dlp, rejects live videos and sources over three hours, checks content policy, and stores an import receipt under `data/imports/`.

Automatic preparation:

1. transcribe with local faster-whisper
2. use word timestamps where available
3. map topics over the full transcript
4. propose complete 15–180 second scenes
5. rank distinct scenes
6. run a second context-audit pass against surrounding dialogue
7. validate evidence quotes, numbers, title claims, language, boundaries, payoff and non-overlap
8. render vertical previews
9. place jobs in the review queue

Default transcription model is `small`; `base`, `small` and `medium` are selectable. The local editorial model is Ollama `qwen2.5:7b`. It is called through `http://127.0.0.1:11434/api/chat` and must be installed locally. Cloud models are deliberately rejected.

Manual visual path:

`Make clips → Already imported video → Choose a visual moment manually`

The user previews the source and enters start/end seconds, an English title and a 1–180 second duration. The app attempts English transcription only on that selected interval for subtitles. It cannot visually verify a goal, stunt, facial expression or engineering demonstration, so the preview must be checked.

### Subtitles

English subtitles are enabled by default for new automated batches. Word-timed captions are preferred. A caption source/SRT is retained for each draft. If FFmpeg lacks the `subtitles`/libass filter, the app keeps an English SRT file, labels the job as “English SRT available; subtitles not burned in,” and does not pretend subtitles were burned into the MP4.

For burned-in subtitles on the user's Mac:

```bash
brew install ffmpeg-full
```

The app checks the Homebrew keg-only paths `/opt/homebrew/opt/ffmpeg-full/bin` and `/usr/local/opt/ffmpeg-full/bin` automatically. Existing exports are never silently rewritten.

### Review & publish

Every job remains in review until the user:

- watches the actual preview
- checks the title and description
- confirms audience setting
- enters/keeps the permission reference
- confirms the clip is English dialogue or understandable visual footage
- clicks **Approve & publish now**, or saves as ready and later publishes one or more jobs

The approval is bound to exact job metadata and exported video bytes. A changed title, metadata or video invalidates approval.

The user wants the fewest steps possible, so “Approve & publish now” is the preferred path. Publishing uses public visibility immediately.

### Published

Published history is app-produced uploads, not every video on the channel. It supports:

- Today
- Choose a day
- Month
- Year
- All dates
- title search

Default timezone is `America/Toronto`; it can be changed in Activity & settings. New receipts save upload and YouTube publication timestamps. **Refresh publication dates from YouTube** backfills exact timestamps and current recorded visibility for older receipts without retrying or modifying uploads. Legacy receipts remain labelled as legacy UTC dates until backfilled.

## 4. Repository architecture

- `dashboard.py` — primary Streamlit guided UI and workflow tabs
- `dashboard_legacy.py` — retained manual fallback dashboard
- `pipeline.py` — validation, FFmpeg rendering, captions, approval hashes, YouTube OAuth upload, channel guard, upload receipts, recent upload helpers
- `content_policy.py` — English/180-second/music exclusion policy, topic overlays and source classification estimate
- `scouting.py` — discovery, rotating searches, enrichment, momentum ranking, saved filters, shortlist diversity, hidden IDs and exclusions
- `editorial.py` — local Ollama semantic scene selection, topic map, ranking and final context audit
- `preparation.py` — yt-dlp import, faster-whisper transcription, SRT/caption preparation, semantic draft generation and visual caption attempt
- `studio.py` — saved production preferences and date/time filtering for publishing history; YouTube timestamp backfill
- `app_runtime.py` — durable background task state, process submission, logs, update flow, launchd installation and diagnostics
- `worker.py` — older/local worker functionality retained for compatibility
- `config/discovery.json` — base discovery settings; updater preserves local JSON configuration
- `config/settings.json` — channel guard and daily upload limit
- `requirements.txt` — dashboard/upload dependencies
- `requirements-preparation.txt` — yt-dlp and faster-whisper
- `tests/` — unit, integration and Streamlit AppTest coverage (`tests/test_dashboard.py`)
- `Install-Mac.command` — one-time Mac installation
- `Launch.command` — launcher helper
- `README.md` — user-facing operating guide

Runtime data is under `data/` and should remain ignored by Git: OAuth secrets, token files, imported media, transcripts, jobs, exports, approvals, receipts, logs, saved discovery preferences, hidden videos and publication history.

## 5. Background task behavior

The dashboard starts a separate local worker process for `scout`, `rescreen`, `import`, `prepare`, `visual`, `publish`, `sync_history` and `update`. `data/activity.json` records status and stage. `data/logs/activity.log` records output. The UI fragment refreshes every three seconds and releases/re-enables controls when work completes.

The app cannot process while the Mac is asleep. Ollama must be running for semantic selection. No unattended daily ingestion is currently enabled; scouting is on demand.

Resilience (2026-10-29): network-bound tasks retry automatically (`app_runtime.retry`, never for `ValueError`). The `auto` task / **Auto-run** button scouts, picks the top unused shortlist video, imports it with the saved default permission record and prepares clips for review. `pipeline.reconcile_receipts` resolves `uploading` receipts by exact title match before each publish. Publishing a batch continues past failed clips.

## 6. Mac installation and update

The actual installed Mac project is normally `~/viral-shorts-pipeline`. The Finder app is `~/Applications/Viral Moment Clips.app`. launchd label is `com.viralmomentclips.dashboard`. Dashboard is `http://127.0.0.1:8501`.

One-time setup on the Mac:

```bash
git clone https://github.com/Mastermindulrich/viral-shorts-pipeline.git
cd viral-shorts-pipeline
bash Install-Mac.command
```

For an existing install:

1. Open the Finder app.
2. Open **Activity & settings**.
3. Click **Update app**.
4. Wait for dependency installation, tests and service restart.
5. Refresh the dashboard.

The updater fetches the upstream, accepts only a fast-forward update, preserves local JSON configuration, installs requirements, runs `python -m unittest discover -s tests -v`, and rolls back code on failure. It does not fully roll back dependency changes. Local code edits stop the updater to prevent overwriting work.

## 7. Ollama requirements and what Claude can/cannot take over

Claude can read and modify the repository after GitHub is connected, but GitHub access does **not** reproduce the user's Mac runtime. Claude will not automatically inherit:

- the Mac Python virtual environment
- FFmpeg installation
- the running Streamlit launchd service
- Ollama or the `qwen2.5:7b` model
- YouTube OAuth credentials in `data/secrets/token.json`
- local imported videos, transcripts, jobs, exports or receipts
- the user's local browser state

Claude can take over repository development immediately after connecting GitHub, because the code and this handoff are in the repository. To run the complete local pipeline on the Mac, Ollama and the local dependencies still need to be present. Claude Code can use the repository and can instruct the user to run setup commands, but it should never ask the user to paste OAuth tokens or secret files into chat or commit them.

The minimum local runtime is:

- macOS with Python 3.11+
- Git
- FFmpeg and ffprobe; `ffmpeg-full` is recommended for burned subtitles
- Ollama running locally
- Ollama model `qwen2.5:7b`
- Python dependencies installed in `.venv`
- YouTube OAuth already configured locally

Useful checks on the Mac:

```bash
cd ~/viral-shorts-pipeline
source .venv/bin/activate
ollama list
ollama run qwen2.5:7b
python -m unittest discover -s tests -v
```

Do not remove the Ollama connection from Claude merely to operate the Shorts app. The Shorts app talks directly to Ollama through its local HTTP endpoint. Claude's own GitHub connector and Ollama's model connection are separate.

## 7a. Local setup check

`.venv/bin/python app_runtime.py doctor` (and **Activity & settings → Mac setup check**) reports Python 3.11+, `.venv`, packages, FFmpeg/ffprobe, libass subtitles (optional), Ollama reachability, `qwen2.5:7b` presence (a `:latest` tag also counts) and whether `data/secrets/token.json` exists, with exact fix commands. It never reads or prints credential contents. The `prepare` task calls `editorial.require_model` before downloading or transcribing. `Install-Mac.command` creates `.venv` when missing and runs the doctor without failing installation.

## 8. Validation status

Current (2026-10-29, after the restore described in the log): 70 tests pass with dependencies installed; 2 are skipped on bare Python without Streamlit/libass. CI installs `requirements.txt` so the Streamlit AppTest runs there.

Original handoff status:

At handoff preparation:

- 54 tests pass locally
- GitHub Actions test job passed for the published update
- Streamlit AppTest passed for up-to-10 shortlist rendering, source selection, subtitle default, saved filters, date modes and history-sync dispatch
- `git diff --check` passed
- real FFmpeg render/approval tests passed
- caption capability detection and SRT fallback tests passed
- final editorial audit tests passed

GitHub Actions run that passed: `40889961521`.

## 9. Known limitations and safe next improvements

- YouTube search API quota can limit the number of searches; the app rotates topics rather than pretending to search everything at once.
- “Viral” and “unofficial” are estimates. The app measures source traction; it cannot predict Shorts performance or prove rights.
- Event freshness is based on upload/discovery date, not verified event date.
- Content policy uses title/channel/category/description/audio-language metadata and can miss or over-exclude ambiguous videos.
- The local AI editor sees transcript text, not video pixels. Visual content requires manual selection/review.
- No direct TikTok, Instagram or Twitch connector exists; content must be found/imported through supported YouTube flows.
- No unattended scheduled ingestion is enabled.
- No automatic face tracking, visual highlight detector, automatic thumbnail upload, rights verification or revenue prediction exists.
- Existing old drafts may use older policy/editor IDs; generate new batches after update for the latest selection behavior.
- The app's upload attempt cap uses UTC while history display uses a selected local timezone.

Good future work should preserve the current constraints and tests. If adding a vision model, keep it optional and local; do not silently send user media to a cloud service. If changing upload behavior, preserve public-immediately behavior and durable duplicate protection.

## 10. Instruction to give either assistant

Paste this into Claude or Codex/ChatGPT after it has access to the repository:

> Read `CLAUDE_HANDOFF.md` (especially sections 0 and 2) and `PROJECT_COLLABORATION_LOG.md` completely before changing anything. You are continuing the existing Viral Moment Clips project, not starting a new app. Pull the latest `main` and edit files in place; never replace a file with an older copy, and never remove another assistant's features or tests. Run the full test suite before and after changes; commit only when every test passes. Preserve user data, OAuth credentials, `data/`, public-immediately publishing, duplicate-upload protection, music exclusions, English-only rules, English subtitles and the 15–180 second coherent-cut rule. Keep the workflow: recent discovery → 10 strong choices → accurate complete scene selection → English subtitles → one review/approval → public upload. Never request secrets in chat. If local execution is needed, ask the owner to run `.venv/bin/python app_runtime.py doctor` and share its output. Append a dated entry to `PROJECT_COLLABORATION_LOG.md` with what you changed, why, and the test results.

## 11. Open items and next steps

Owner actions on the Mac (not verifiable from the cloud):
- Click **Activity & settings → Update app** after the latest fix is on `main`, then run `cd ~/viral-shorts-pipeline && .venv/bin/python app_runtime.py doctor` and fix anything marked MISSING (typically `ollama pull qwen2.5:7b`, opening the Ollama app, or `brew install ffmpeg-full`).
- Retry the source that failed scene selection and record the outcome in the log (Codex's boundary-expansion fix).

Suggested next development steps:
1. Run a real end-to-end batch with the 180-second rule and record clip-quality issues in the log.
2. Optional local-timezone view of the daily upload cap (currently UTC; see section 9).
3. Optional local vision check for visual clips (must stay local and optional).
