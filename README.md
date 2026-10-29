# Viral Moment Clips

A local Shorts studio: discover promising YouTube sources, select complete moments,
create English captions, review and publish. Original sound only; no narration.
The former 60-second cap has been removed. New clips may be up to 180 seconds, with the shortest coherent self-contained cut preferred. The dashboard publishes approved
clips **public immediately**; YouTube processing or channel restrictions can delay playback.

## Daily workflow

1. Open **Viral Moment Clips.app** from your Mac Applications folder.
2. In **Find videos**, click **Find and rank videos**. Each round shows up to **10 choices**.
3. Pick **Generate clips from this video** if you saved an applicable permission
   reference. Otherwise choose **Use this video**, then **Make clips**, enter the
   permission reference and click **Generate clips**.
4. Open **Review & publish**, watch the preview, check the title, captions and
   audience, tick the review confirmation and click **Approve & publish now**.
   You can also save approvals and publish a selected batch.
5. **Published** defaults to today's uploads. Choose a particular day, month, year,
   all dates, or search titles. Dates use America/Toronto by default; change that
   under **Activity & settings**.

The Mac must stay awake and Ollama must be running with `qwen2.5:7b` installed.
Tasks continue if the browser is closed or refreshed. The first use of a new
transcription model downloads its free weights; transcription on a long source
and the extra editorial review can take several minutes or longer.

## Recent discovery and momentum

Defaults: uploads from the last **3 days**, at least **5,000 views**, at least
**200 views/hour**, and a preference for independent uploads. Save different
settings in **Find videos → Discovery filters**. Filter choices are stored in
`data/scouting-preferences.json`, so existing local config files stay intact.

Included categories cover Champions League/football, exceptional sports moments,
athlete controversies, influencer life, streamers, unexpected incidents, fan movie
cuts, engineering hacks, celebrity fashion/red carpet/paparazzi footage, gaming,
interviews, African urban dance, TikTok dance challenges, trailers and music reactions.
Previous broad categories remain available in the filter chooser. An empty category
selection means all categories. Standalone music releases remain excluded, including
Music-category uploads unless they clearly match an allowed editorial/visual format.

- Ranking combines recent views/hour or measured growth, freshness, engagement and
  sample-relative source performance. Measured growth needs two observations at least
  15 minutes apart; before that, the UI explicitly labels the lifetime average.
- A scan searches up to four rotating categories/event queries and checks popular
  charts. Date-sorted searches alternate with view-count-sorted searches. Additional
  scans rotate through your selected topics. API quotas still apply.
- Shortlists show up to ten qualifying videos, with no more than two per channel and
  no identical titles. The list may contain fewer than ten; weak matches are not added
  merely to fill it. Scores are source signals, not predictions of Shorts performance.
- Official/independent classification uses channel-name clues. It is **not verified
  ownership**. Choose Prefer independent, Any source, or Exclude likely official;
  block exact channel names/IDs and exclude unwanted words when necessary.
- Add optional **Specific events to follow**, one query per line. One event query is
  included per scan and rotates through the list. Include/exclude keywords are
  comma-separated phrases. An event query still obeys language, music, date and
  momentum filters.
- Discovery is through **YouTube**; TikTok/streamer content means videos available
  there, not direct access to TikTok, Instagram or Twitch. A fresh upload can show an
  older event. Metadata screening does not fact-check breaking news.
- **Hide this video** persists across scans. Restore items under Hidden videos.
  Updates with a new policy version hide old results until they are refreshed.

## Accurate dialogue clips and English subtitles

The local AI reads every transcript section, compares scenes across a whole-video
topic map and runs a final context check against dialogue around each proposed cut.
It favors a clear opening, complete setup/payoff, concrete stakes and supported titles.
The final pass can tighten boundaries or reject misleading fragments. Evidence quotes
and numeric title claims are checked against the selected scene; repeated topics and
overlapping cuts are rejected. AI quality still depends on the source and local model.

Automatic dialogue clips must contain English speech. Confidently detected non-English
speech blocks automatic editing. Dance and other visual footage can be selected manually
under **Make clips → Already imported video → Choose a visual moment manually**.
The editor analyzes dialogue; it cannot verify a goal, stunt, facial expression or
engineering demonstration visually. Review the picture and context before publication.
Manual visual cuts also attempt English transcription on just the chosen interval;
captions are omitted with an explicit status if no confident English speech is detected.

English subtitle burning is **on by default** for new automated batches. Transcription
uses the `small` model and word timestamps by default; base/small/medium can be chosen in
Editing options. Short timed cues improve readability. Every automatic dialogue draft
also has a downloadable `.en.srt` file. The renderer trims and offsets timings to the
actual clip. Subtitles preserve spoken English; they do not translate foreign audio.

If FFmpeg lacks the subtitles/libass filter, a draft is created with a clearly labelled
SRT file instead of burned text. For burned subtitles on a Mac, run once:

```bash
brew install ffmpeg-full
```

Then restart the studio and generate new clips. The app automatically detects the
Homebrew alternate executable at `/opt/homebrew/opt/ffmpeg-full/bin` or
`/usr/local/opt/ffmpeg-full/bin`; no global relinking is needed. Existing exports are
not silently modified. Review caption spelling, names and timing before publishing.

**Make clips → Editing options → Save production defaults** saves clip count, subtitle
preference, transcription quality and an optional applicable permission reference.
Production preferences live in `data/studio-preferences.json`.

## Published history

New receipts save exact upload timestamps and YouTube publication timestamps when
returned. **Published → Refresh publication dates from YouTube** backfills older receipts
and refreshes recorded visibility without changing videos or retrying uploads.
Until backfilled, legacy receipts are labelled with their original UTC date. The history
contains uploads made through this app, not unrelated channel uploads. Uncertain attempts
remain visibly separate from confirmed video links; check YouTube Studio before retrying.

## Install or update on a Mac

Prerequisites: Python 3.11+, Git, FFmpeg/ffprobe, and local Ollama/Qwen. No paid AI APIs or
hosting are used. Your YouTube OAuth connection and expected channel must be configured.

```bash
git clone https://github.com/Mastermindulrich/viral-shorts-pipeline.git
cd viral-shorts-pipeline
bash Install-Mac.command
```

The installer creates `.venv` with Python 3.11+ if it is missing, installs dependencies,
runs a setup check and installs the launcher. Re-running it keeps `data/` and your settings.
Check local readiness at any time (also shown under **Activity & settings → Mac setup check**):

```bash
cd ~/viral-shorts-pipeline
.venv/bin/python app_runtime.py doctor
```

It reports Python, `.venv`, packages, FFmpeg/ffprobe, burned-subtitle support, whether
Ollama is running, whether `qwen2.5:7b` is pulled and whether YouTube sign-in exists, with
the exact command for anything missing. It never prints credential contents.
**Generate clips** checks Ollama and the model first, so a missing editor fails in seconds
instead of after a long download and transcription.

For an existing installation, use **Activity & settings → Update app**. It fetches the
configured upstream, accepts only a fast-forward update, preserves local JSON config,
installs dependencies, runs checks and restarts the service. Failed installation/tests
restore the previous code. Dependency changes are not fully rolled back. Local code edits
stop the updater to protect your work. Videos, credentials, receipts and preferences stay
in `data/`; they are not committed to Git.

The macOS launchd service starts at login and the Finder app opens the dashboard at
`http://127.0.0.1:8501`. It does not require keeping VS Code or a terminal open. Logs are in
`data/logs/activity.log`; **Activity & settings** provides filtered diagnostics to share.
The previous manual interface remains available as `dashboard_legacy.py`.

## Development and operational limits

```bash
python -m pip install -r requirements.txt -r requirements-preparation.txt
python -m unittest discover -s tests -v
python -m streamlit run dashboard.py
```

Tests include real FFmpeg video rendering and approval checks. The real burned-caption
test runs when the subtitles filter exists; its explicit skip does not skip core tests.

Sources and final editorial review remain under the owner's control. The pipeline records
an external permission reference, not a licensing determination. Approval is bound to the
exact exported bytes and job metadata. Uploads verify the expected channel and use durable
reservations to prevent automatic duplicate attempts after ambiguous failures. A clip is
also blocked when an earlier upload attempt (confirmed or uncertain) used the same source
and overlaps at least half of the shorter clip, or has identical video bytes, so a
regenerated batch cannot republish a moment. Review & publish shows these as warnings.
In a multi-clip publish, a blocked clip no longer stops the remaining clips. The daily
attempt limit uses UTC independently of the publishing-history display timezone.

Discovery and preparation run on demand. There is no unattended scheduled ingestion,
visual vision model, face tracking, revenue guarantee or automatic Shorts thumbnail upload.
