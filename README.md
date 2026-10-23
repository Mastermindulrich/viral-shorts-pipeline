# Viral Shorts Pipeline

Original-video clips with original audio. No narration. Optional captions. Runs locally with Python 3.11+ and FFmpeg; no paid APIs or hosting. Your computer must remain awake for scheduled work. Electricity, disk space and bandwidth are still required.

## Implemented

- Recent-source discovery from configured YouTube RSS feeds, with SQLite deduplication.
- Optional local CPU transcription using faster-whisper.
- Rough, sentence-aligned 20–50 second speech-window suggestions.
- Batch MP4 exports: 1080×1920, original audio, fit or center-crop, optional burned captions.
- Cover-frame JPEG and local HTML video preview.
- External clearance reference and approval bound to the exact video bytes and metadata.
- Google OAuth upload, default private, with optional future publication time.
- Three upload attempts per UTC day, durable upload receipts and concurrent-worker protection.
- Local scheduled worker for discovery, rendering, and optionally uploading approved jobs.

## Current limits

This is an initial working foundation, not an autonomous channel already producing revenue. The owner has completed a private test upload to Viral Moment Clips. Source feeds and Google access need configuration. Highlight suggestions are a simple heuristic, not an AI virality prediction. Source ingestion, final clip selection, titles and descriptions currently require editorial input. There is no face tracking, automatic thumbnail upload or analytics integration yet. The source list starts empty.

The owner handles content permissions outside this project. The pipeline records the owner's clearance reference; it does not verify licensing. Downloadability does not itself establish rights. Pure clipping may be ineligible for YouTube monetization even with permission.

## Install on your computer

Install Python 3.11+ and FFmpeg/ffprobe from their official sources or a trusted package manager. FFmpeg must include libass for captions.

```sh
git clone https://github.com/Mastermindulrich/viral-shorts-pipeline.git
cd viral-shorts-pipeline
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
mkdir -p data/inbox data/jobs data/secrets
```

Run commands from this folder. All source media, secrets, approvals and exports stay under `data/`, ignored by Git. The repository is public: never commit private material or credentials. Place a source video obtained through your separate content-permissions process in `data/inbox/source.mp4`. This version does not download arbitrary online videos.

## Render actual video clips

Copy `config/job.example.json` to `data/jobs/first-clip.json`. Set local input path, source reference, start/end seconds, accurate title, description and audience declaration. `fit` preserves the complete frame with black padding; `crop` uses a center crop that must be checked for lost faces or action.

```sh
python pipeline.py render data/jobs/first-clip.json
python pipeline.py batch data/jobs
```

Open `data/exports/first-clip/review.html` to watch the export. `cover.jpg` is a first-frame image for review; this version does not automatically set a YouTube Shorts thumbnail.

Optional local transcription and speech-window suggestions:

```sh
python -m pip install -r requirements-transcription.txt
python pipeline.py transcribe data/inbox/source.mp4 --model base
python pipeline.py suggest data/transcripts/source.json
```

The first transcription downloads free model weights. Add `"transcript": "data/transcripts/source.json"` to a job for burned captions. Transcript timestamps refer to the full source; the renderer trims and offsets them. Suggestions in `data/suggestions.json` need editorial selection and conversion into jobs. Inspect caption accuracy, context, timing and framing before approval.

```sh
python pipeline.py approve data/jobs/first-clip.json --clearance-ref "my-external-clearance-record"
```

Any video or metadata change invalidates approval. Re-rendering removes previous approval. This is workflow tracking, not legal verification.

## Discovery

Add actual source channel IDs (not handles) to `config/sources.json`:

```json
[{"name":"Selected creator", "channel_id":"UC_REPLACE_WITH_REAL_CHANNEL_ID"}]
```

`python pipeline.py discover` stores up to 100 recent candidates in `data/candidates.json`, with deduplication in `data/discovery.sqlite3`. RSS provides recent uploads, not view velocity or exhaustive trends. A candidate is not automatically downloaded, cleared or published.

## YouTube authorization

1. Create or select the intended YouTube channel in your Google account.
2. In Google Cloud Console create a project and enable YouTube Data API v3. Configure an OAuth consent screen; if external and testing, add your Google account as a test user.
3. Create a Desktop app OAuth client. Save its JSON locally at `data/secrets/client_secret.json`.
4. Run `python pipeline.py auth` on your computer and complete Google's authorization screen, verifying the intended channel. Credentials remain local; do not paste them into chat or GitHub.
5. Run `python pipeline.py upload data/jobs/first-clip.json` for a private test. Verify the destination in YouTube Studio before public operation.

The application requests YouTube upload and read-only scopes. Read-only permission is used to verify the channel before every upload. Older tokens require reauthorization. Testing-mode OAuth tokens may expire and require consent again. Account restrictions, project verification and API quotas can affect publishing; validate actual scheduling before relying on it. No live OAuth or upload test has been performed without the owner's account.

To schedule publication, use `"privacy":"private"` and a future ISO timestamp with timezone, for example `"publish_at":"2030-01-01T12:00:00-05:00"`. Re-render and approve after editing. For immediate public publication use `"privacy":"public"` without `publish_at`.

A durable `upload.json` reservation is written before the upload starts. Ambiguous failures block automatic retries to prevent duplicates. Inspect YouTube Studio before removing a failed reservation. Daily caps count attempts, including failures. Caps are local, not shared across separate computers.

## Scheduled operation

`python worker.py` discovers sources and renders queued jobs. `python worker.py --publish` additionally uploads approved exports. It never approves a video. Jobs are processed in filename order; absent `publish_at`, they may upload as a batch rather than evenly spaced.

Use your operating system's scheduler. macOS/Linux cron example, replacing both absolute paths:

```cron
0 * * * * cd /absolute/path/viral-shorts-pipeline && /absolute/path/viral-shorts-pipeline/.venv/bin/python worker.py --publish >> data/worker.log 2>&1
```

The machine must stay awake. Remove `--publish` to pause publishing. A local lock blocks simultaneous commands; after a crash, inspect running processes before removing stale `data/worker.lock`. No background worker is started just by cloning the project.

## Test

```sh
python -m unittest discover -s tests -v
```

Tests exercise real FFmpeg export with generated video/audio, caption offsets, approval invalidation and lock protection. CI does not authorize Google or upload videos.

## Next milestones

Approved source ingestion; better source ranking and clip selection; review queue controls; channel performance feedback. No paid infrastructure has been provisioned.


## Local control panel (new)

Update and launch from the repository folder:

```sh
git pull --ff-only
source .venv/bin/activate
python -m pip install -r requirements.txt
python pipeline.py auth
python pipeline.py channel
python -m streamlit run dashboard.py --server.address 127.0.0.1 --browser.gatherUsageStats false
```

The one-time authorization now includes read-only YouTube access so uploads can verify the connected channel. Choose Viral Moment Clips. `channel` must print that name and ID `UC66Gf5TgUNxGHM7DbPUqrSw`. The upload function fails closed on missing permissions or a different channel before creating an upload reservation. The default expected ID is configured in `config/settings.json` for this project.

After installing, use `bash Launch.command` or double-click the executable launcher. The panel binds only to the local computer. Keep the terminal open while using it; Ctrl+C stops it. Do not expose it to a public network.

Create clips from existing files in `data/inbox`, review previews in the queue, choose visibility and optional future publication time, enter your external clearance reference and approve. A separate Upload button sends an approved clip. Google credentials stay in the existing local secrets folder. Source discovery supports adding creator channel IDs and browsing recent uploads. No automatic downloading, autonomous editorial selection, local transcription buttons or background scheduling have been added to the panel yet.

The panel preserves the original audio and does not generate narration. Creating a preview does not upload it. Existing exports and upload receipts remain in place on update. Dates for scheduled uploads must include a timezone and require private visibility.


## Source importing and automatic draft batches

Install optional local tools with `python -m pip install -r requirements-preparation.txt`, then restart the dashboard. In Source discovery, Add starter research channels merges three initial creators without replacing your list. These are candidates for research, not licensed partners or recommendations to repost without clearance.

The Prepare a batch tab imports a single HTTPS YouTube video with your external clearance reference, capped at 1080p, excluding active live streams and sources longer than three hours. It does not use browser cookies or bypass access controls. Download availability depends on YouTube and yt-dlp; authentication, bot checks, JavaScript runtime requirements or source restrictions may prevent downloads. A failed import can be replaced by a local source file in data/inbox. Imported sources are reused rather than downloaded again when their receipt and file exist.

Choose a local or imported video, select up to five drafts, and run local CPU transcription. The first run downloads free model weights. Speech-window selection favors coherent spoken sentences; it is not a reliable predictor of viral performance and cannot identify silent action highlights. Suggested titles are transcript excerpts and must be edited. Drafts default private and have an editorial hold: review and save title, description and audience setting in Review queue before approval. No draft is automatically uploaded.

Captions are off by default because the owner's installed FFmpeg may lack libass. Enable captions only if `ffmpeg -filters` lists subtitles. Original source audio is retained. This release has not been validated against live source downloads or a full speech-model inference on the owner's Mac; the local import/transcription test is the next milestone.


## Editorial upgrade: complete scenes and evidence-based titles

The dashboard now defaults to Story editor. Install the free local Ollama application from https://ollama.com/download and download a local model with `ollama pull qwen2.5:7b`. Keep Ollama running. This model requires several GB of storage and sufficient memory; smaller local models may work but need their own quality validation. Nothing in this integration calls a paid cloud API. Downloading weights needs internet; inference happens at 127.0.0.1:11434. Existing transcription remains local.

The editor reads the full transcript in overlapping sections, summarizes each section, proposes complete 15–90 second scenes with setup and payoff, and compares candidates using the whole-video topic map. It requests a main title, two alternatives, a scene topic, cut rationale, and a supporting transcript quote. Programmatic validation rejects out-of-range boundaries, unsupported numeric title strings, missing evidence quotes and weak model-rated coherence/payoff. These checks do not prove truth or eliminate hallucinations: reviewers must still verify names, factual implications, quote meaning and the actual video. Visual reactions are not inferred from frames in this release.

A local model is an editorial assistant, not a predictor of views. Strong curiosity-driven titles must describe the specific moment. No claims of bank balances from net worth, no invented identities, no fictional reactions. The review queue shows title alternatives, transcript evidence, setup, payoff and cut rationale. It still requires metadata review and approval before uploads. Old basic drafts/approvals remain unchanged; semantic drafts use story-v1 IDs and remain unapproved. Repeated runs reuse an existing semantic job rather than overwriting edits. Basic mode is explicitly labeled; if the AI editor fails it reports the error rather than silently using basic cuts.

Source scouting now has a Rank sources button. It batches video statistics and duration lookups and highlights 90-second to three-hour sources. Priority combines log views/hour and relative performance against the creator's retrieved sample median. On the first scan, views/hour means lifetime average since upload; actual measured growth becomes available after snapshots at least 15 minutes apart. This is a transparent experimental prioritization score, not a virality probability, earnings estimate, or permission check. No automatic public posting is enabled.

This release was tested with mocked model/API responses and real synthetic FFmpeg rendering. A live model run on the owner's Mac and a before/after editorial review on a real source are still required before claiming better clip quality.


## Topic-agnostic discovery

Scout across topics merges the public mostPopular chart from three configurable regions with four rotating searches among 18 topic families: politics, dance, celebrities, soccer, basketball, news, Hollywood, finance, geopolitics, culture, debates, music, comedy, other sports, science/technology, human stories, lifestyle and gaming. Topics guide coverage, not preference in ranking. Queries cover uploads from the preceding three days ordered by view count. Run Rank sources afterward to retrieve growth signals and duration. Rotation state is saved locally and the most recent 1,000 candidates retained, deduplicated by video ID.

This is a quota-bounded sample, not coverage of every topic on every scan or every platform. Popular charts may omit topics and depend on YouTube availability. Queries currently use English and charts default to US, GB and CA; edit config/discovery.json for other regions or query languages. Four search calls plus up to three chart calls per scan are bounded in code; API daily quota exhaustion can still occur after repeated scans. Errors are shown with partial results retained. Traditional creator-feed discovery replaces the candidate file; run broad scouting afterward to merge additional results.

Prioritization has no positive or negative category weight. It ranks measured growth or lifetime average views/hour with sample-relative performance; that is an experimental proxy for audience interest, not a prediction of clicks. Speech-only semantic clipping is unsuitable for silent dance/sports/action moments without visual editorial review. No visual scene understanding or automatic publishing is claimed in this release.
