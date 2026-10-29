# Viral Moment Clips — Complete Handoff for Claude

Updated: 2026-10-29 (America/Toronto)
Canonical repository: `https://github.com/Mastermindulrich/viral-shorts-pipeline`
Canonical GitHub branch: `main`
Latest published remote commit: `ea8ae8dbbe14869dad49d75b9b1c904803416aa8`
Latest local snapshot commit: `9954d5a` (the remote tree is the authoritative project state)

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

- Every exported and uploaded clip must be 60 seconds or less. This is checked in job validation, rendering, approval and upload, including measured media duration.
- Automatically edited dialogue must be English. High-confidence non-English transcription blocks automatic dialogue editing.
- Visual dance, sports action and other silent/visual moments can be selected manually.
- Original audio is preserved. There is no narration or synthetic voice.
- Titles, descriptions and explanations are written in English.
- Clips must have a coherent opening/setup and a complete payoff. Avoid mid-sentence cuts, ads, intros, topic changes, context-dependent fragments and unsupported claims.
- Videos are uploaded with `privacyStatus=public` immediately after approval. YouTube processing can still delay playback.
- The app verifies the expected YouTube channel before upload. Expected channel name is Viral Moment Clips; expected ID is `UC66Gf5TgUNxGHM7DbPUqrSw`.
- Upload attempts reserve a receipt before network upload to avoid automatic duplicate retries after ambiguous failures.
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
4. propose complete 15–60 second scenes
5. rank distinct scenes
6. run a second context-audit pass against surrounding dialogue
7. validate evidence quotes, numbers, title claims, language, boundaries, payoff and non-overlap
8. render vertical previews
9. place jobs in the review queue

Default transcription model is `small`; `base`, `small` and `medium` are selectable. The local editorial model is Ollama `qwen2.5:7b`. It is called through `http://127.0.0.1:11434/api/chat` and must be installed locally. Cloud models are deliberately rejected.

Manual visual path:

`Make clips → Already imported video → Choose a visual moment manually`

The user previews the source and enters start/end seconds, an English title and a 1–60 second duration. The app attempts English transcription only on that selected interval for subtitles. It cannot visually verify a goal, stunt, facial expression or engineering demonstration, so the preview must be checked.

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
- `content_policy.py` — English/60-second/music exclusion policy, topic overlays and source classification estimate
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
- `tests/` — unit, integration and Streamlit-related fixtures
- `Install-Mac.command` — one-time Mac installation
- `Launch.command` — launcher helper
- `README.md` — user-facing operating guide

Runtime data is under `data/` and should remain ignored by Git: OAuth secrets, token files, imported media, transcripts, jobs, exports, approvals, receipts, logs, saved discovery preferences, hidden videos and publication history.

## 5. Background task behavior

The dashboard starts a separate local worker process for `scout`, `rescreen`, `import`, `prepare`, `visual`, `publish`, `sync_history` and `update`. `data/activity.json` records status and stage. `data/logs/activity.log` records output. The UI fragment refreshes every three seconds and releases/re-enables controls when work completes.

The app cannot process while the Mac is asleep. Ollama must be running for semantic selection. No unattended daily ingestion is currently enabled; scouting is on demand.

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

## 8. Validation status

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

## 10. Exact instruction to give Claude

Paste this into Claude Code after it has access to the repository:

> Read `CLAUDE_HANDOFF.md` completely before changing anything. You are taking over the existing Viral Moment Clips project, not starting a new app. Treat GitHub `main` and this handoff as the authoritative current state. First inspect the repository, current branch, tests and recent commit `ea8ae8dbbe14869dad49d75b9b1c904803416aa8`. Do not reset, rewrite or remove existing user data, OAuth credentials, `data/` files, public-upload behavior, music exclusion, English-only policy or the 60-second limit. Run the test suite before making changes, then make a concrete implementation plan based on the current code. Keep the dashboard workflow streamlined: recent discovery → 10 strong choices → accurate complete scene selection → English subtitles → one review/approval → public upload. Preserve the user’s desired categories and saved filtering/date-history behavior. Do not expose or request secrets in chat. If local execution is needed, check for `.venv`, FFmpeg, Ollama and `qwen2.5:7b`; explain any missing dependency clearly. Before proposing a change, run relevant tests and show the result. Before opening a PR or pushing, provide a reviewable summary and validation results. Do not create a replacement architecture without first understanding the existing modules and data contracts.

Claude should then be asked to begin with:

> Inspect the repository and confirm your understanding of the current implementation, current limitations and the next three highest-value improvements. Do not edit yet. Report any mismatch between `CLAUDE_HANDOFF.md`, the code and the latest GitHub commit.

